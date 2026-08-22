
Ouroboros BOT 3.1 — COMPLETE STEP BY STEP CODE GUIDE
====================================================
Every file. Every line. Exactly where it goes.
====================================================


FOLDER STRUCTURE — CREATE THIS FIRST
=====================================

Run these commands in your terminal:

    mkdir Ouroboros-bot
    cd Ouroboros-bot
    python3 -m venv venv
    source venv/bin/activate          # Mac/Linux
    venv\\Scripts\\activate             # Windows
    pip install python-binance pandas ta requests flask gunicorn python-dotenv
    pip freeze > requirements.txt
    mkdir output


FILE 1 OF 11 — .env
====================
Location: Ouroboros-bot/.env
Purpose : Holds all secrets and settings. Never commit this file.

--- START OF FILE ---
BINANCE_API_KEY=paste_your_binance_api_key_here
BINANCE_SECRET=paste_your_binance_secret_here
TELEGRAM_BOT_TOKEN=paste_your_telegram_bot_token_here
TELEGRAM_CHAT_ID=paste_your_telegram_chat_id_here
PAPER_MODE=true
SYMBOL=BTCUSDT
INTERVAL_PRIMARY=1h
LOOKBACK=50
MAX_RISK_PCT=0.20
STOP_LOSS_PCT=0.015
TAKE_PROFIT_PCT=0.025
MAX_DAILY_LOSS_PCT=0.05
ATR_MULTIPLIER=3.5
--- END OF FILE ---

HOW TO GET TELEGRAM TOKEN AND CHAT ID:
  1. Open Telegram, search @BotFather
  2. Send /newbot, follow prompts, copy the token
  3. Message your new bot once
  4. Open this URL in browser: https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
  5. Find "chat": {"id": 123456789} — that number is your TELEGRAM_CHAT_ID

HOW TO GET BINANCE API KEY:
  1. Log into Binance
  2. Top right menu -> API Management
  3. Create new API key (label: Ouroboros-bot)
  4. Enable: Read Info + Spot Trading ONLY
  5. Disable: Futures, Margin, Withdrawals
  6. Copy API Key and Secret


FILE 2 OF 11 — config.py
=========================
Location: Ouroboros-bot/config.py
Purpose : Loads all environment variables into Python constants.

--- START OF FILE ---
import os
from dotenv import load_dotenv
load_dotenv()

