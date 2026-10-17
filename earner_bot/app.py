"""
app.py — Ouroboros Bot 3.1 Main Application
Cloud Run HTTP entrypoint with 13-gate decision pipeline.
All state is persisted to disk. AED portfolio tracking throughout.

Gate Pipeline:
  0. Halt flag check
  1. Fetch balances & price
  2. Stop-loss / Take-profit / Trailing stop check
  3. Time-based exit check
  4. Reconcile position vs exchange
  5. Capital protection tier (with auto daily/weekly/monthly resets)
  6. Fetch market data + indicators (closed candles only)
  7. Regime detection + Black Swan check
  8. Multi-timeframe directional confluence
  9. Confluence scoring + minimum threshold
  10. Idempotency check
  11. Adaptive Kelly position sizing
  12. Execute trade with order confirmation
"""
import logging
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                    force=True)

from flask import Flask, jsonify, request, send_from_directory, session, abort
import os
import dotenv
import webview
from functools import wraps
from flask_wtf.csrf import CSRFProtect, generate_csrf, CSRFError
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
import threading
trade_lock = threading.Lock()
import time
import requests
import pandas as pd

from strategy import (
    get_data, add_indicators, detect_regime, get_signal,
    multi_timeframe_gate, drop_incomplete_candle,
)
from risk import (
    adaptive_kelly_size, CapitalProtectionTiers,
    compute_stop_loss, compute_take_profit,
    check_stop_take, portfolio_value_usd, portfolio_value_aed,
)
from broker_binance import (
    get_balances,
    execute_buy_safe,
    execute_sell_safe,
    get_current_price,
    safe_api_call, init_client,
)
import broker_binance
from concurrent.futures import ThreadPoolExecutor

# Separate pool for order execution (prevents websocket starvation during 50s chases)
execution_pool = ThreadPoolExecutor(max_workers=10)
from idempotency import IdempotencyGuard, make_decision_id
from watchdog import (
    is_halted, emergency_close_all, ExceptionCounter,
    create_halt_flag, clear_halt,
)
from notifier import (
    send_telegram, send_trade_alert, send_daily_summary,
    send_stop_loss_alert, fmt_aed,
)
from audit import audit
from state import StateManager
from ws_engine import WebSocketEngine
import config
from loggers import trade_logger

logger = logging.getLogger("Ouroboros.app")

app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "Ouroboros_bot_static_secret_key_99123")

# Ensure cookies are secure
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Strict',
    PERMANENT_SESSION_LIFETIME=timedelta(days=365)
)

csrf = CSRFProtect(app)

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    return jsonify({"error": "Session expired or invalid CSRF token"}), 401

@app.errorhandler(401)
def handle_401_error(e):
    return jsonify({"error": "Unauthorized"}), 401

# Fallback passphrase if not set in .env
ADMIN_PASSPHRASE = os.environ.get("ADMIN_PASSPHRASE", "Ouroboros")

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            abort(401)
        return f(*args, **kwargs)
    return decorated_function

# ─── Persistent State (survives restarts) ─────────────────────────
state_mgr    = StateManager()
ws_engine    = WebSocketEngine(state_mgr)
idem_guard   = IdempotencyGuard(state_mgr.idempotency_cache)
exc_counter  = ExceptionCounter(threshold=3)


def _save_state() -> None:
    """Persist all state to disk atomically."""
    state_mgr.idempotency_cache = idem_guard.get_cache()
    state_mgr.save()


