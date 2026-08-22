import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add WebSocket start to boot
if "ws_engine" not in content:
    content = content.replace("from state import StateManager", "from state import StateManager\nfrom ws_engine import WebSocketEngine")
    content = content.replace("state_mgr    = StateManager()", "state_mgr    = StateManager()\nws_engine    = WebSocketEngine(state_mgr)")
    content = content.replace("app = Flask(__name__, static_folder='static')", "app = Flask(__name__, static_folder='static')\nws_engine.start()")

# 2. Rewrite /api/run_cycle to just return status or trigger background scan
new_run_cycle = """@app.route('/api/run_cycle', methods=['POST'])
@login_required
def run_cycle():
    \"\"\"
    Forces a background evaluation of top symbols. Doesn't block UI.
    \"\"\"
    from threading import Thread
    def background_scan():
        try:
            from market_scanner import get_top_symbols
            symbols = get_top_symbols(broker_binance.client, limit=10)
            for sym in symbols:
                _evaluate_symbol_async(sym)
        except Exception as e:
            logger.error(f"Background scan error: {e}")
            
    Thread(target=background_scan, daemon=True).start()
    return jsonify({"action": "BACKGROUND_SCAN_STARTED", "message": "Evaluating in background..."})

def _evaluate_symbol_async(symbol: str):
    \"\"\"
    Evaluates a single symbol. Triggered by WebSocket candle close or background scan.
    \"\"\"
    try:
        from data_fetcher import get_data
        from strategy import add_indicators, drop_incomplete_candle, detect_regime, get_signal
        from run_cycle import multi_timeframe_gate
        from risk import portfolio_value_usd
        
        # Check protection
        if is_halted():
            return
            
        balances = get_balances()
        if not balances:
            return
            
        price = get_current_price(symbol)
        if not price:
            return
            
        # Check if we already hold it
        trade = state_mgr.get_trade(symbol)
        if trade:
            state_mgr.update_highest_price(symbol, price)
            try:
                df_check = add_indicators(get_data(broker_binance.client, symbol, config.INTERVAL_PRIMARY, 50))
                current_atr = df_check.iloc[-1]["ATR"] if len(df_check) > 0 else price * 0.01
            except:
                current_atr = price * 0.01
            
            from risk import check_stop_take
            exit_trigger = check_stop_take(trade, price, current_atr)
            if exit_trigger:
                port_usd = portfolio_value_usd(balances.get(symbol.replace('USDT',''),0), balances.get('USDT',0), price)
                _execute_exit(exit_trigger, trade, price, port_usd)
                return

        # Scan for entry if we have empty slots (max 3)
        open_trades = state_mgr.open_trades
        if len(open_trades) < 3 and not trade:
            raw_df = get_data(broker_binance.client, symbol, config.INTERVAL_PRIMARY, config.LOOKBACK)
            clean_df = drop_incomplete_candle(raw_df)
            df = add_indicators(clean_df)
            
            if df is None or len(df) < 30:
                return
                
            regime = detect_regime(df)
            if regime == "BLACK_SWAN":
                return
                
            signal_result = get_signal(df, regime)
            if signal_result["signal"] == "BUY" and signal_result["score"] >= config.MIN_CONFLUENCE_SCORE:
                mtf = multi_timeframe_gate(broker_binance.client, symbol)
                if mtf == "CONFIRMED_BUY" or mtf == "MIXED":  # adjust logic as needed
                    # Execute Buy
                    usdt_bal = balances.get('USDT', 0.0)
                    slot_capital = usdt_bal / (3 - len(open_trades))
                    # Kelly sizing logic can go here
                    
                    dec_id = make_decision_id(symbol, str(df.index[-1]), regime, "BUY")
                    if idem_guard.is_duplicate(dec_id):
                        return
                        
                    # Calculate qty
                    qty = (slot_capital * 0.98) / price
                    
                    from run_cycle import _execute_buy
                    _execute_buy(symbol, price, qty, regime, df.iloc[-1]["ATR"], dec_id)
                    
    except Exception as e:
        logger.error(f"Eval error for {symbol}: {e}")
"""

lines = content.split('\n')
start_idx = -1
end_idx = -1
for i, line in enumerate(lines):
    if line.startswith('@app.route("/run", methods=["POST"])'):
        start_idx = i
    if line.startswith('# ═══════════════════════════════════════════════════════════════════'):
        if start_idx != -1 and i > start_idx:
            end_idx = i
            break

if start_idx != -1 and end_idx != -1:
    new_lines = lines[:start_idx] + [new_run_cycle] + lines[end_idx:]
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines))
    print("Successfully refactored app.py")
else:
    print(f"Could not find blocks. start: {start_idx}, end: {end_idx}")
