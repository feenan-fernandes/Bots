import pandas as pd
import numpy as np
from binance.client import Client
import config
from strategy import add_indicators

client = Client(config.BINANCE_API_KEY, config.BINANCE_SECRET)
symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT", "AAVEUSDT", "UNIUSDT", "DEXEUSDT", "EULUSDT"]

print("Researching high-frequency high-conviction edges...")

total_trades = 0
total_wins = 0
total_pnl = 0

for sym in symbols:
    klines = client.get_historical_klines(sym, "5m", "30 days ago UTC")
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qa', 'nt', 'tbv', 'tqv', 'ignore'])
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    df = df.iloc[:-1]
    
    # Calculate basics
    df['body'] = abs(df['close'] - df['open'])
    df['lower_wick'] = df[['open', 'close']].min(axis=1) - df['low']
    df['upper_wick'] = df['high'] - df[['open', 'close']].max(axis=1)
    df['vol_ma'] = df['volume'].rolling(20).mean()
    df['atr'] = df['high'].rolling(14).max() - df['low'].rolling(14).min() # proxy
    
    # Liquidation Sweep Edge: Huge lower wick, high volume
    cond = (df['lower_wick'] > df['body'] * 2) & (df['volume'] > df['vol_ma'] * 2) & (df['lower_wick'] > df['close'] * 0.003)
    
    entries = df.index[cond].tolist()
    
    for idx in entries:
        if idx + 1 >= len(df): continue
        entry = df.loc[idx, 'close']
        
        # Fixed aggressive targets: 0.8% TP, 0.4% SL (Risk 1:2)
        tp = entry * 1.008
        sl = entry * 0.996
        
        future = df.loc[idx+1:idx+24] # Look forward 2 hours
        hit_sl = future['low'] <= sl
        hit_tp = future['high'] >= tp
        
        exits = future[hit_sl | hit_tp]
        if not exits.empty:
            exit_idx = exits.index[0]
            if exits.loc[exit_idx, 'low'] <= sl:
                total_pnl -= 0.4 + 0.2 # 0.4% loss + 0.2% fee
            else:
                total_pnl += 0.8 - 0.2 # 0.8% win - 0.2% fee
                total_wins += 1
            total_trades += 1

print(f"\nLiquidation Sweep Edge:")
print(f"Trades: {total_trades}")
if total_trades > 0:
    print(f"Win Rate: {(total_wins/total_trades)*100:.1f}%")
print(f"Net PnL: {total_pnl:.2f}%")
