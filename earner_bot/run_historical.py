import pandas as pd
from strategy import add_indicators, detect_regime, get_signal
from broker_binance import client
from market_scanner import get_top_symbols
from tqdm import tqdm
from datetime import datetime
import config

def backtest(days):
    print(f'\nRunning {days}-day backtest...')
    symbols = get_top_symbols(client, limit=10) # Limit to 10 for speed
    
    total_trades = 0
    wins = 0
    pnl_sum = 0.0
    
    for sym in symbols:
        klines = client.get_historical_klines(sym, '4h', f'{days} days ago UTC')
        if not klines: continue
        
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qa', 'nt', 'tbv', 'tqv', 'ignore'])
        for col in ['open', 'high', 'low', 'close', 'volume', 'qa', 'tbv', 'tqv']:
            df[col] = df[col].astype(float)
        
        df = add_indicators(df)
        if df is None or len(df) < 50: continue
        
        in_trade = False
        entry_price = 0
        side = ""
        
        # We need to simulate stepping through time
        # This is slow, so we'll do a simplified vector-like approach or step through
        for i in range(50, len(df)):
            if in_trade:
                # Simplified exit logic
                p = df['close'].iloc[i]
                if side == 'BUY':
                    if p >= entry_price * 1.015: # TP
                        total_trades += 1; wins += 1; pnl_sum += 1.5; in_trade = False
                    elif p <= entry_price * 0.99: # SL
                        total_trades += 1; pnl_sum -= 1.0; in_trade = False
                elif side == 'SELL':
                    if p <= entry_price * 0.985: # TP
                        total_trades += 1; wins += 1; pnl_sum += 1.5; in_trade = False
                    elif p >= entry_price * 1.01: # SL
                        total_trades += 1; pnl_sum -= 1.0; in_trade = False
            else:
                window = df.iloc[i-30:i+1]
                r = detect_regime(window)
                sig = get_signal(window, r, client, sym)
                if sig['score'] >= 50:
                    in_trade = True
                    entry_price = window['close'].iloc[-1]
                    side = sig['signal']
                    
    wr = (wins / total_trades * 100) if total_trades > 0 else 0
    print(f'Trades: {total_trades}, Win Rate: {wr:.2f}%, Est PNL%: {pnl_sum:.2f}%')

backtest(30)
backtest(60)
backtest(90)
