import json

hist = json.load(open('output/bot_state.json')).get('trade_history', [])
total = len(hist)
wins = sum(1 for t in hist if t.get('pnl_pct', 0) > 0)
total_pnl = sum(t.get('pnl_usd', 0) for t in hist)

print(f"Total trades: {total}")
print(f"Wins: {wins}  Losses: {total - wins}")
print(f"Win rate: {wins/total*100:.1f}%" if total else "N/A")
print(f"Total PNL: ${total_pnl:+.4f}")
print()
print("--- All trades ---")
for t in hist:
    sym = t.get('symbol', '???')
    side = t.get('side', 'LONG')
    pnl = t.get('pnl_pct', 0)
    usd = t.get('pnl_usd', 0)
    reason = t.get('exit_reason', '')
    marker = "WIN" if pnl > 0 else "LOSS"
    print(f"  {sym:14s} {side:5s}  {pnl:+.2f}%  ${usd:+.4f}  {reason}  [{marker}]")
