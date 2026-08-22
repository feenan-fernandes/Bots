import os
import sys
import logging

logging.basicConfig(level=logging.DEBUG)

# Add current dir to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

try:
    from app import app, get_chart_data, state_mgr
    from broker_binance import init_client

    with app.app_context():
        # Setup context
        app.config['SERVER_NAME'] = 'localhost'
        with app.test_request_context('/api/chart'):
            init_client()
            state_mgr._load()
            
            # Since get_chart_data has @login_required, we need to bypass it or mock session.
            # We will just call the inner logic directly here.
            from strategy import get_data, add_indicators
            import config
            import pandas as pd
            from broker_binance import client
            
            symbol = state_mgr.last_analysis.get("symbol", "BTCUSDT")
            print(f"Fetching data for {symbol} with lookback 350 on interval {config.INTERVAL_PRIMARY}")
            
            raw_df = get_data(client, symbol, config.INTERVAL_PRIMARY, 350)
            print(f"Raw DF len: {len(raw_df)}")
            
            df = add_indicators(raw_df)
            print(f"DF with indicators len: {len(df)}")
            
            chart_data = []
            for idx, row in df.iterrows():
                chart_data.append({
                    "time": int(idx.timestamp()),
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "ma25": row["MA25"] if not pd.isna(row["MA25"]) else None
                })
            print(f"Generated chart_data len: {len(chart_data)}")
            if len(chart_data) > 0:
                print("First:", chart_data[0])
                print("Last:", chart_data[-1])
                times = [c["time"] for c in chart_data]
                dups = len(times) - len(set(times))
                print(f"Duplicates: {dups}")
            else:
                print("CHART DATA IS EMPTY!")

except Exception as e:
    import traceback
    traceback.print_exc()
