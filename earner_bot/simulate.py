import json
from datetime import datetime

with open('output/bot_state.json', 'r') as f:
    state = json.load(f)

history = state.get('trade_history', [])

recent_trades = history[-15:] if len(history) >= 15 else history

if not recent_trades:
    print('No trades to analyze.')
    exit()

wins = [t for t in recent_trades if float(t.get('pnl_usd', 0)) > 0]
losses = [t for t in recent_trades if float(t.get('pnl_usd', 0)) <= 0]

win_rate = len(wins) / len(recent_trades)
avg_win_usd = sum(float(t.get('pnl_usd', 0)) for t in wins) / len(wins) if wins else 0
avg_loss_usd = sum(float(t.get('pnl_usd', 0)) for t in losses) / len(losses) if losses else 0
avg_win_pct = sum(float(t.get('pnl_pct', 0)) for t in wins) / len(wins) if wins else 0
avg_loss_pct = sum(float(t.get('pnl_pct', 0)) for t in losses) / len(losses) if losses else 0

ev_usd = (win_rate * avg_win_usd) + ((1 - win_rate) * avg_loss_usd)
ev_pct = (win_rate * avg_win_pct) + ((1 - win_rate) * avg_loss_pct)

first_trade_ts = datetime.fromisoformat(recent_trades[0]['entry_time'])
last_trade_ts = datetime.fromisoformat(recent_trades[-1]['entry_time'])
delta_days = (last_trade_ts - first_trade_ts).total_seconds() / 86400
if delta_days < 1: delta_days = 1

trades_per_day = len(recent_trades) / delta_days
expected_trades_30d = trades_per_day * 30
proj_pnl_usd_30d = expected_trades_30d * ev_usd
proj_pnl_aed_30d = proj_pnl_usd_30d * 3.6725

print(f'Recent Trades Evaluated: {len(recent_trades)}')
print(f'Win Rate: {win_rate*100:.2f}%')
print(f'Avg Win: USD {avg_win_usd:.4f} ({avg_win_pct:.2f}%)')
print(f'Avg Loss: USD {avg_loss_usd:.4f} ({avg_loss_pct:.2f}%)')
print(f'Expected Value per Trade: USD {ev_usd:.4f}')
print(f'Trades per Day: {trades_per_day:.2f}')
print(f'Projected Trades (30d): {expected_trades_30d:.0f}')
print(f'Projected 30d PNL: USD {proj_pnl_usd_30d:.4f} (AED {proj_pnl_aed_30d:.2f})')
