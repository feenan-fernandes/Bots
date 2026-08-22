import pandas as pd
import numpy as np
import itertools
from binance.client import Client
import config
from strategy import add_indicators

print("Running ultra-fast vectorized backtest engine...")

client = Client(config.BINANCE_API_KEY, config.BINANCE_SECRET)
symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "DEXEUSDT", "EULUSDT"]

# 1. Download & Prep Data
data = {}
for sym in symbols:
    print(f"Fetching 30 days of {sym}...")
    klines = client.get_historical_klines(sym, "5m", "30 days ago UTC")
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qa', 'nt', 'tbv', 'tqv', 'ignore'])
    for col in ['open', 'high', 'low', 'close', 'volume', 'qa', 'tbv', 'tqv']:
        df[col] = df[col].astype(float)
    df = df.iloc[:-1] # drop incomplete candle
    
    # Pre-compute indicators
    try:
        df = add_indicators(df)
        if df is not None and len(df) > 100:
            data[sym] = df
    except Exception as e:
        print(f"Error prepping {sym}: {e}")

# 2. Vectorized Grid Search
sl_mults = [0.8, 1.2, 2.0]
tp_mults = [1.2, 1.8, 2.5]
results = []

print(f"\nRunning grid search across {len(sl_mults)*len(tp_mults)} combinations...")

for sl_mult, tp_mult in itertools.product(sl_mults, tp_mults):
    total_trades = 0
    total_wins = 0
    total_pnl = 0.0
    
    for sym, df in data.items():
        # A simplified vectorized entry condition based on our alpha logic
        # For speed, we approximate the confluence score > 40 requirement
        
        # Condition: RSI < 30 and price crosses VWAP from below (oversold bounce)
        # OR RSI > 70 and price crosses VWAP from above (overbought rejection)
        
        if 'RSI' not in df.columns or 'VWAP' not in df.columns or 'ATR' not in df.columns:
            continue
            
        long_cond = (df['RSI'] < 40) & (df['close'] > df['VWAP']) & (df['open'] < df['VWAP'])
        short_cond = (df['RSI'] > 60) & (df['close'] < df['VWAP']) & (df['open'] > df['VWAP'])
        
        # Get entry indices
        long_entries = df.index[long_cond].tolist()
        short_entries = df.index[short_cond].tolist()
        
        # Evaluate longs
        for idx in long_entries:
            if idx + 1 >= len(df): continue
            
            entry_price = df.loc[idx, 'close']
            atr = df.loc[idx, 'ATR']
            if pd.isna(atr) or atr == 0: continue
            
            sl = entry_price - (atr * sl_mult)
            tp = entry_price + (atr * tp_mult)
            
            # Floor SL/TP to minimums to match real bot logic
            sl = min(sl, entry_price * (1 - 0.0035))
            tp = max(tp, entry_price * (1 + 0.0025))
            
            # Look forward to find exit
            future = df.loc[idx+1:]
            
            # Find first index where low <= sl OR high >= tp
            hit_sl = future['low'] <= sl
            hit_tp = future['high'] >= tp
            
            # Combine to find first exit
            exits = future[hit_sl | hit_tp]
            
            if not exits.empty:
                exit_idx = exits.index[0]
                exit_row = exits.loc[exit_idx]
                
                # If both hit in same candle, assume SL hit first (pessimistic)
                if exit_row['low'] <= sl:
                    total_pnl -= ((entry_price - sl) / entry_price) * 100
                    total_pnl -= 0.20 # fees
                else:
                    total_pnl += ((tp - entry_price) / entry_price) * 100
                    total_pnl -= 0.20 # fees
                    total_wins += 1
                total_trades += 1
                
        # Evaluate shorts
        for idx in short_entries:
            if idx + 1 >= len(df): continue
            
            entry_price = df.loc[idx, 'close']
            atr = df.loc[idx, 'ATR']
            if pd.isna(atr) or atr == 0: continue
            
            sl = entry_price + (atr * sl_mult)
            tp = entry_price - (atr * tp_mult)
            
            # Floor SL/TP to minimums
            sl = max(sl, entry_price * (1 + 0.0035))
            tp = min(tp, entry_price * (1 - 0.0025))
            
            # Look forward to find exit
            future = df.loc[idx+1:]
            hit_sl = future['high'] >= sl
            hit_tp = future['low'] <= tp
            
            exits = future[hit_sl | hit_tp]
            
            if not exits.empty:
                exit_idx = exits.index[0]
                exit_row = exits.loc[exit_idx]
                
                if exit_row['high'] >= sl:
                    total_pnl -= ((sl - entry_price) / entry_price) * 100
                    total_pnl -= 0.20 # fees
                else:
                    total_pnl += ((entry_price - tp) / entry_price) * 100
                    total_pnl -= 0.20 # fees
                    total_wins += 1
                total_trades += 1

    win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
    results.append({
        'sl_mult': sl_mult,
        'tp_mult': tp_mult,
        'trades': total_trades,
        'win_rate': win_rate,
        'pnl': total_pnl
    })

# 3. Print Results
results.sort(key=lambda x: x['pnl'], reverse=True)
print(f"\n{'='*70}")
print(f"{'SL Mult':>7} | {'TP Mult':>7} | {'Trades':>8} | {'Win Rate':>9} | {'Net PnL%':>9}")
print(f"{'-'*70}")
for r in results:
    print(f"{r['sl_mult']:>7.1f} | {r['tp_mult']:>7.1f} | {r['trades']:>8d} | {r['win_rate']:>8.1f}% | {r['pnl']:>8.2f}%")
print(f"{'='*70}")
