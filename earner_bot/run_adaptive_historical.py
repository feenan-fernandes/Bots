import pandas as pd
from strategy import add_indicators, detect_regime, get_signal
from broker_binance import client
from market_scanner import get_top_symbols
import config

def backtest(days):
    print(f'\nRunning {days}-day Option A adaptive backtest...')
    symbols = get_top_symbols(client, limit=10) # 10 coins for speed
    
    total_trades = 0
    wins = 0
    pnl_sum = 0.0
    
    all_data = {}
    for sym in symbols:
        klines = client.get_historical_klines(sym, '4h', f'{days} days ago UTC')
        if not klines: continue
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qa', 'nt', 'tbv', 'tqv', 'ignore'])
        for col in ['open', 'high', 'low', 'close', 'volume', 'qa', 'tbv', 'tqv']:
            df[col] = df[col].astype(float)
        df = add_indicators(df)
        if df is not None and len(df) >= 50:
            all_data[sym] = df
            
    if not all_data:
        print("No data.")
        return
        
    min_len = min([len(df) for df in all_data.values()])
    trade_history = []
    active_trades = {}
    
    for i in range(50, min_len):
        recent_trades = trade_history[-10:] if trade_history else []
        if recent_trades:
            w = [t for t in recent_trades if t > 0]
            recent_win_rate = len(w) / len(recent_trades)
        else:
            recent_win_rate = 0.5
            
        for sym, df in all_data.items():
            if sym in active_trades:
                entry_price = active_trades[sym]['entry_price']
                side = active_trades[sym]['side']
                p = df['close'].iloc[i]
                
                if side == 'BUY':
                    if p >= entry_price * 1.015:
                        total_trades += 1; wins += 1; pnl_sum += 1.5; trade_history.append(1.5); del active_trades[sym]
                    elif p <= entry_price * 0.99:
                        total_trades += 1; pnl_sum -= 1.0; trade_history.append(-1.0); del active_trades[sym]
                elif side == 'SELL':
                    if p <= entry_price * 0.985:
                        total_trades += 1; wins += 1; pnl_sum += 1.5; trade_history.append(1.5); del active_trades[sym]
                    elif p >= entry_price * 1.01:
                        total_trades += 1; pnl_sum -= 1.0; trade_history.append(-1.0); del active_trades[sym]
            else:
                window = df.iloc[i-30:i+1]
                r = detect_regime(window)
                
                dynamic_score = 50
                if recent_win_rate > 0.55:
                    dynamic_score = 40
                    
                sig = get_signal(window, r, client, sym, recent_win_rate=recent_win_rate)
                
                if sig['score'] >= dynamic_score:
                    active_trades[sym] = {
                        'entry_price': window['close'].iloc[-1],
                        'side': sig['signal']
                    }
                    
    wr = (wins / total_trades * 100) if total_trades > 0 else 0
    print(f'Trades: {total_trades}, Win Rate: {wr:.2f}%, Est PNL%: {pnl_sum:.2f}%')

backtest(7)
backtest(30)
backtest(60)
backtest(90)
