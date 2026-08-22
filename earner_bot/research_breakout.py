import pandas as pd
import numpy as np
from binance.client import Client
import config

client = Client(config.BINANCE_API_KEY, config.BINANCE_SECRET)
symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "AAVEUSDT", "UNIUSDT", "DEXEUSDT", "EULUSDT"]

print("Researching 4H Breakout Asymmetric Edge...")

total_trades = 0
total_wins = 0
total_pnl = 0

for sym in symbols:
    klines = client.get_historical_klines(sym, "5m", "30 days ago UTC")
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qa', 'nt', 'tbv', 'tqv', 'ignore'])
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    df = df.iloc[:-1]
    
    # 4H High is 48 candles
    df['rolling_high'] = df['high'].shift(1).rolling(48).max()
    
    # Breakout edge
    cond = (df['close'] > df['rolling_high'])
    
    entries = df.index[cond].tolist()
    
    # We can't enter multiple times on the same breakout, so we must skip forward if in trade
    i = 0
    while i < len(entries):
        idx = entries[i]
        if idx + 1 >= len(df): 
            break
            
        entry = df.loc[idx, 'close']
        
        # Asymmetric target: 1% risk, 3% reward
        tp = entry * 1.03
        sl = entry * 0.99
        
        future = df.loc[idx+1:idx+288] # look forward 24 hours
        hit_sl = future['low'] <= sl
        hit_tp = future['high'] >= tp
        
        exits = future[hit_sl | hit_tp]
        if not exits.empty:
            exit_idx = exits.index[0]
            if exits.loc[exit_idx, 'low'] <= sl:
                total_pnl -= 1.0 + 0.2
            else:
                total_pnl += 3.0 - 0.2
                total_wins += 1
            total_trades += 1
            
            # Skip entries that happen while we were in this trade
            while i < len(entries) and entries[i] <= exit_idx:
                i += 1
        else:
            i += 1

print(f"\n4H Breakout Asymmetric Edge:")
print(f"Trades: {total_trades}")
if total_trades > 0:
    print(f"Win Rate: {(total_wins/total_trades)*100:.1f}%")
print(f"Net PnL: {total_pnl:.2f}%")