# ═══════════════════════════════════════════════════════════════════
#  HTTP ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@app.route("/health")
def health():
    """Health check with portfolio status in AED."""
    port_aed = 0.0
    symbol = state_mgr.last_analysis.get("symbol", "BTCUSDT")
    try:
        balances = get_balances()
        if balances:
            # Build prices dict for all held assets
            prices = {}
            for asset in balances:
                if asset != 'USDT':
                    p = get_current_price(f"{asset}USDT")
                    if p:
                        prices[f"{asset}USDT"] = p
            port_usd = portfolio_value_usd(balances, prices)
            port_aed = port_usd * config.AED_USD_RATE
    except Exception as e:
        logger.error(f"Error in health check: {e}")

    return jsonify({
        "status":       "halted" if is_halted() else "ok",
        "paper_mode":   config.PAPER_MODE,
        "symbol":       symbol,
        "has_position":  len(state_mgr.open_trades) > 0,
        "portfolio_aed": round(port_aed, 2),
        "ts":           datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/login", methods=["POST"])
def login():
    """Authenticate via passphrase."""
    data = request.get_json()
    if data and data.get("passphrase") == ADMIN_PASSPHRASE:
        session["logged_in"] = True
        session.permanent = True
        return jsonify({"status": "success"})
    return jsonify({"error": "Invalid passphrase"}), 401


@app.route("/api/logout", methods=["POST"])
def logout():
    """Clear session."""
    session.clear()
    return jsonify({"status": "success"})


@app.route("/api/csrf", methods=["GET"])
def get_csrf():
    """Return a CSRF token for the frontend SPA to use in POST requests."""
    return jsonify({"csrf_token": generate_csrf()})


@app.route("/emergency", methods=["POST"])
@login_required
def emergency():
    """Emergency close all positions and halt."""
    emergency_close_all(state_mgr)
    _save_state()
    return jsonify({"status": "emergency_close_executed"})


@app.route("/resume", methods=["POST"])
@login_required
def resume():
    """Clear halt flag to resume trading."""
    clear_halt()
    send_telegram("✅ Halt cleared by operator. Bot resuming next cycle.")
    return jsonify({"status": "resumed"})


@app.route("/status")
@login_required
def status():
    """Detailed bot status with trade history and AED values."""
    stats = state_mgr.daily_stats
    history = state_mgr.get_trade_history(10)
    
    # Calculate full blacklist for display
    from market_scanner import CORE_BLACKLIST
    custom_bans = {s.strip().upper() for s in config.BLACKLIST_SYMBOLS.split(",") if s.strip()}
    custom_bans = {s if s.endswith("USDT") else f"{s}USDT" for s in custom_bans}
    full_bl = list(CORE_BLACKLIST.union(custom_bans))
    full_bl_str = ", ".join(full_bl) if full_bl else "None"
    
    # Calculate current portfolio values
    balances = get_balances()
    portfolio_usd = 0.0
    portfolio_aed = 0.0
    if balances:
        # Build prices dict for all held assets
        prices = {}
        for asset in balances:
            if asset != 'USDT':
                p = get_current_price(f"{asset}USDT")
                if p:
                    prices[f"{asset}USDT"] = p
        portfolio_usd = portfolio_value_usd(balances, prices)
        portfolio_aed = portfolio_value_aed(balances, prices)
        
    # Calculate top candidates from background scans
    scanned = state_mgr.state.get("scanned_candidates", {})
    top_candidates = []
    if scanned:
        # Sort by score descending
        sorted_scanned = sorted(scanned.items(), key=lambda x: x[1].get("score", 0) if isinstance(x[1], dict) else x[1], reverse=True)
        
        for sym, data in sorted_scanned[:20]:
            if isinstance(data, dict):
                score = data.get("score", 0)
                breakdown = data.get("breakdown", {})
                regime = data.get("regime", "UNKNOWN")
            else:
                # Fallback for old integer format
                score = data
                breakdown = {}
                regime = "UNKNOWN"
                
    # ─── Institutional Telemetry Collectors ───
    # 1. Order Flow Snapshot for current focus asset
    focus_sym = "BTCUSDT"
    if state_mgr.open_trades:
        focus_sym = state_mgr.open_trades[0]["symbol"]
    elif state_mgr.last_analysis and state_mgr.last_analysis.get("symbol"):
        focus_sym = state_mgr.last_analysis.get("symbol")
        
    from orderflow_engine import orderflow_engine
    of_snapshot = orderflow_engine.get_orderflow_snapshot(broker_binance.client, focus_sym)

    # 2. Pre-Trade Risk Engine Status
    from pre_trade_risk import risk_gate
    daily_pnl = float(stats.get("pnl_usd", 0.0))
    daily_dd_pct = (daily_pnl / portfolio_usd * 100.0) if portfolio_usd > 0 else 0.0
    current_exposure = sum(float(t.get("price", 0.0)) * float(t.get("qty", 0.0)) for t in state_mgr.open_trades)
    
    risk_telemetry = {
        "daily_drawdown_pct": round(daily_dd_pct, 2),
        "max_drawdown_limit_pct": round(risk_gate.limits.max_daily_drawdown_pct * 100.0, 1),
        "current_exposure_usd": round(current_exposure, 2),
        "max_exposure_usd": round(risk_gate.limits.max_portfolio_exposure_usd, 2),
        "max_ticket_usd": round(risk_gate.limits.max_order_notional_usd, 2),
        "status": "CIRCUIT_BREAKER_ACTIVE" if daily_dd_pct <= -risk_gate.limits.max_daily_drawdown_pct * 100.0 else "NOMINAL"
    }

    # 3. Dead-Man's Switch Pulse
    import json
    hb_file = os.path.join("output", "heartbeat.json")
    dms_status = "STANDBY"
    dms_latency_ms = 0
    if os.path.exists(hb_file):
        try:
            with open(hb_file, "r") as f:
                hb_data = json.load(f)
            elapsed = time.time() - float(hb_data.get("timestamp", 0.0))
            dms_latency_ms = int(elapsed * 1000)
            dms_status = "ARMED" if elapsed < 3.5 else "TRIGGERED"
        except Exception:
            pass
            
    dead_man_telemetry = {
        "status": dms_status,
        "latency_ms": dms_latency_ms
    }

    # 4. Learning Memory & Neural Vault Telemetry
    from learning_memory import learning_memory
    active_penalties = []
    for fp, rec in learning_memory.memory.items():
        if rec.get("penalty", 0) != 0:
            active_penalties.append({
                "fingerprint": fp,
                "penalty": rec["penalty"],
                "win_rate": round(rec.get("win_rate", 0.0) * 100, 1),
                "trades": rec.get("trades", 0)
            })
            
    vault_dossier_count = 0
    vault_trades_dir = os.path.join("Obsidian_Vault", "Trades")
    if os.path.exists(vault_trades_dir):
        vault_dossier_count = len([f for f in os.listdir(vault_trades_dir) if f.endswith(".md")])
        
    memory_telemetry = {
        "active_penalties": active_penalties,
        "vault_dossier_count": vault_dossier_count
    }

    # 5. AETHERIS Micro-Alpha Strategy Telemetry
    from aetheris_engine import aetheris_engine
    aeth_state = aetheris_engine.update_and_evaluate(of_snapshot)
    aetheris_telemetry = {
        "dislocation": aeth_state.hydrodynamic_dislocation,
        "threshold": aeth_state.phase_transition_threshold,
        "is_cavitation": aeth_state.is_cavitation_vacuum,
        "entropy_concentration": aeth_state.entropy_concentration,
        "viscosity": aeth_state.liquidity_viscosity,
        "signal": aeth_state.signal,
        "confidence": aeth_state.confidence_score,
        "structural_sl": aeth_state.density_stop_loss,
        "cavitation_tp": aeth_state.cavitation_take_profit,
        "rr_ratio": aeth_state.risk_reward_ratio
    }

    return jsonify({
        "open_trades":  state_mgr.open_trades,
        "daily_stats": stats,
        "recent_trades": history,
        "halted":      is_halted(),
        "paper_mode":  config.PAPER_MODE,
        "blacklist_symbols": full_bl_str,
        "scanned_symbols": state_mgr.state.get("last_scanned_symbols", []),
        "top_candidates": top_candidates,
        "next_scan_time": state_mgr.state.get("next_scan_time", 0),
        "portfolio_aed": portfolio_aed,
        "portfolio_usd": portfolio_usd,
        "last_analysis": state_mgr.last_analysis,
        "orderflow": of_snapshot,
        "risk_telemetry": risk_telemetry,
        "dead_man_telemetry": dead_man_telemetry,
        "memory_telemetry": memory_telemetry,
        "aetheris_telemetry": aetheris_telemetry,
        "broker_venue": {
            "primary": "BINANCE_SPOT",
            "mt5_available": True,
            "mode": "SPOT" if not config.FUTURES_MODE else "FUTURES"
        }
    })


@app.route("/api/config", methods=["GET"])
@login_required
def get_config():
    """Return masked config status (true if configured)."""
    env_file = dotenv.find_dotenv()
    if not env_file:
        return jsonify({"configured": False})
    
    # Check if the keys exist and are not the placeholder text
    api_key = os.environ.get("BINANCE_API_KEY", "")
    secret = os.environ.get("BINANCE_SECRET", "")
    telegram = os.environ.get("TELEGRAM_BOT_TOKEN", "")

    configured_keys = {
        "api": bool(api_key) and "paste_your" not in api_key.lower(),
        "secret": bool(secret) and "paste_your" not in secret.lower(),
        "telegram_token": bool(telegram) and "paste_your" not in telegram.lower(),
        "telegram_chat_id": bool(os.environ.get("TELEGRAM_CHAT_ID", ""))
    }

    configured = configured_keys["api"] and configured_keys["secret"]
    return jsonify({
        "configured": configured, 
        "configured_keys": configured_keys,
        "paper_mode": config.PAPER_MODE,
        "futures_mode": config.FUTURES_MODE,
        "blacklist_symbols": config.BLACKLIST_SYMBOLS
    })


@app.route("/api/config", methods=["POST"])
@login_required
def update_config():
    """Update API keys in .env securely."""
    data = request.get_json()
    env_file = dotenv.find_dotenv()
    
    if not env_file:
        # Create .env if it doesn't exist
        env_file = os.path.join(os.getcwd(), ".env")
        with open(env_file, 'w') as f:
            f.write("PAPER_MODE=true\nSYMBOL=BTCUSDT\n")

    if data.get("binance_api_key"):
        dotenv.set_key(env_file, "BINANCE_API_KEY", data["binance_api_key"])
        os.environ["BINANCE_API_KEY"] = data["binance_api_key"]
        config.BINANCE_API_KEY = data["binance_api_key"]
    
    if data.get("binance_secret"):
        dotenv.set_key(env_file, "BINANCE_SECRET", data["binance_secret"])
        os.environ["BINANCE_SECRET"] = data["binance_secret"]
        config.BINANCE_SECRET = data["binance_secret"]

    if data.get("telegram_token"):
        dotenv.set_key(env_file, "TELEGRAM_BOT_TOKEN", data["telegram_token"])
        os.environ["TELEGRAM_BOT_TOKEN"] = data["telegram_token"]
        config.TELEGRAM_BOT_TOKEN = data["telegram_token"]

    if data.get("telegram_chat_id"):
        dotenv.set_key(env_file, "TELEGRAM_CHAT_ID", data["telegram_chat_id"])
        os.environ["TELEGRAM_CHAT_ID"] = data["telegram_chat_id"]
        config.TELEGRAM_CHAT_ID = data["telegram_chat_id"]

    if "paper_mode" in data:
        mode_str = "true" if data["paper_mode"] else "false"
        dotenv.set_key(env_file, "PAPER_MODE", mode_str)
        os.environ["PAPER_MODE"] = mode_str
        config.PAPER_MODE = data["paper_mode"]

    if "futures_mode" in data:
        fmode_str = "true" if data["futures_mode"] else "false"
        dotenv.set_key(env_file, "FUTURES_MODE", fmode_str)
        os.environ["FUTURES_MODE"] = fmode_str
        config.FUTURES_MODE = data["futures_mode"]

    init_client()

    return jsonify({"status": "success", "message": "Configuration saved."})


@app.route("/api/chart", methods=["GET"])
@login_required
def get_chart_data():
    """Returns the last 150 candles with MA25 for the UI chart."""
    try:
        symbol = request.args.get("symbol")
        if not symbol:
            symbol = state_mgr.last_analysis.get("symbol", "BTCUSDT")
        
        interval = request.args.get("interval", config.INTERVAL_PRIMARY)
        
        raw_df = get_data(broker_binance.client, symbol, interval, 350)
        df = add_indicators(raw_df)
        
        chart_data = []
        for idx, row in df.iterrows():
            chart_data.append({
                "time": int(idx.timestamp()),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "kalman": float(row.get("Kalman")) if "Kalman" in row and not pd.isna(row.get("Kalman")) else None,
                "vwap": float(row.get("VWAP")) if "VWAP" in row and not pd.isna(row.get("VWAP")) else None
            })
        
        # Limit to the last 100 candles for a zoomed-in look
        return jsonify({"status": "success", "data": chart_data[-100:]})
    except Exception as e:
        logger.error("Chart error: %s", e, exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/")
def serve_index():
    """Serve the SPA frontend."""
    return send_from_directory(app.static_folder, 'index.html')


@app.route("/<path:path>")
def serve_static(path):
    """Serve static files."""
    return send_from_directory(app.static_folder, path)


def background_scan():
    try:
        from market_scanner import get_top_symbols
        from concurrent.futures import ThreadPoolExecutor
        from reconcile import reconcile_all_positions
        
        # Run reconciliation first
        reconcile_all_positions(state_mgr)
        
        symbols = get_top_symbols(broker_binance.client, limit=20)
        state_mgr.state["last_scanned_symbols"] = symbols
        # Removed clearing of scanned_candidates to prevent UI glitch during scans
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            executor.map(_evaluate_symbol_async, symbols)
            
        import time
        from datetime import datetime, timezone
        state_mgr.state["next_scan_time"] = time.time() + 300  # 5 minutes
        
        if "last_analysis" in state_mgr.state:
            state_mgr.state["last_analysis"]["ts"] = datetime.now(timezone.utc).isoformat()
        
        state_mgr.save()
            
    except Exception as e:
        logger.error(f"Background scan error: {e}")

@app.route('/api/run_cycle', methods=['POST'])
@login_required
def run_cycle():
    """
    Forces a manual background evaluation of top symbols.
    """
    from threading import Thread
    Thread(target=background_scan, daemon=True).start()
    return jsonify({"action": "BACKGROUND_SCAN_STARTED", "message": "Evaluating in background..."})

def _scanner_loop():
    """Runs the background scan autonomously every 5 minutes."""
    import time
    while True:
        logger.info("Starting autonomous market scan cycle...")
        background_scan()
        time.sleep(300)

def _evaluate_symbol_async(symbol: str, price: float = None):
    """
    Evaluates a single symbol. Triggered by WebSocket candle close or background scan.
    """
    try:
        from strategy import (
            get_data, add_indicators, drop_incomplete_candle, 
            detect_regime, get_signal, multi_timeframe_gate
        )
        from risk import portfolio_value_usd
        
        # Check protection
        if is_halted():
            return
            
        balances = get_balances()
        if not balances:
            return
            
        if price is None:
            price = get_current_price(symbol)
        if not price:
            return
            
        # Check if we already hold it
        trade = state_mgr.get_trade(symbol)
        if trade:
            # Verify active trade against exchange balances
            if not config.PAPER_MODE:
                base_asset = symbol.replace("USDT", "")
                if config.FUTURES_MODE:
                    from broker_binance import safe_api_call, client
                    pos_info = safe_api_call(client.futures_position_information, symbol=symbol)
                    pos_amt = 0.0
                    if pos_info:
                        for p in pos_info:
                            if p["symbol"] == symbol:
                                pos_amt = float(p["positionAmt"])
                                break
                    if pos_amt == 0.0:
                        logger.warning(f"Position for {symbol} closed externally. Clearing state.")
                        state_mgr.remove_trade(symbol)
                        return
                else:
                    asset_bal = float(balances.get(base_asset, 0.0))
                    if asset_bal * price < 5.0:  # Binance min notional threshold
                        logger.warning(f"Position for {symbol} closed externally. Clearing state.")
                        state_mgr.remove_trade(symbol)
                        return

            state_mgr.update_highest_price(symbol, price)
            state_mgr.update_lowest_price(symbol, price)
            early_reversal_trigger = None
            try:
                df_check = add_indicators(get_data(broker_binance.client, symbol, config.INTERVAL_PRIMARY, 50))
                current_atr = df_check.iloc[-1]["ATR"] if len(df_check) > 0 else price * 0.01
                
                # Check for Early Reversal based on candlestick and indicators
                if len(df_check) >= 30:
                    regime_check = detect_regime(df_check)
                    signal_check = get_signal(df_check, regime_check, broker_binance.client, symbol)
                    
                    trade_to_check = state_mgr.get_trade(symbol)
                    if trade_to_check:
                        side = trade_to_check.get("side", "LONG")
                        last_candle = df_check.iloc[-1]
                        
                        if side == "LONG":
                            if signal_check["signal"] == "SELL" and signal_check["score"] >= 60:
                                early_reversal_trigger = "EARLY_REVERSAL"
                            elif last_candle.get("is_shooting_star", False) or last_candle.get("is_bearish_engulfing", False):
                                early_reversal_trigger = "PATTERN_EXIT"
                        elif side == "SHORT":
                            if signal_check["signal"] == "BUY" and signal_check["score"] >= 60:
                                early_reversal_trigger = "EARLY_REVERSAL"
                            elif last_candle.get("is_hammer", False) or last_candle.get("is_bullish_engulfing", False):
                                early_reversal_trigger = "PATTERN_EXIT"
            except Exception as e:
                logger.error(f"Error checking indicators for {symbol}: {e}")
                current_atr = price * 0.01
            
            from risk import check_stop_take
            with trade_lock:
                # Re-fetch trade inside lock to ensure it hasn't been closed by another thread
                trade = state_mgr.get_trade(symbol)
                if not trade:
                    return
                    
                exit_trigger = check_stop_take(trade, price, current_atr)
                if early_reversal_trigger and not exit_trigger:
                    exit_trigger = early_reversal_trigger
                    
                if exit_trigger:
                    prices = {symbol: price}
                    port_usd = portfolio_value_usd(balances, prices)
                    execution_pool.submit(_execute_exit, exit_trigger, trade, price, port_usd)
                    return

        # Scan for entry if we have empty slots
        open_trades = state_mgr.open_trades
        if len(open_trades) < config.MAX_OPEN_TRADES and not trade:
            raw_df = get_data(broker_binance.client, symbol, config.INTERVAL_PRIMARY, config.LOOKBACK)
            clean_df = drop_incomplete_candle(raw_df)
            df = add_indicators(clean_df)
            
            if df is None or len(df) < 30:
                return
                
            regime = detect_regime(df)
            if regime == "BLACK_SWAN":
                return
                
            from orderflow_engine import orderflow_engine
            orderflow_snapshot = orderflow_engine.get_orderflow_snapshot(broker_binance.client, symbol)
            
            signal_result = get_signal(df, regime, broker_binance.client, symbol, orderflow=orderflow_snapshot)
            
            # Determine MTF and action for UI
            action = "WAITING"
            mtf = "N/A"
            
            reason = "Confluence Check"
            
            if signal_result["signal"] == "BUY" and signal_result["score"] >= config.MIN_CONFLUENCE_SCORE:
                mtf = multi_timeframe_gate(broker_binance.client, symbol)
                if mtf == "CONFIRMED_BUY" or mtf == "MIXED":
                    action = "EXECUTING_BUY"
                else:
                    action = "SKIPPED_MTF"
                    reason = "mtf_direction_conflict"
            elif signal_result["signal"] == "SELL" and signal_result["score"] >= config.MIN_CONFLUENCE_SCORE:
                mtf = multi_timeframe_gate(broker_binance.client, symbol)
                if mtf == "CONFIRMED_SELL" or mtf == "MIXED":
                    action = "EXECUTING_SHORT"
                else:
                    action = "SKIPPED_MTF"
                    reason = "mtf_direction_conflict"
                    
            state_mgr.record_analysis(
                symbol=symbol,
                regime=regime,
                mtf=mtf,
                signal=signal_result["signal"],
                score=signal_result["score"],
                action=action,
                reason=reason,
                breakdown=signal_result.get("breakdown", {})
            )
            
            # State updated via record_analysis
            
            with trade_lock:
                # TOCTOU Fix: Re-check available slots inside the lock!
                if len(state_mgr.open_trades) >= config.MAX_OPEN_TRADES:
                    return

                if action in ["EXECUTING_BUY", "EXECUTING_SHORT"]:
                    # Execute Trade
                    usdt_bal = balances.get('USDT', 0.0)
                    
                    # Daily Target Check (AED 20)
                    daily_aed = state_mgr.daily_stats.get("pnl_aed", 0.0)
                    if daily_aed >= 20.0:
                        logger.warning(f"Daily Target (20 AED) achieved ({daily_aed:.2f} AED). Halting entries.")
                        return

                    # Risk Gate: Capital Protection
                    from risk import CapitalProtectionTiers, adaptive_kelly_size, check_consecutive_losses
                    trade_history = state_mgr.state.get("trade_history", [])
                    
                    if check_consecutive_losses(trade_history):
                        logger.warning(f"Kill Switch Activated: Consecutive losses limit reached. Halting entries.")
                        return
                        
                    cap_prot = CapitalProtectionTiers(from_dict=state_mgr.state.get("capital_protection"))
                    cap_status, size_mult = cap_prot.evaluate(usdt_bal)
                    
                    if size_mult == 0.0:
                        logger.warning(f"Capital Protection halted entry for {symbol}: {cap_status}")
                        return
                    
                    # Compute stats_by_regime for regime-aware risk scaling
                    stats_by_regime = {}
                    for t in trade_history:
                        r = t.get("regime", "UNKNOWN")
                        if r not in stats_by_regime:
                            stats_by_regime[r] = {"trades": 0, "wins": 0}
                        stats_by_regime[r]["trades"] += 1
                        if float(t.get("pnl_usd", 0.0)) > 0:
                            stats_by_regime[r]["wins"] += 1
                    
                    # Risk Gate: Kelly Criterion
                    kelly_qty = adaptive_kelly_size(usdt_bal, price, trade_history, regime, stats_by_regime)
                    if not kelly_qty:
                        return
                        
                    qty = kelly_qty * 0.98 * size_mult

                    side = "BUY" if action == "EXECUTING_BUY" else "SHORT"
                    
                    # Fee Viability Check
                    from risk import compute_take_profit, check_fee_viability
                    projected_tp = compute_take_profit(price, df.iloc[-1]["ATR"], regime, side=side)
                    if not check_fee_viability(price, projected_tp, side):
                        return
                    
                    dec_id = make_decision_id(symbol, str(df.index[-1]), regime, side)
                    if idem_guard.is_duplicate(dec_id):
                        return
                    
                    # ─── Hard Pre-Trade Risk Engine (Deterministic O(1) Checks) ───
                    from pre_trade_risk import risk_gate
                    current_mid = orderflow_snapshot.get("mid_price", price)
                    prices_dict = {symbol: price}
                    equity_usd = portfolio_value_usd(balances, prices_dict)
                    daily_pnl = float(state_mgr.daily_stats.get("pnl_usd", 0.0))

                    approved, risk_reason = risk_gate.evaluate_order(
                        symbol=symbol,
                        side=side,
                        order_type="LIMIT",
                        price=price,
                        quantity=qty,
                        current_mid=current_mid,
                        daily_pnl_usd=daily_pnl,
                        portfolio_equity_usd=equity_usd,
                        open_trades=state_mgr.open_trades
                    )
                    if not approved:
                        logger.warning(f"PRE-TRADE RISK REJECT for {symbol} ({side}): {risk_reason}")
                        return
                        
                    if side == "BUY":
                        execution_pool.submit(_execute_buy, symbol, price, qty, regime, df.iloc[-1]["ATR"], dec_id, orderflow_snapshot, signal_result["score"], signal_result.get("breakdown", {}))
                    else:
                        execution_pool.submit(_execute_short, symbol, price, qty, regime, df.iloc[-1]["ATR"], dec_id, orderflow_snapshot, signal_result["score"], signal_result.get("breakdown", {}))
                
    except Exception as e:
        logger.error(f"Eval error for {symbol}: {e}")

# ═══════════════════════════════════════════════════════════════════
#  HELPER: Execute Exit (used by stop-loss, take-profit, signal sell)
# ═══════════════════════════════════════════════════════════════════

def _execute_exit(trigger: str, trade: Dict, price: float, port_usd: float,
                  score: int = 0, regime: str = "", dec_id: str = "") -> Any:
    """Execute a closing trade for any exit reason (stop-loss, trailing, signal, time)."""
    qty = trade["qty"]
    entry_price = trade["price"]
    symbol = trade["symbol"]
    side = trade.get("side", "LONG")
    
    if side == "SHORT":
        if config.PAPER_MODE:
            # Cannot actually buy back a short on spot unless we implemented margin repays
            logger.warning(f"Simulating short cover for {symbol} (Paper mode only)")
            order = {"paper": True, "qty": qty, "price": price, "status": "FILLED"}
        else:
            order = execute_buy_safe(symbol, qty)
    else:
        order = execute_sell_safe(symbol, qty)

    if order:
        actual_price = order.get("price", price)
        if side == "SHORT":
            pnl_pct_gross = (entry_price - actual_price) / entry_price * 100
            pnl_usd_gross = qty * (entry_price - actual_price)
        else:
            pnl_pct_gross = (actual_price - entry_price) / entry_price * 100
            pnl_usd_gross = qty * (actual_price - entry_price)
            
        # Deduct 0.2% round-trip exchange fees from the gross PNL
        fee_pct = 0.2
        fee_usd = qty * actual_price * 0.002
        
        pnl_pct = pnl_pct_gross - fee_pct
        pnl_usd = pnl_usd_gross - fee_usd

        state_mgr.record_trade_result(
            symbol=symbol,
            entry_price=entry_price, exit_price=actual_price,
            pnl_pct=pnl_pct, pnl_usd=pnl_usd,
            regime=trade.get("regime", regime),
            entry_time=trade.get("ts", trade.get("entry_time", "Unknown")),
            aed_rate=config.AED_USD_RATE,
        )
        state_mgr.remove_trade(symbol)

        # ─── Post-Mortem Autopsy & Self-Learning Adaptation ───
        try:
            from autopsy import autopsy_engine
            from learning_memory import learning_memory
            from obsidian_vault_mgr import vault_mgr
            
            entry_time = trade.get("ts", trade.get("entry_time", "Unknown"))
            orderflow = trade.get("orderflow", {})
            exit_data = {
                "exit_price": actual_price,
                "entry_price": entry_price,
                "pnl_pct": pnl_pct,
                "pnl_usd": pnl_usd,
                "pnl_aed": pnl_usd * config.AED_USD_RATE,
                "trigger": trigger,
                "exit_time": datetime.now(timezone.utc).isoformat()
            }
            
            autopsy_result = autopsy_engine.perform_autopsy(trade, exit_data, orderflow)
            
            # Record learning fingerprint
            regime_val = trade.get("regime", regime)
            trade_side = trade.get("side", "LONG")
            ofi_skew = orderflow.get("liquidity_skew", "NEUTRAL")
            cvd_delta = orderflow.get("cvd_delta", 0.0)
            cvd_aligned = (cvd_delta >= 0 if trade_side in ["BUY", "LONG"] else cvd_delta <= 0)
            
            fingerprint = learning_memory.make_fingerprint(regime_val, trade_side, ofi_skew, cvd_aligned)
            learning_memory.record_outcome(fingerprint, is_win=(pnl_usd > 0), pnl_usd=pnl_usd)
            
            # Archive Dossier to Obsidian Vault
            trade_id = str(entry_time).replace(":", "_").replace("-", "_")
            vault_mgr.record_trade_exit(trade_id, symbol, exit_data, autopsy_result)
        except Exception as e:
            logger.error(f"Error in autopsy/learning/vault recording: {e}")

        if dec_id:
            idem_guard.mark_executed(dec_id)

        audit(trigger, {
            "pnl_pct": round(pnl_pct, 3), "pnl_usd": round(pnl_usd, 4),
            "price": actual_price, "entry_price": entry_price,
            "regime": trade.get("regime", regime),
        })
        
        trade_logger.info(f"SELL EXECUTION ({trigger}) | QTY: {qty:.6f} | EXIT: ${actual_price:.2f} | ENTRY: ${entry_price:.2f} | PNL: {pnl_pct:+.2f}% (${pnl_usd:+.2f})")

        if trigger in ("STOP_LOSS", "TRAILING_STOP", "TAKE_PROFIT", "TIME_EXIT"):
            stop_price = trade.get("stop_loss", 0) if trigger == "STOP_LOSS" else \
                         trade.get("take_profit", 0) if trigger == "TAKE_PROFIT" else actual_price
            send_stop_loss_alert(trigger, actual_price, stop_price, pnl_pct, port_usd)
        else:
            send_trade_alert(
                f"SELL {'WIN' if pnl_pct > 0 else 'LOSS'}", qty, actual_price,
                trade.get("regime", regime), config.PAPER_MODE,
                confluence=score, pnl_pct=pnl_pct, portfolio_usd=port_usd,
            )

        exc_counter.record_success()
        _save_state()
        return {
            "action": trigger, "pnl_pct": round(pnl_pct, 3),
            "price": actual_price, "portfolio_aed": round(port_usd * config.AED_USD_RATE, 2),
        }
    else:
        audit(f"{trigger}_FAILED", {"price": price})
        _save_state()
        return {"action": f"{trigger}_FAILED"}


def _check_daily_summary(port_usd: float) -> None:
    """Send daily summary at the end of each trading day (first cycle after midnight UTC)."""
    stats = state_mgr.daily_stats
    now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if stats.get("date") and stats["date"] != now_date and stats.get("trades", 0) > 0:
        send_daily_summary(stats, port_usd)


def _execute_buy(symbol: str, price: float, qty: float, regime: str, current_atr: float, dec_id: str,
                 orderflow: Optional[Dict] = None, score: int = 0, breakdown: Optional[Dict] = None):
    from broker_binance import execute_buy_safe, init_futures_margin, place_bracket_orders
    from risk import compute_stop_loss, compute_take_profit
    from notifier import send_trade_alert
    from loggers import trade_logger
    from audit import audit
    import config

    init_futures_margin(symbol)
    order = execute_buy_safe(symbol, qty)
    if order:
        actual_qty = order.get("qty", qty)
        actual_price = order.get("price", price)
        
        stop_loss = compute_stop_loss(actual_price, current_atr, regime)
        take_profit = compute_take_profit(actual_price, current_atr, regime)

        # Secure natively on the exchange
        place_bracket_orders(symbol, "BUY", actual_qty, stop_loss, take_profit)

        state_mgr.add_open_trade(
            symbol=symbol, price=actual_price, qty=actual_qty, regime=regime,
            stop_loss=stop_loss, take_profit=take_profit,
            atr=current_atr, side="LONG",
            orderflow=orderflow, score=score, breakdown=breakdown
        )
        idem_guard.mark_executed(dec_id)
        audit("BUY", {
            "symbol": symbol, "qty": actual_qty, "price": actual_price, "regime": regime,
            "stop_loss": stop_loss, "take_profit": take_profit,
        })
        trade_logger.info(f"BUY EXECUTION | SYMBOL: {symbol} | QTY: {actual_qty:.6f} | PRICE: ${actual_price:.2f} | STOP: ${stop_loss:.2f}")
        send_trade_alert("BUY", actual_qty, actual_price, regime, config.PAPER_MODE)

        # Archive Entry to Obsidian Vault
        try:
            from obsidian_vault_mgr import vault_mgr
            vault_mgr.record_trade_entry(dec_id, {
                "symbol": symbol, "side": "BUY", "price": actual_price, "qty": actual_qty,
                "regime": regime, "stop_loss": stop_loss, "take_profit": take_profit,
                "atr": current_atr, "score": score, "breakdown": breakdown
            }, orderflow=orderflow)
        except Exception as e:
            logger.error(f"Error recording entry to Obsidian vault: {e}")


def _execute_short(symbol: str, price: float, qty: float, regime: str, current_atr: float, dec_id: str,
                  orderflow: Optional[Dict] = None, score: int = 0, breakdown: Optional[Dict] = None):
    from broker_binance import execute_sell_safe, init_futures_margin, place_bracket_orders
    from risk import compute_stop_loss, compute_take_profit
    from notifier import send_trade_alert
    from loggers import trade_logger
    from audit import audit
    import config

    init_futures_margin(symbol)
    order = execute_sell_safe(symbol, qty)
    if order:
        actual_qty = order.get("qty", qty)
        actual_price = order.get("price", price)
        
        stop_loss = compute_stop_loss(actual_price, current_atr, regime, side="SHORT")
        take_profit = compute_take_profit(actual_price, current_atr, regime, side="SHORT")

        # Secure natively on the exchange
        place_bracket_orders(symbol, "SHORT", actual_qty, stop_loss, take_profit)

        state_mgr.add_open_trade(
            symbol=symbol, price=actual_price, qty=actual_qty, regime=regime,
            stop_loss=stop_loss, take_profit=take_profit,
            atr=current_atr, side="SHORT",
            orderflow=orderflow, score=score, breakdown=breakdown
        )
        idem_guard.mark_executed(dec_id)
        audit("SHORT", {
            "symbol": symbol, "qty": actual_qty, "price": actual_price, "regime": regime,
            "stop_loss": stop_loss, "take_profit": take_profit,
        })
        trade_logger.info(f"SHORT EXECUTION | SYMBOL: {symbol} | QTY: {actual_qty:.6f} | PRICE: ${actual_price:.2f} | STOP: ${stop_loss:.2f}")
        send_trade_alert("SHORT", actual_qty, actual_price, regime, config.PAPER_MODE)

        # Archive Entry to Obsidian Vault
        try:
            from obsidian_vault_mgr import vault_mgr
            vault_mgr.record_trade_entry(dec_id, {
                "symbol": symbol, "side": "SHORT", "price": actual_price, "qty": actual_qty,
                "regime": regime, "stop_loss": stop_loss, "take_profit": take_profit,
                "atr": current_atr, "score": score, "breakdown": breakdown
            }, orderflow=orderflow)
        except Exception as e:
            logger.error(f"Error recording entry to Obsidian vault: {e}")


@app.route("/api/analytics")
@login_required
def get_analytics():
    try:
        history = state_mgr.get_trade_history(1000)
        
        # Apply Filters
        symbol_filter = request.args.get('symbol', 'ALL')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        
        filtered_history = []
        for t in history:
            sym = t.get("symbol", "UNKNOWN")
            if symbol_filter != 'ALL' and sym != symbol_filter:
                continue
                
            exit_time = t.get("exit_time", "")
            if start_date and exit_time and exit_time < start_date:
                continue
            if end_date and exit_time and exit_time > end_date:
                continue
                
            filtered_history.append(t)
            
        history = filtered_history
        
        # Build Equity Curve
        equity_curve = []
        cumulative_pnl = 0.0
        for t in history:
            cumulative_pnl += float(t.get("pnl_usd", 0.0))
            equity_curve.append({
                "time": t.get("exit_time", ""),
                "value": cumulative_pnl
            })
            
        # Build Win Rate by Regime & Symbol
        stats_by_regime = {}
        stats_by_symbol = {}
        
        for t in history:
            regime = t.get("regime", "UNKNOWN")
            symbol = t.get("symbol", "UNKNOWN")
            is_win = float(t.get("pnl_usd", 0.0)) > 0
            
            if regime not in stats_by_regime:
                stats_by_regime[regime] = {"trades": 0, "wins": 0, "pnl_usd": 0.0}
            stats_by_regime[regime]["trades"] += 1
            if is_win: stats_by_regime[regime]["wins"] += 1
            stats_by_regime[regime]["pnl_usd"] += float(t.get("pnl_usd", 0.0))
            
            if symbol not in stats_by_symbol:
                stats_by_symbol[symbol] = {"trades": 0, "wins": 0, "pnl_usd": 0.0}
            stats_by_symbol[symbol]["trades"] += 1
            if is_win: stats_by_symbol[symbol]["wins"] += 1
            stats_by_symbol[symbol]["pnl_usd"] += float(t.get("pnl_usd", 0.0))
            
        return jsonify({
            "status": "success",
            "data": {
                "equity_curve": equity_curve,
                "by_regime": stats_by_regime,
                "by_symbol": stats_by_symbol,
                "daily_stats": state_mgr.daily_stats
            }
        })
    except Exception as e:
        logger.error(f"Analytics error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    ws_engine.start()
    
    # Start Dead-Man's Switch Heartbeat Emitter Loop (every 500ms)
    def _heartbeat_loop():
        from dead_mans_switch import DeadMansSwitch
        dms = DeadMansSwitch()
        while True:
            try:
                active_syms = [t["symbol"] for t in state_mgr.open_trades]
                dms.emit_heartbeat(active_syms)
            except Exception:
                pass
            import time
            time.sleep(0.5)

    from threading import Thread
    heartbeat_thread = Thread(target=_heartbeat_loop, daemon=True)
    heartbeat_thread.start()
    
    # Start autonomous scanner loop
    scanner_thread = Thread(target=_scanner_loop, daemon=True)
    scanner_thread.start()
    
    # Run the Flask app in a separate thread so webview can take the main thread
    def start_server():
        app.run(host="127.0.0.1", port=8080, debug=False, use_reloader=False)
        
    t = threading.Thread(target=start_server)
    t.daemon = True
    import sys
    if "--headless" in sys.argv or os.environ.get("OUROBOROS_HEADLESS") == "1":
        logger.info("Ouroboros running in headless server mode on http://127.0.0.1:8080")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Ouroboros server shutting down...")
    else:
        # Launch pywebview window
        webview.create_window("Ouroboros Algo Trading", "http://127.0.0.1:8080")
        webview.start(private_mode=False)
