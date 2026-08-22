import pandas as pd
import numpy as np
from binance.client import Client
import config
from strategy import add_indicators

client = Client(config.BINANCE_API_KEY, config.BINANCE_SECRET)
symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "AAVEUSDT", "UNIUSDT", "DEXEUSDT", "EULUSDT"]

print("Researching Trend Pullback edge...")

total_trades = 0
total_wins = 0
total_pnl = 0

for sym in symbols:
    klines = client.get_historical_klines(sym, "5m", "30 days ago UTC")
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qa', 'nt', 'tbv', 'tqv', 'ignore'])
    for col in ['open', 'high', 'low', 'close', 'volume', 'tbv', 'tqv']:
        df[col] = df[col].astype(float)
    df = df.iloc[:-1]
    
    df = add_indicators(df)
    if df is None: continue
    
    # Trend Pullback Edge
    cond = (df['Kalman_Slope'] > 0.0005) & (df['close'] > df['Kalman']) & (df['low'] <= df['VWAP']) & (df['close'] > df['VWAP'])
    
    entries = df.index[cond].tolist()
    
    for idx in entries:
        if idx + 1 >= len(df): continue
        entry = df.loc[idx, 'close']
        
        tp = entry * 1.008
        sl = entry * 0.992
        
        future = df.loc[idx+1:idx+24]
        hit_sl = future['low'] <= sl
        hit_tp = future['high'] >= tp
        
        exits = future[hit_sl | hit_tp]
        if not exits.empty:
            exit_idx = exits.index[0]
            if exits.loc[exit_idx, 'low'] <= sl:
                total_pnl -= 0.8 + 0.2
            else:
                total_pnl += 0.8 - 0.2
                total_wins += 1
            total_trades += 1

print(f"\nTrend Pullback Edge:")
print(f"Trades: {total_trades}")
if total_trades > 0:
    print(f"Win Rate: {(total_wins/total_trades)*100:.1f}%")
print(f"Net PnL: {total_pnl:.2f}%")
