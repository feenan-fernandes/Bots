import os

# Fix app.py
app_path = 'app.py'
with open(app_path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    '"has_position":  state_mgr.open_trade is not None,',
    '"has_position":  len(state_mgr.open_trades) > 0,'
)

content = content.replace(
    'symbol = state_mgr.open_trade["symbol"] if state_mgr.open_trade else "BTCUSDT"',
    'symbol = state_mgr.open_trades[0]["symbol"] if len(state_mgr.open_trades) > 0 else "BTCUSDT"'
)

content = content.replace(
    '"open_trade":  state_mgr.open_trade,',
    '"open_trades":  state_mgr.open_trades,'
)

with open(app_path, 'w', encoding='utf-8') as f:
    f.write(content)

# Fix app.js
app_js_path = os.path.join('static', 'app.js')
with open(app_js_path, 'r', encoding='utf-8') as f:
    js_content = f.read()

js_content = js_content.replace(
    "await secureFetch('/run', { method: 'POST' });",
    "await secureFetch('/api/run_cycle', { method: 'POST' });"
)

with open(app_js_path, 'w', encoding='utf-8') as f:
    f.write(js_content)
