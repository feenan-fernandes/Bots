import json
import pandas as pd
from datetime import datetime, timezone, timedelta
from binance.client import Client
import config

print("Analyzing recent live trades to find true edge...")
hist = json.load(open('output/bot_state.json')).get('trade_history', [])
client = Client(config.BINANCE_API_KEY, config.BINANCE_SECRET)

print(f"Found {len(hist)} trades. Fetching 1m candle data for precision tracking...")

wins_old = 0
wins_new = 0
losses_new = 0
total = 0

for t in hist:
    sym = t.get('symbol')
    side = t.get('side', 'LONG')
    entry_price = t.get('entry_price')
    exit_price = t.get('exit_price')
    entry_time_str = t.get('entry_time')
    
    if not sym or not entry_price or not entry_time_str:
        continue
        
    try:
        # Parse entry time
        entry_time = datetime.fromisoformat(entry_time_str)
        # Fetch 24 hours of 1-minute candles starting from entry
        start_ts = int(entry_time.timestamp() * 1000)
        
        klines = client.get_historical_klines(sym, "1m", start_str=start_ts, limit=1440)
        if not klines:
            continue
            
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qa', 'nt', 'tbv', 'tqv', 'ignore'])
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col].astype(float)
            
        tp_dist = 0.006
        sl_dist = 0.007
        
        outcome = "OPEN"
        max_fav = 0
        max_adv = 0
        
        for _, row in df.iterrows():
            high = row['high']
            low = row['low']
            
            if side == "LONG":
                fav = (high - entry_price) / entry_price
                adv = (entry_price - low) / entry_price
            else:
                fav = (entry_price - low) / entry_price
                adv = (high - entry_price) / entry_price
                
            max_fav = max(max_fav, fav)
            max_adv = max(max_adv, adv)
            
            # Check chronological hits
            if adv >= sl_dist:
                outcome = "LOSS"
                break
            elif fav >= tp_dist:
                outcome = "WIN "
                break
                
        # Did it actually win originally?
        if t.get('pnl_pct', 0) > 0:
            wins_old += 1
            
        if outcome == "WIN ":
            wins_new += 1
        elif outcome == "LOSS":
            losses_new += 1
            
        total += 1
        print(f"{sym:10s} {side:5s} | Max Fav: {max_fav*100:>5.2f}% | Max Adv: {max_adv*100:>5.2f}% | NEW: {outcome} | OLD: {'WIN' if t.get('pnl_pct',0)>0 else 'LOSS'}")
        
    except Exception as e:
        print(f"Error on {sym}: {e}")

print("="*50)
print(f"Total Analyzed: {total}")
print(f"OLD WIN RATE: {(wins_old/total)*100:.1f}%")
print(f"NEW WIN RATE (estimated with 0.7% SL / 0.6% TP): {(wins_new/total)*100:.1f}%")
print("="*50)