BINANCE_API_KEY    = os.environ["BINANCE_API_KEY"]
BINANCE_SECRET     = os.environ["BINANCE_SECRET"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
PAPER_MODE         = os.getenv("PAPER_MODE", "true").lower() == "true"
SYMBOL             = os.getenv("SYMBOL", "BTCUSDT")
INTERVAL_PRIMARY   = os.getenv("INTERVAL_PRIMARY", "1h")
LOOKBACK           = int(os.getenv("LOOKBACK", 50))
MAX_RISK_PCT       = float(os.getenv("MAX_RISK_PCT", 0.20))
STOP_LOSS_PCT      = float(os.getenv("STOP_LOSS_PCT", 0.015))
TAKE_PROFIT_PCT    = float(os.getenv("TAKE_PROFIT_PCT", 0.025))
MAX_DAILY_LOSS_PCT = float(os.getenv("MAX_DAILY_LOSS_PCT", 0.05))
ATR_MULTIPLIER     = float(os.getenv("ATR_MULTIPLIER", 3.5))
--- END OF FILE ---

TEST IT:
    python3 -c "import config; print('API Key loaded:', bool(config.BINANCE_API_KEY))"
    Expected output: API Key loaded: True


FILE 3 OF 11 — audit.py
========================
Location: Ouroboros-bot/audit.py
Purpose : Logs every bot event to a file. Always build this first.

--- START OF FILE ---
import json, os
from datetime import datetime, timezone

AUDIT_FILE = "output/audit_log.jsonl"

def audit(event_type, data={}):
    entry = {
        "ts":    datetime.now(timezone.utc).isoformat(),
        "event": event_type,
    }
    entry.update(data)
    os.makedirs("output", exist_ok=True)
    with open(AUDIT_FILE, "a") as f:
        f.write(json.dumps(entry) + "\\n")
--- END OF FILE ---

TEST IT:
    python3 -c "from audit import audit; audit('TEST', {'msg': 'hello'}); print('Audit works')"
    Check output/audit_log.jsonl — should contain one line


FILE 4 OF 11 — notifier.py
===========================
Location: Ouroboros-bot/notifier.py
Purpose : Sends Telegram alerts. All bot events notify you here.

--- START OF FILE ---
import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from audit import audit

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "paste_your_telegram_bot_token_here":
        print(f"[NOTIFY SKIPPED] {message}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       f"Ouroboros 3.1\\n{message}",
        "parse_mode": "HTML"
    }
    try:
        r = requests.post(url, json=payload, timeout=5)
        r.raise_for_status()
    except Exception as e:
        audit("TELEGRAM_ERROR", {"error": str(e)})
        print(f"Telegram error: {e}")

def send_daily_summary(metrics):
    lines = ["Daily Summary"]
    for k, v in metrics.items():
        lines.append(f"  {k}: {v}")
    send_telegram("\\n".join(lines))
--- END OF FILE ---

TEST IT:
    python3 -c "from notifier import send_telegram; send_telegram('Bot is alive - test message')"
    You should receive a Telegram message


FILE 5 OF 11 — broker_binance.py
=================================
Location: Ouroboros-bot/broker_binance.py
Purpose : All exchange communication. Handles retries, filters, order confirmation.

--- START OF FILE ---
import math, time, logging
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from requests.exceptions import ConnectionError, Timeout
from config import BINANCE_API_KEY, BINANCE_SECRET, SYMBOL, PAPER_MODE

logger = logging.getLogger("Ouroboros.broker")
client = Client(BINANCE_API_KEY, BINANCE_SECRET)

RETRYABLE_CODES  = {-1001, -1007, -1021, -1099}
_filters_cache   = {}

def safe_api_call(fn, *args, retries=3, delay=2.0, **kwargs):
    for attempt in range(1, retries + 1):
        try:
            return fn(*args, **kwargs)
        except BinanceAPIException as e:
            if e.code in RETRYABLE_CODES and attempt < retries:
                logger.warning(f"Binance transient {e.code} retry {attempt}")
                time.sleep(delay * attempt)
            else:
                logger.error(f"Non-retryable Binance error: {e.code}")
                return None
        except (BinanceRequestException, ConnectionError, Timeout) as e:
            logger.warning(f"Network error attempt {attempt}: {e}")
            if attempt < retries:
                time.sleep(delay * attempt)
            else:
                return None
        except Exception as e:
            logger.error(f"Unexpected broker error: {e}")
            return None

def get_exchange_filters(symbol=SYMBOL):
    if symbol in _filters_cache:
        return _filters_cache[symbol]
    info    = client.get_symbol_info(symbol)
    filters = {f["filterType"]: f for f in info["filters"]}
    _filters_cache[symbol] = filters
    return filters

def quantize_qty(symbol, qty):
    step      = float(get_exchange_filters(symbol)["LOT_SIZE"]["stepSize"])
    precision = int(round(-math.log10(step)))
    return round(math.floor(qty / step) * step, precision)

def validate_notional(symbol, qty, price):
    f     = get_exchange_filters(symbol)
    min_n = float(f.get("NOTIONAL", f.get("MIN_NOTIONAL", {})).get("minNotional", 5.0))
    return qty * price >= min_n

def get_balances():
    account = client.get_account()
    return {b["asset"]: float(b["free"])
            for b in account["balances"] if float(b["free"]) > 0}

def verify_order_filled(symbol, order_id, timeout_sec=30):
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        order  = safe_api_call(client.get_order, symbol=symbol, orderId=order_id)
        if order is None:
            time.sleep(2)
            continue
        status = order.get("status")
        if status == "FILLED":
            return order
        if status in ("CANCELED", "REJECTED", "EXPIRED"):
            logger.error(f"Order {order_id} status={status}")
            return None
        time.sleep(2)
    logger.error(f"Order {order_id} not confirmed in {timeout_sec}s")
    return None

def place_market_buy_safe(symbol, qty):
    qty   = quantize_qty(symbol, qty)
    price = float(safe_api_call(client.get_symbol_ticker, symbol=symbol)["price"])
    if not validate_notional(symbol, qty, price):
        logger.warning("Order rejected: below min notional")
        return None
    if PAPER_MODE:
        logger.info(f"[PAPER] BUY {qty} {symbol} @ {price}")
        return {"paper": True, "qty": qty, "price": price, "status": "FILLED"}
    order = safe_api_call(client.order_market_buy, symbol=symbol, quantity=qty)
    if order is None:
        logger.error("BUY placement failed")
        return None
    confirmed = verify_order_filled(symbol, order["orderId"])
    if confirmed is None:
        raise RuntimeError("UNCONFIRMED_ORDER")
    return confirmed

def place_market_sell_safe(symbol, qty):
    qty   = quantize_qty(symbol, qty)
    price = float(safe_api_call(client.get_symbol_ticker, symbol=symbol)["price"])
    if PAPER_MODE:
        logger.info(f"[PAPER] SELL {qty} {symbol} @ {price}")
        return {"paper": True, "qty": qty, "price": price, "status": "FILLED"}
    order = safe_api_call(client.order_market_sell, symbol=symbol, quantity=qty)
    if order is None:
        logger.error("SELL placement failed")
        return None
    confirmed = verify_order_filled(symbol, order["orderId"])
    if confirmed is None:
        raise RuntimeError("UNCONFIRMED_ORDER")
    return confirmed
--- END OF FILE ---

TEST IT:
    python3 -c "from broker_binance import get_balances; print(get_balances())"
    Expected: dict showing your BTC, USDT balances


FILE 6 OF 11 — strategy.py
===========================
Location: Ouroboros-bot/strategy.py
Purpose : All technical indicators, regime detection, and trade signals.

--- START OF FILE ---
import pandas as pd
import ta
from binance.client import Client
from config import BINANCE_API_KEY, BINANCE_SECRET, ATR_MULTIPLIER

client = Client(BINANCE_API_KEY, BINANCE_SECRET)

def get_data(symbol, interval, lookback=120):
    candles = client.get_klines(symbol=symbol, interval=interval, limit=lookback)
    df = pd.DataFrame(candles, columns=[
        "time","open","high","low","close","volume",
        "ct","qa","nt","tbv","tqv","ignore"])
    for col in ["open","high","low","close","volume"]:
        df[col] = df[col].astype(float)
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    return df.set_index("time")

def add_indicators(df):
    bb = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
    df["BB_upper"] = bb.bollinger_hband()
    df["BB_lower"] = bb.bollinger_lband()
    df["BB_mid"]   = bb.bollinger_mavg()
    df["BB_width"] = (df["BB_upper"] - df["BB_lower"]) / df["BB_mid"]
    df["RSI"]      = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
    df["MA25"]     = df["close"].rolling(25).mean()
    df["std25"]    = df["close"].rolling(25).std()
    df["zscore"]   = (df["close"] - df["MA25"]) / df["std25"]
    adx            = ta.trend.ADXIndicator(df["high"], df["low"], df["close"], window=14)
    df["ADX"]      = adx.adx()
    macd           = ta.trend.MACD(df["close"])
    df["MACD"]        = macd.macd()
    df["MACD_signal"] = macd.macd_signal()
    stoch          = ta.momentum.StochasticOscillator(
                         df["high"], df["low"], df["close"], window=14, smooth_window=3)
    df["stoch_k"]  = stoch.stoch()
    df["stoch_d"]  = stoch.stoch_signal()
    df["ATR"]      = ta.volatility.AverageTrueRange(
                         df["high"], df["low"], df["close"], window=14).average_true_range()
    df["vol_ma"]   = df["volume"].rolling(20).mean()
    df["vol_spike"]= df["volume"] / df["vol_ma"]
    df["price_roc"]= df["close"].pct_change(3)
    return df.dropna()

def detect_regime(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if (last["high"] - last["low"]) > ATR_MULTIPLIER * last["ATR"]:
        return "BLACK_SWAN"
    price_drop = (prev["close"] - last["close"]) / prev["close"]
    if last["vol_spike"] > 2.0 and price_drop > 0.02:
        return "PANIC"
    bw_mean = df["BB_width"].rolling(20).mean().iloc[-1]
    if last["ADX"] > 25 and last["BB_width"] > bw_mean:
        return "TRENDING"
    return "RANGING"

def get_signal(df, regime):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    if regime == "TRENDING":
        buy  = (prev["MACD"] < prev["MACD_signal"] and
                last["MACD"] > last["MACD_signal"] and
                last["close"] > last["MA25"] and
                last["vol_spike"] > 1.2)
        sell = ((prev["MACD"] > prev["MACD_signal"] and
                 last["MACD"] < last["MACD_signal"]) or
                last["close"] < df["MA25"].rolling(7).mean().iloc[-1])
        if buy:  return "BUY"
        if sell: return "SELL"
    elif regime == "RANGING":
        buy  = (last["zscore"] < -1.8 and
                last["RSI"]    < 40   and
                last["close"] <= last["BB_lower"] * 1.005)
        sell = (last["zscore"] > 1.8  and
                last["RSI"]    > 60   and
                last["close"] >= last["BB_upper"] * 0.995)
        if buy:  return "BUY"
        if sell: return "SELL"
    elif regime == "PANIC":
        buy  = (last["stoch_k"] < 15 and
                prev["stoch_k"] < prev["stoch_d"] and
                last["stoch_k"] > last["stoch_d"])
        sell = last["stoch_k"] > 55
        if buy:  return "BUY"
        if sell: return "SELL"
    return "HOLD"

def multi_timeframe_gate(symbol):
    biases = []
    for iv in ("1h", "15m", "5m"):
        df   = add_indicators(get_data(symbol, iv, 50))
        last = df.iloc[-1]
        biases.append("BULL" if last["close"] > last["MA25"] else "BEAR")
    if all(b == "BULL" for b in biases): return "CONFIRMED_BUY"
    if all(b == "BEAR" for b in biases): return "CONFIRMED_SELL"
    return "MIXED"
--- END OF FILE ---

TEST IT:
    python3 -c "
from strategy import get_data, add_indicators, detect_regime, get_signal
df = add_indicators(get_data('BTCUSDT', '1h', 50))
regime = detect_regime(df)
signal = get_signal(df, regime)
print('Regime:', regime, '| Signal:', signal)
"
    Expected: Regime: RANGING | Signal: HOLD  (or similar)


FILE 7 OF 11 — risk.py
=======================
Location: Ouroboros-bot/risk.py
Purpose : Position sizing (Kelly Criterion) and 3-tier capital protection.

--- START OF FILE ---
from config import MAX_DAILY_LOSS_PCT

DEFAULT_WIN_RATE = 0.55
DEFAULT_AVG_WIN  = 0.025
DEFAULT_AVG_LOSS = 0.015

TIER_1_WARNING_PCT = 0.03
TIER_2_REDUCE_PCT  = 0.05
TIER_3_HALT_PCT    = 0.07
WEEKLY_HALT_PCT    = 0.10
MONTHLY_HALT_PCT   = 0.15

def kelly_position_size(btc_balance, btc_price,
                        win_rate=DEFAULT_WIN_RATE,
                        avg_win=DEFAULT_AVG_WIN,
                        avg_loss=DEFAULT_AVG_LOSS):
    if avg_loss == 0:
        return None
    R     = avg_win / avg_loss
    kelly = win_rate - (1 - win_rate) / R
    frac  = max(0.05, min(kelly / 2, 0.25))
    qty   = btc_balance * frac
    return qty if qty * btc_price >= 5.0 else None

class CapitalProtectionTiers:
    def __init__(self, start_usd):
        self.start       = start_usd
        self.week_start  = start_usd
        self.month_start = start_usd
        self.hwm         = start_usd
        self.floor       = start_usd * (1 - TIER_3_HALT_PCT)

    def update(self, current_usd):
        if current_usd > self.hwm:
            self.hwm  = current_usd
            gain      = self.hwm - self.start
            self.floor = self.start + gain * 0.50

    def evaluate(self, current_usd):
        daily   = (self.start - current_usd)       / max(self.start, 1e-9)
        weekly  = (self.week_start - current_usd)  / max(self.week_start, 1e-9)
        monthly = (self.month_start - current_usd) / max(self.month_start, 1e-9)
        if monthly >= MONTHLY_HALT_PCT:               return "HALT_MONTHLY",   0.0
        if weekly  >= WEEKLY_HALT_PCT:                return "HALT_WEEKLY",    0.0
        if daily   >= TIER_3_HALT_PCT or current_usd < self.floor:
                                                      return "HALT_DAILY",     0.0
        if daily   >= TIER_2_REDUCE_PCT:              return "NO_NEW_ENTRIES", 0.0
        if daily   >= TIER_1_WARNING_PCT:             return "REDUCED_SIZE",   0.5
        return "NORMAL", 1.0

    def reset_day(self, v):   self.start       = v
    def reset_week(self, v):  self.week_start  = v
    def reset_month(self, v): self.month_start = v
--- END OF FILE ---

TEST IT:
    python3 -c "
from risk import kelly_position_size, CapitalProtectionTiers
qty = kelly_position_size(0.00164494, 77000)
print('Kelly qty:', qty)
p = CapitalProtectionTiers(127.0)
tier, mult = p.evaluate(127.0)
print('Tier:', tier, 'Mult:', mult)
"
    Expected: Kelly qty: some small number | Tier: NORMAL Mult: 1.0


FILE 8 OF 11 — reconcile.py
============================
Location: Ouroboros-bot/reconcile.py
Purpose : Compares local bot state vs real Binance balance every cycle.

--- START OF FILE ---
import logging
from broker_binance import get_balances, safe_api_call, client
from audit import audit

logger = logging.getLogger("Ouroboros.reconcile")

def reconcile_position(state, symbol="BTCUSDT"):
    balances    = get_balances()
    actual_btc  = balances.get("BTC", 0.0)
    local_trade = state.get("open_trade")
    ticker      = safe_api_call(client.get_symbol_ticker, symbol=symbol)
    price       = float(ticker["price"]) if ticker else 77000.0
    min_btc     = 5.0 / price

    if local_trade is None and actual_btc > min_btc:
        logger.warning(f"Phantom BTC found: {actual_btc:.8f} — restoring state")
        audit("RECONCILE", {"case": "A_phantom", "actual_btc": actual_btc})
        state["open_trade"] = {"price": price, "qty": actual_btc, "regime": "UNKNOWN"}

    elif local_trade is not None and actual_btc < min_btc:
        logger.warning("Ghost position detected — clearing state")
        audit("RECONCILE", {"case": "B_ghost", "local_qty": local_trade.get("qty")})
        state["open_trade"] = None

    elif local_trade is not None:
        expected = local_trade["qty"]
        if abs(actual_btc - expected) / max(expected, 1e-9) > 0.05:
            logger.warning(f"Qty mismatch local={expected:.8f} actual={actual_btc:.8f}")
            audit("RECONCILE", {"case": "C_mismatch", "expected": expected, "actual": actual_btc})
            state["open_trade"]["qty"] = actual_btc

    return state
--- END OF FILE ---


FILE 9 OF 11 — idempotency.py
==============================
Location: Ouroboros-bot/idempotency.py
Purpose : Fingerprints every decision. Same candle/signal never fires twice.

--- START OF FILE ---
import hashlib
from datetime import datetime, timezone

_executed = {}

def make_decision_id(symbol, candle_ts, regime, signal):
    raw = f"{symbol}:{candle_ts}:{regime}:{signal}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def is_duplicate(decision_id):
    return decision_id in _executed

def mark_executed(decision_id):
    _executed[decision_id] = datetime.now(timezone.utc).isoformat()
    if len(_executed) > 100:
        del _executed[next(iter(_executed))]
--- END OF FILE ---


FILE 10 OF 11 — watchdog.py
============================
Location: Ouroboros-bot/watchdog.py
Purpose : Emergency close, halt flag system, consecutive exception counter.

--- START OF FILE ---
import os, logging
from audit import audit
from notifier import send_telegram

logger    = logging.getLogger("Ouroboros.watchdog")
HALT_FILE = "/tmp/Ouroboros_halt.flag"

def create_halt_flag(reason):
    with open(HALT_FILE, "w") as f:
        f.write(reason)
    logger.critical(f"HALT FLAG CREATED: {reason}")
    audit("HALT_FLAG", {"reason": reason})

def is_halted():
    return os.path.exists(HALT_FILE)

def clear_halt():
    if os.path.exists(HALT_FILE):
        os.remove(HALT_FILE)
    logger.info("Halt flag cleared")
    audit("HALT_CLEARED", {})

def emergency_close_all(state, symbol="BTCUSDT"):
    from broker_binance import get_balances, place_market_sell_safe
    balances = get_balances()
    btc      = balances.get("BTC", 0.0)
    min_btc  = 5.0 / 77000
    if btc > min_btc:
        logger.critical(f"Emergency closing {btc:.8f} BTC")
        result = place_market_sell_safe(symbol, btc)
        if result:
            send_telegram(f"EMERGENCY CLOSE: Sold {btc:.8f} BTC. Bot halted.")
            audit("EMERGENCY_CLOSE", {"btc_sold": btc, "result": "success"})
        else:
            send_telegram(f"EMERGENCY CLOSE FAILED — manual action needed. BTC={btc:.8f}")
            audit("EMERGENCY_CLOSE", {"btc_sold": btc, "result": "failed"})
    else:
        audit("EMERGENCY_CLOSE", {"btc_sold": 0, "result": "no_position"})
    state["open_trade"] = None
    create_halt_flag("EMERGENCY_CLOSE")

class ExceptionCounter:
    def __init__(self, threshold=3):
        self.count     = 0
        self.threshold = threshold

    def record_failure(self):
        self.count += 1
        return self.count >= self.threshold

    def record_success(self):
        self.count = 0
--- END OF FILE ---


FILE 11 OF 11 — app.py
=======================
Location: Ouroboros-bot/app.py
Purpose : Cloud Run HTTP entrypoint. Runs one decision cycle per call.
          Called every hour by Cloud Scheduler.

--- START OF FILE ---
import logging
from flask import Flask, jsonify
from datetime import datetime, timezone
from strategy import get_data, add_indicators, detect_regime, get_signal, multi_timeframe_gate
from risk import kelly_position_size, CapitalProtectionTiers
from broker_binance import get_balances, place_market_buy_safe, place_market_sell_safe
from broker_binance import safe_api_call, client
from reconcile import reconcile_position
from idempotency import make_decision_id, is_duplicate, mark_executed
from watchdog import is_halted, emergency_close_all, ExceptionCounter, create_halt_flag, clear_halt
from notifier import send_telegram, send_daily_summary
from audit import audit
from config import SYMBOL, INTERVAL_PRIMARY, LOOKBACK, PAPER_MODE

logging.basicConfig(level=logging.INFO)
app         = Flask(__name__)
state       = {"open_trade": None, "protection": None}
exc_counter = ExceptionCounter(threshold=3)

@app.route("/health")
def health():
    return jsonify({
        "status":     "halted" if is_halted() else "ok",
        "paper_mode": PAPER_MODE,
        "symbol":     SYMBOL,
        "ts":         datetime.now(timezone.utc).isoformat()
    })

@app.route("/emergency", methods=["POST"])
def emergency():
    emergency_close_all(state, SYMBOL)
    return jsonify({"status": "emergency_close_executed"})

@app.route("/resume", methods=["POST"])
def resume():
    clear_halt()
    send_telegram("Halt cleared by operator. Bot resuming next cycle.")
    return jsonify({"status": "resumed"})

@app.route("/run", methods=["POST", "GET"])
def run():
    try:
        audit("CYCLE_START", {"symbol": SYMBOL, "paper": PAPER_MODE})

        # GATE 0: halt flag
        if is_halted():
            return jsonify({"action": "HALTED", "reason": "halt_flag"})

        # GATE 1: fetch balances with retry
        balances = safe_api_call(get_balances)
        if balances is None:
            audit("SKIP", {"reason": "balance_fetch_failed"})
            return jsonify({"action": "SKIP", "reason": "balance_fetch_failed"})
        btc_bal  = balances.get("BTC", 0.0)
        usdt_bal = balances.get("USDT", 0.0)
        ticker   = safe_api_call(client.get_symbol_ticker, symbol=SYMBOL)
        if ticker is None:
            return jsonify({"action": "SKIP", "reason": "price_fetch_failed"})
        price    = float(ticker["price"])
        port_usd = btc_bal * price + usdt_bal

        # GATE 2: reconcile position vs exchange
        state.update(reconcile_position(state, SYMBOL))

        # GATE 3: capital protection tier
        if state["protection"] is None:
            state["protection"] = CapitalProtectionTiers(port_usd)
        state["protection"].update(port_usd)
        tier, size_mult = state["protection"].evaluate(port_usd)

        if tier.startswith("HALT"):
            send_telegram(f"Capital protection halt: {tier} | portfolio=${port_usd:.2f}")
            audit("HALT", {"tier": tier, "portfolio_usd": port_usd})
            if tier == "HALT_DAILY":
                emergency_close_all(state, SYMBOL)
            else:
                create_halt_flag(tier)
            return jsonify({"action": "HALTED", "tier": tier})

        if tier == "NO_NEW_ENTRIES":
            audit("SKIP", {"reason": tier})
            return jsonify({"action": "SKIP", "reason": tier})

        # GATE 4: market data and indicators
        df = add_indicators(get_data(SYMBOL, INTERVAL_PRIMARY, LOOKBACK))
        if df is None or len(df) < 30:
            return jsonify({"action": "SKIP", "reason": "insufficient_data"})
        regime = detect_regime(df)
        if regime == "BLACK_SWAN":
            send_telegram("Black Swan detected — standing down this candle")
            audit("SKIP", {"reason": "black_swan"})
            return jsonify({"action": "SKIP", "reason": "black_swan"})

        # GATE 5: multi-timeframe confluence
        mtf = multi_timeframe_gate(SYMBOL)
        if mtf == "MIXED":
            audit("SKIP", {"reason": "no_mtf_confluence", "regime": regime})
            return jsonify({"action": "SKIP", "reason": "no_mtf_confluence"})

        signal    = get_signal(df, regime)
        candle_ts = str(df.index[-1])

        # GATE 6: idempotency check
        dec_id = make_decision_id(SYMBOL, candle_ts, regime, signal)
        if is_duplicate(dec_id):
            audit("DUPLICATE_SKIP", {"decision_id": dec_id})
            return jsonify({"action": "SKIP", "reason": "duplicate"})

        # GATE 7: position sizing with tier multiplier
        base_qty = kelly_position_size(btc_bal, price)
        qty      = (base_qty * size_mult) if base_qty else None
        result   = {"signal": signal, "regime": regime, "price": price, "tier": tier}

        # GATE 8: execute with order confirmation
        if signal == "BUY" and qty and state["open_trade"] is None:
            order = place_market_buy_safe(SYMBOL, qty)
            if order:
                state["open_trade"] = {"price": price, "qty": qty, "regime": regime}
                mark_executed(dec_id)
                audit("BUY", {"qty": qty, "price": price, "regime": regime})
                send_telegram(f"BUY {qty:.6f} BTC | regime={regime} | price={price} | paper={PAPER_MODE}")
                result["action"] = "BUY"
            else:
                audit("BUY_FAILED", {"qty": qty, "price": price})
                result["action"] = "BUY_FAILED"

        elif signal == "SELL" and state["open_trade"]:
            t     = state["open_trade"]
            order = place_market_sell_safe(SYMBOL, t["qty"])
            if order:
                pnl = (price - t["price"]) / t["price"] * 100
                mark_executed(dec_id)
                audit("SELL", {"pnl_pct": round(pnl, 3), "price": price, "regime": regime})
                send_telegram(f"{'SELL WIN' if pnl > 0 else 'SELL LOSS'} | pnl={pnl:.2f}% | regime={regime} | paper={PAPER_MODE}")
                state["open_trade"] = None
                result["action"]    = "SELL"
                result["pnl_pct"]   = round(pnl, 3)
            else:
                audit("SELL_FAILED", {"price": price})
                result["action"] = "SELL_FAILED"
        else:
            mark_executed(dec_id)
            audit("HOLD", {"regime": regime, "signal": signal})
            result["action"] = "HOLD"

        exc_counter.record_success()
        return jsonify(result)

    except RuntimeError as e:
        if "UNCONFIRMED_ORDER" in str(e):
            emergency_close_all(state, SYMBOL)
            audit("EXCEPTION", {"error": "UNCONFIRMED_ORDER"})
            return jsonify({"error": "unconfirmed_order_halt"}), 500
        raise

    except Exception as e:
        halt = exc_counter.record_failure()
        audit("EXCEPTION", {"error": str(e)})
        send_telegram(f"Exception in /run: {str(e)}")
        if halt:
            emergency_close_all(state, SYMBOL)
            create_halt_flag("CONSECUTIVE_EXCEPTIONS")
            return jsonify({"error": "consecutive_failures_halt"}), 500
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
--- END OF FILE ---

TEST IT LOCALLY:
    python3 app.py
    In another terminal:
    curl http://localhost:8080/health
    curl -X POST http://localhost:8080/run
    Expected: JSON response with action, regime, signal, price


BACKTEST FILE — backtest.py
============================
Location: Ouroboros-bot/backtest.py
Purpose : Run 90-day historical simulation. Must pass gates before going live.

--- START OF FILE ---
import pandas as pd
import numpy as np
import json, os
from binance.client import Client
from strategy import add_indicators, detect_regime, get_signal
from config import BINANCE_API_KEY, BINANCE_SECRET, SYMBOL

client   = Client(BINANCE_API_KEY, BINANCE_SECRET)
FEE_RATE = 0.001
SLIPPAGE = 0.0002

def fetch_historical(symbol, interval, days=120):
    raw = client.get_historical_klines(symbol, interval, f"{days} days ago UTC")
    df  = pd.DataFrame(raw, columns=[
          "time","open","high","low","close","volume",
          "ct","qa","nt","tbv","tqv","ignore"])
    for col in ["open","high","low","close","volume"]:
        df[col] = df[col].astype(float)
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    return df.set_index("time")

def run_backtest(symbol=SYMBOL, days=120, eval_days=90, initial_usdt=127.0):
    df_raw  = fetch_historical(symbol, "1h", days)
    df      = add_indicators(df_raw.copy())
    cutoff  = df.index[-1] - pd.Timedelta(days=eval_days)
    df_eval = df[df.index >= cutoff]

    trades, equity = [], [initial_usdt]
    cash, position, entry_px = initial_usdt, 0.0, 0.0

    for i in range(1, len(df_eval)):
        window = df_eval.iloc[:i+1]
        if len(window) < 30: continue
        regime = detect_regime(window)
        if regime == "BLACK_SWAN": continue
        signal = get_signal(window, regime)
        price  = window.iloc[-1]["close"]

        if signal == "BUY" and position == 0 and cash >= 5.0:
            cost      = cash * 0.20
            effective = price * (1 + SLIPPAGE)
            fee       = cost * FEE_RATE
            position  = cost / effective
            entry_px  = effective
            cash     -= (cost + fee)

        elif signal == "SELL" and position > 0:
            effective = price * (1 - SLIPPAGE)
            proceeds  = position * effective
            fee       = proceeds * FEE_RATE
            pnl_pct   = (effective - entry_px) / entry_px
            pnl_usd   = proceeds - fee - position * entry_px
            cash     += (proceeds - fee)
            trades.append({
                "exit_time": str(window.index[-1]),
                "regime":    regime,
                "entry_px":  round(entry_px, 2),
                "exit_px":   round(effective, 2),
                "pnl_pct":   round(pnl_pct * 100, 3),
                "pnl_usd":   round(pnl_usd, 4)
            })
            position = 0.0
            entry_px = 0.0

        equity.append(cash + position * price)

    return pd.DataFrame(trades), equity

def compute_metrics(trades_df, equity):
    if len(trades_df) == 0:
        return {"error": "No trades executed"}
    wins   = trades_df[trades_df["pnl_pct"] > 0]
    losses = trades_df[trades_df["pnl_pct"] <= 0]
    hr     = np.diff(equity) / np.array(equity[:-1])
    sharpe = (np.mean(hr) / (np.std(hr) + 1e-9)) * np.sqrt(8760)
    peak   = equity[0]; max_dd = 0
    for e in equity:
        if e > peak: peak = e
        dd = (peak - e) / peak if peak > 0 else 0
        if dd > max_dd: max_dd = dd
    pf = (wins["pnl_usd"].sum() / abs(losses["pnl_usd"].sum())
          if len(losses) > 0 and losses["pnl_usd"].sum() != 0 else 9.99)
    return {
        "total_trades":      len(trades_df),
        "win_rate_pct":      round(len(wins) / len(trades_df) * 100, 1),
        "total_return_pct":  round((equity[-1] - equity[0]) / equity[0] * 100, 2),
        "sharpe_ratio":      round(sharpe, 3),
        "max_drawdown_pct":  round(max_dd * 100, 2),
        "profit_factor":     round(pf, 2)
    }

def run_and_save():
    os.makedirs("output", exist_ok=True)
    print("Running 90-day backtest — this takes 1-2 minutes...")
    trades, equity = run_backtest()
    metrics = compute_metrics(trades, equity)
    trades.to_csv("output/backtest_trades.csv", index=False)
    pd.DataFrame({"equity": equity}).to_csv("output/backtest_equity.csv", index=False)
    with open("output/backtest_summary.json", "w") as f:
        json.dump(metrics, f, indent=2)
    print("\\n=== BACKTEST RESULTS ===")
    for k, v in metrics.items():
        print(f"  {k:25s}: {v}")
    passed = (
        metrics.get("sharpe_ratio", 0)    >= 1.5 and
        metrics.get("max_drawdown_pct", 99) <= 7.0 and
        metrics.get("profit_factor", 0)   >= 1.2 and
        metrics.get("total_trades", 0)    >= 30
    )
    print("\\n" + ("GATE PASSED — safe to proceed to paper trading"
                   if passed else "GATE FAILED — do NOT go live yet"))
    return passed

if __name__ == "__main__":
    run_and_save()
--- END OF FILE ---

RUN BACKTEST:
    python3 backtest.py
    Check output/backtest_summary.json for results
    All 4 gates must pass before next phase


DOCKERFILE
==========
Location: Ouroboros-bot/Dockerfile
Purpose : Packages the bot for Cloud Run deployment.

--- START OF FILE ---
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "1", "--timeout", "300", "app:app"]
--- END OF FILE ---


GCP DEPLOYMENT COMMANDS
========================
Run these in Google Cloud Shell after all gates pass.

Step 1: Store secrets
    echo -n "YOUR_BINANCE_API_KEY"  | gcloud secrets create BINANCE_API_KEY --data-file=-
    echo -n "YOUR_BINANCE_SECRET"   | gcloud secrets create BINANCE_SECRET --data-file=-
    echo -n "YOUR_TELEGRAM_TOKEN"   | gcloud secrets create TELEGRAM_BOT_TOKEN --data-file=-
    echo -n "YOUR_CHAT_ID"          | gcloud secrets create TELEGRAM_CHAT_ID --data-file=-

Step 2: Deploy to Cloud Run
    PROJECT_ID=your-gcp-project-id
    REGION=me-central1
    SERVICE=Ouroboros-bot

    gcloud run deploy $SERVICE \\
      --source . \\
      --region $REGION \\
      --project $PROJECT_ID \\
      --no-allow-unauthenticated \\
      --min-instances 1 \\
      --max-instances 1 \\
      --concurrency 1 \\
      --timeout 300 \\
      --memory 512Mi \\
      --set-secrets "BINANCE_API_KEY=BINANCE_API_KEY:latest,BINANCE_SECRET=BINANCE_SECRET:latest,TELEGRAM_BOT_TOKEN=TELEGRAM_BOT_TOKEN:latest,TELEGRAM_CHAT_ID=TELEGRAM_CHAT_ID:latest" \\
      --set-env-vars "PAPER_MODE=true,SYMBOL=BTCUSDT,ENV=production"

Step 3: Set up Cloud Scheduler (runs every hour)
    CLOUD_RUN_URL=$(gcloud run services describe $SERVICE --region $REGION --format "value(status.url)")

    gcloud scheduler jobs create http Ouroboros-bot-hourly \\
      --schedule="0 * * * *" \\
      --uri="${CLOUD_RUN_URL}/run" \\
      --http-method=POST \\
      --oidc-service-account-email=YOUR_SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com \\
      --location=$REGION

Step 4: Test deployment
    curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \\
         ${CLOUD_RUN_URL}/health

Step 5: Go live (only after all gates pass)
    gcloud run services update $SERVICE \\
      --region $REGION \\
      --update-env-vars PAPER_MODE=false


BUILD ORDER SUMMARY
===================

Week 1 - Local Build and Test
  Day 1:  Create folder, venv, install packages
  Day 1:  Build .env, config.py, audit.py — test each
  Day 2:  Build notifier.py — test Telegram message arrives
  Day 2:  Build broker_binance.py — test get_balances()
  Day 3:  Build strategy.py — test regime and signal output
  Day 3:  Build risk.py — test Kelly and tier logic
  Day 4:  Build reconcile.py, idempotency.py, watchdog.py
  Day 5:  Build app.py — test /health and /run locally

Week 2 - Backtest
  Day 6:  Build backtest.py
  Day 7:  Run 90-day simulation — check all 4 gates pass
  Day 8:  If gates fail, review strategy thresholds and rerun
  Day 9:  Backtest gates pass confirmed

Week 3 - Paper Trading
  Day 10: Run app.py locally with PAPER_MODE=true
  Day 10: Verify Telegram alerts firing correctly
  Day 11+: Monitor 2 weeks — zero exceptions, zero duplicates

Week 4 - Cloud Run
  Day 18: Deploy to Cloud Run with PAPER_MODE=true
  Day 18: Set up Cloud Scheduler
  Day 19+: Monitor 1 week on GCP

Week 5 - Go Live
  Day 25: Confirm all gates and paper trading clean
  Day 25: Set PAPER_MODE=false
  Day 25: Monitor every Telegram alert for first 72 hours


VALIDATION GATES — DO NOT SKIP
================================

Gate                         Threshold
---                          ---------
Backtest Sharpe Ratio        >= 1.5
Backtest Max Drawdown        <= 7%
Backtest Profit Factor       >= 1.2
Total Trades in 90 days      >= 30
Paper trading period         >= 2 weeks
Zero duplicate orders        0
All Telegram alerts working  All 5 types
Daily balance matches BNB    Every day
"""
