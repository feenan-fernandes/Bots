import os
import sys
import pandas as pd
from orderflow_engine import orderflow_engine
from autopsy import autopsy_engine
from learning_memory import learning_memory
from obsidian_vault_mgr import vault_mgr
from strategy import get_signal

print("=== 1. Testing Order Flow Engine ===")
dummy_client = None
snapshot = orderflow_engine.get_orderflow_snapshot(dummy_client, "BTCUSDT")
print("Snapshot keys:", list(snapshot.keys()))
ofi_val = snapshot["ofi"]
skew_val = snapshot["liquidity_skew"]
print(f"Default OFI: {ofi_val}, Skew: {skew_val}")

print("\n=== 2. Testing Autopsy Engine ===")
trade_data = {
    "symbol": "BTCUSDT",
    "side": "BUY",
    "price": 68000.0,
    "qty": 0.1,
    "regime": "TRENDING",
    "score": 85,
    "breakdown": {"volatility_breakout": 50, "cvd_alignment": 30}
}
exit_data = {
    "exit_price": 67200.0,
    "entry_price": 68000.0,
    "pnl_pct": -1.37,
    "pnl_usd": -80.0,
    "trigger": "STOP_LOSS"
}
of_adverse = {
    "ofi": -0.45,
    "spread_bps": 2.5,
    "cvd_delta": -12.5,
    "liquidity_skew": "HEAVY_ASK_PRESSURE"
}
autopsy_res = autopsy_engine.perform_autopsy(trade_data, exit_data, of_adverse)
m_id = autopsy_res["mistake_id"]
m_title = autopsy_res["mistake_title"]
print(f"Diagnosed: {m_id} ({m_title})")
assert m_id == "Mistake_CVD_Exhaustion_Trap", f"Unexpected autopsy: {autopsy_res}"

print("\n=== 3. Testing Learning Memory Penalty Matrix ===")
fp = learning_memory.make_fingerprint("TRENDING", "BUY", "HEAVY_ASK_PRESSURE", cvd_aligned=False)
print(f"Fingerprint: {fp}")
for _ in range(3):
    learning_memory.record_outcome(fp, is_win=False, pnl_usd=-50.0)
penalty = learning_memory.get_pattern_penalty(fp)
print(f"Dynamic Penalty after 3 losses: {penalty} points")
assert penalty < 0, f"Expected negative penalty, got {penalty}"

print("\n=== 4. Testing Obsidian Vault Generation ===")
test_id = "test_run_001"
entry_file = vault_mgr.record_trade_entry(test_id, trade_data, of_adverse)
print(f"Entry file created: {entry_file}")
assert os.path.exists(entry_file), "Entry file missing"

exit_file = vault_mgr.record_trade_exit(test_id, "BTCUSDT", exit_data, autopsy_res)
print(f"Exit file updated: {exit_file}")
assert os.path.exists(exit_file), "Exit file missing"

mistake_file = os.path.join(vault_mgr.mistakes_dir, "Mistake_CVD_Exhaustion_Trap.md")
print(f"Mistake taxonomy file created: {mistake_file}")
assert os.path.exists(mistake_file), "Mistake file missing"

print("\n=== 5. Testing Strategy Integration with Dynamic Penalty ===")
dates = pd.date_range("2026-01-01", periods=40, freq="4h")
df = pd.DataFrame({
    "close": [68000.0] * 40,
    "VWAP_Z": [2.0] * 40,
    "Kalman": [67500.0] * 40,
    "Kalman_Slope": [1.0] * 40,
    "delta": [5.0] * 40,
    "delta_MA": [3.0] * 40
}, index=dates)
sig = get_signal(df, "TRENDING", None, "BTCUSDT", orderflow=of_adverse)
sig_val = sig["signal"]
sig_score = sig["score"]
print(f"Signal: {sig_val}, Final Score: {sig_score}, Breakdown: {sig['breakdown']}")
assert "learning_memory_adj" in sig["breakdown"], "Learning memory adjustment missing from signal breakdown"

print("\n>>> ALL UNIT AND INTEGRATION TESTS PASSED SUCCESSFULLY! <<<")
