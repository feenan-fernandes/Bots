import os
import sys
import time
from pre_trade_risk import PreTradeRiskEngine, RiskLimits
from orderflow_engine import orderflow_engine
from dead_mans_switch import DeadMansSwitch

print("=======================================================")
print("  INSTITUTIONAL QUANT ARCHITECTURE TEST SUITE")
print("=======================================================")

# --- 1. Test Order Flow Microstructure (Micro-Price & Volatility) ---
print("\n[1] Testing Micro-Price & Realized Volatility Engine...")
class MockClient:
    def get_order_book(self, symbol, limit):
        return {
            "bids": [["68000.0", "15.5"], ["67990.0", "10.0"], ["67980.0", "8.0"]],
            "asks": [["68010.0", "2.0"], ["68020.0", "5.0"], ["68030.0", "6.0"]]
        }
    def get_recent_trades(self, symbol, limit):
        return [
            {"price": "68005.0", "qty": "0.5", "isBuyerMaker": False},
            {"price": "68008.0", "qty": "1.2", "isBuyerMaker": False},
            {"price": "68007.0", "qty": "0.3", "isBuyerMaker": True},
            {"price": "68009.0", "qty": "0.8", "isBuyerMaker": False},
            {"price": "68010.0", "qty": "2.0", "isBuyerMaker": False},
        ]
    def futures_symbol_ticker(self, symbol):
        return {"symbol": symbol, "price": "68018.0"}

snapshot = orderflow_engine.get_orderflow_snapshot(MockClient(), "BTCUSDT")
print(f"Mid Price: ${snapshot['mid_price']:.2f}")
print(f"Micro-Price (Weighted Mid): ${snapshot['micro_price']:.2f}")
print(f"Micro-Price Skew: {snapshot['micro_skew_bps']:+.2f} bps")
print(f"OFI Ratio: {snapshot['ofi']:+.3f} ({snapshot['liquidity_skew']})")
print(f"Realized Volatility: {snapshot.get('realized_vol_bps', 0.0)} bps")
print(f"Futures Lead: {snapshot['futures_lead_pct']:+.4f}%")

# Best Bid: 68000 (qty 15.5), Best Ask: 68010 (qty 2.0). 
# Heavy bid queue means micro-price should skew strongly toward the Ask!
assert snapshot['micro_price'] > snapshot['mid_price'], "Micro-price should skew towards ask when bids dominate"
assert snapshot['micro_skew_bps'] > 0, "Micro-skew should be positive"
print(">>> Micro-Price & Microstructure Verification Passed! <<<")

# --- 2. Test Deterministic Pre-Trade Risk Engine ---
print("\n[2] Testing Deterministic Pre-Trade Risk Gate (O(1) In-Memory Checks)...")
custom_limits = RiskLimits(
    max_daily_drawdown_pct=0.03,
    max_order_notional_usd=5000.0,
    max_portfolio_exposure_usd=20000.0,
    max_price_deviation_pct=0.015,
    max_orders_per_second=5
)
risk_engine = PreTradeRiskEngine(limits=custom_limits)

# Test 2.1: Valid Order
ok, reason = risk_engine.evaluate_order(
    symbol="BTCUSDT", side="BUY", order_type="LIMIT",
    price=68000.0, quantity=0.05,  # $3,400 notional
    current_mid=68005.0, daily_pnl_usd=-100.0, portfolio_equity_usd=10000.0,
    open_trades=[]
)
print(f"Valid Order: approved={ok}, reason={reason}")
assert ok, f"Valid order rejected: {reason}"

# Test 2.2: Circuit Breaker (-3% Drawdown)
ok, reason = risk_engine.evaluate_order(
    symbol="BTCUSDT", side="BUY", order_type="LIMIT",
    price=68000.0, quantity=0.05,
    current_mid=68005.0, daily_pnl_usd=-350.0, portfolio_equity_usd=10000.0, # -3.5% DD
    open_trades=[]
)
print(f"Circuit Breaker Test: approved={ok}, reason={reason}")
assert not ok and "CIRCUIT_BREAKER_ACTIVE" in reason, "Circuit breaker failed to trigger"

# Test 2.3: Max Single Order Notional ($5,000 cap)
ok, reason = risk_engine.evaluate_order(
    symbol="BTCUSDT", side="BUY", order_type="LIMIT",
    price=68000.0, quantity=0.10, # $6,800 notional > $5,000
    current_mid=68005.0, daily_pnl_usd=0.0, portfolio_equity_usd=10000.0,
    open_trades=[]
)
print(f"Max Notional Test: approved={ok}, reason={reason}")
assert not ok and "MAX_ORDER_NOTIONAL_BREACH" in reason, "Max order notional cap failed"

# Test 2.4: Fat-Finger Price Collar (>1.5% skew from mid)
ok, reason = risk_engine.evaluate_order(
    symbol="BTCUSDT", side="BUY", order_type="LIMIT",
    price=70000.0, quantity=0.05, # ~2.9% skew from mid 68000
    current_mid=68000.0, daily_pnl_usd=0.0, portfolio_equity_usd=10000.0,
    open_trades=[]
)
print(f"Fat-Finger Collar Test: approved={ok}, reason={reason}")
assert not ok and "FAT_FINGER_PRICE_COLLAR_BREACH" in reason, "Fat-finger collar failed"

# Test 2.5: Rate Limiter (Max 5/sec)
for _ in range(5):
    risk_engine.evaluate_order("BTCUSDT", "BUY", "LIMIT", 68000.0, 0.01, 68000.0, 0.0, 10000.0, [])
ok, reason = risk_engine.evaluate_order("BTCUSDT", "BUY", "LIMIT", 68000.0, 0.01, 68000.0, 0.0, 10000.0, [])
print(f"Rate Limiter Test: approved={ok}, reason={reason}")
assert not ok and "RATE_LIMIT_EXCEEDED" in reason, "Rate limiter failed"
print(">>> Pre-Trade Risk Engine Verification Passed! <<<")

# --- 3. Test External Dead-Man's Switch ---
print("\n[3] Testing Dead-Man's Switch Heartbeat Mechanism...")
test_heartbeat_path = os.path.join("output", "test_heartbeat.json")
dms = DeadMansSwitch(heartbeat_path=test_heartbeat_path, timeout_sec=1.5)

# Emit Heartbeat
dms.emit_heartbeat(["BTCUSDT", "ETHUSDT"])
assert os.path.exists(test_heartbeat_path), "Heartbeat file was not created"
print("Emitted heartbeat successfully. File exists and active.")

# Clean test file
if os.path.exists(test_heartbeat_path):
    os.remove(test_heartbeat_path)

print(">>> Dead-Man's Switch Verification Passed! <<<")

print("\n=======================================================")
print("  ALL INSTITUTIONAL PRODUCTION TESTS PASSED (100%)")
print("=======================================================")
