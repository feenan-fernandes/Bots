import json
import os

path = r"c:\Users\feena\OneDrive\Documents\Agentic\Ouroboros_bot\output\bot_state.json"
with open(path, 'r') as f:
    data = json.load(f)

changed = False
if "trade_history" in data:
    for entry in data["trade_history"]:
        if "symbol" not in entry:
            entry["symbol"] = "BTCUSDT"
            changed = True
        if "entry_time" not in entry:
            entry["entry_time"] = entry.get("exit_time", "")
            changed = True

if "open_trades" in data:
    for trade in data["open_trades"]:
        if "ts" in trade:
            trade["entry_time"] = trade.pop("ts")
            changed = True

if changed:
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
    print("Patched bot_state.json")
else:
    print("No changes needed for bot_state.json")
