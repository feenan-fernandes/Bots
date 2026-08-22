import json
import time
import itertools
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from binance.client import Client
from concurrent.futures import ThreadPoolExecutor
import config
from strategy import add_indicators, detect_regime, get_signal

# ═══════════════════════════════════════════════════════════════════
#  DATA & PRECOMPUTATION
# ═══════════════════════════════════════════════════════════════════

def get_data(client, symbol, days=180):
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d %b %Y")
    import config
    klines = client.get_historical_klines(symbol, "4h", start)
    if not klines: return None
    
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'qa', 'nt', 'tbv', 'tqv', 'ignore'
    ])
    for col in ['open', 'high', 'low', 'close', 'volume', 'qa', 'tbv', 'tqv']:
        df[col] = df[col].astype(float)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    df.set_index('timestamp', inplace=True)
    return df.iloc[:-1]

def precompute_signals(df):
    """Computes indicators, regime, and all possible signals once for the whole DataFrame."""
    df = add_indicators(df)
    if df is None or len(df) < 200: return None
    
    # Pre-allocate arrays for speed
    regimes = np.full(len(df), "RANGING", dtype=object)
    signals = np.full(len(df), "HOLD", dtype=object)
    scores = np.zeros(len(df), dtype=int)
    
    # We only need to compute this once per symbol! This was the bottleneck.
    for i in range(200, len(df)):
        window = df.iloc[i-199:i+1]
        reg = detect_regime(window)
        regimes[i] = reg
        
        # Calculate max possible score for this bar using the full router
        if reg != "BLACK_SWAN":
            # get_signal returns dict with 'signal' and 'score'
            sig_data = get_signal(window, reg)
            signals[i] = sig_data['signal']
            scores[i] = sig_data['score']
            
    df['Regime'] = regimes
    df['Signal'] = signals
    df['Score'] = scores
    return df

# ═══════════════════════════════════════════════════════════════════
#  FAST SIMULATOR
# ═══════════════════════════════════════════════════════════════════

def simulate_trades(df, sl_mult, tp_mult, min_score):
    """Ultra-fast vectorized-ish trade simulator."""
    trades = []
    in_trade = False
    
    # Extract numpy arrays for lightning fast iteration
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    atrs = df['ATR'].values
    scores = df['Score'].values
    signals = df['Signal'].values
    regimes = df['Regime'].values
    
    entry_price = 0
    sl = 0
    tp = 0
    side = ""
    
    for i in range(200, len(df)):
        if in_trade:
            # Check exits
            hit_sl = False
            hit_tp = False
            
            if side == "LONG":
                if lows[i] <= sl: hit_sl = True
                if highs[i] >= tp: hit_tp = True
            else:
                if highs[i] >= sl: hit_sl = True
                if lows[i] <= tp: hit_tp = True
                
            if hit_sl or hit_tp:
                # If both hit in same 5m candle, assume SL hit first (pessimistic)
                exit_price = sl if hit_sl else tp
                if side == "LONG":
                    pnl = (exit_price - entry_price) / entry_price
                else:
                    pnl = (entry_price - exit_price) / entry_price
                    
                trades.append(pnl * 100 - 0.20) # Apply 0.2% fee
                in_trade = False
            continue
            
        # Check entries
        if scores[i] >= min_score and signals[i] in ["BUY", "SELL"] and atrs[i] > 0 and not np.isnan(atrs[i]):
            side = "LONG" if signals[i] == "BUY" else "SHORT"
            entry_price = closes[i]
            atr = atrs[i]
            reg = regimes[i]
            
            # SL calculation
            sm = sl_mult * (0.9 if reg == "RANGING" else 1.2 if reg == "TRENDING" else 1.0)
            sl_dist = max(atr * sm, entry_price * 0.0035)
            sl = entry_price - sl_dist if side == "LONG" else entry_price + sl_dist
            
            # TP calculation
            tm = tp_mult * (0.9 if reg == "RANGING" else 1.3 if reg == "TRENDING" else 1.0)
            tp_dist = max(atr * tm, entry_price * 0.0025)
            tp = entry_price + tp_dist if side == "LONG" else entry_price - tp_dist
            
            in_trade = True
            
    return trades

# ═══════════════════════════════════════════════════════════════════
#  MAIN EXECUTOR
# ═══════════════════════════════════════════════════════════════════

def main():
    import logging
    logging.disable(logging.CRITICAL)
    
    client = Client(config.BINANCE_API_KEY, config.BINANCE_SECRET)
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "AAVEUSDT", "UNIUSDT", "DEXEUSDT", "EULUSDT"]
    
    print("1. Downloading 30 days of data and pre-computing indicators (This is the heavy lifting)...")
    precomputed = {}
    
    def process_sym(sym):
        try:
            df = get_data(client, sym)
            return sym, precompute_signals(df)
        except Exception as e:
            return sym, None
            
    with ThreadPoolExecutor(max_workers=5) as executor:
        for sym, df in executor.map(process_sym, symbols):
            if df is not None:
                precomputed[sym] = df
                print(f"  {sym}: Ready ({len(df)} bars)")
                
    print("\n2. Executing Grid Search at warp speed...")
    
    sl_mults = [1.0, 2.0, 3.0]
    tp_mults = [2.0, 4.0, 6.0]
    min_scores = [70, 80]
    
    results = []
    
    for sl, tp, score in itertools.product(sl_mults, tp_mults, min_scores):
        all_trades = []
        for df in precomputed.values():
            trades = simulate_trades(df, sl, tp, score)
            all_trades.extend(trades)
            
        if all_trades:
            wins = sum(1 for pnl in all_trades if pnl > 0)
            win_rate = (wins / len(all_trades)) * 100
            net_pnl = sum(all_trades)
            results.append({
                "sl": sl, "tp": tp, "score": score,
                "trades": len(all_trades), "win_rate": win_rate, "pnl": net_pnl
            })
            
    # Rank results
    valid = [r for r in results if r['trades'] >= 20]
    valid.sort(key=lambda x: x['pnl'], reverse=True)
    
    print(f"\n{'='*70}")
    print(f"  TOP 15 PARAMETER SETS (from {len(valid)} valid combos)")
    print(f"{'='*70}")
    print(f"{'Rank':>4} | {'SL':>4} | {'TP':>4} | {'Score':>5} | {'Trades':>6} | {'Win Rate':>9} | {'Net PnL%':>9}")
    print(f"{'-'*70}")
    for i, r in enumerate(valid[:15]):
        print(f"{i+1:>4} | {r['sl']:>4.1f} | {r['tp']:>4.1f} | {r['score']:>5} | {r['trades']:>6} | {r['win_rate']:>8.1f}% | {r['pnl']:>8.2f}%")
        
if __name__ == "__main__":
    main()
