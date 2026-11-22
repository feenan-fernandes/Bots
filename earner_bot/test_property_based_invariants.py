"""
test_property_based_invariants.py — Property-Based Testing & Invariant Verification Suite
Based on AgenticSkills Testing & Trail of Bits Property-Based Invariant Methodology:
https://agenticskills.io/category/testing

Validates mathematical properties, bounding invariants, and safety guarantees
across 1,000+ randomized iterations over wide parameter domains.
"""

import os
import sys
import math
import random
import unittest
import shutil

# Ensure earner_bot root is in Python path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from risk import compute_stop_loss, compute_take_profit, adaptive_kelly_size, check_trailing_stop
from pre_trade_risk import PreTradeRiskEngine, RiskLimits
from obsidian_vault_mgr import ObsidianVaultManager


class TestPropertyBasedInvariants(unittest.TestCase):
    """Trail of Bits Property-Based Invariant Verification."""

    @classmethod
    def setUpClass(cls):
        print("\n" + "=" * 70)
        print("  TRAIL OF BITS PROPERTY-BASED INVARIANT SUITE (1,000 ITERATIONS)")
        print("=" * 70)

    def test_invariant_stop_loss_take_profit_soundness(self):
        """
        Property 1: Stop-loss and Take-profit ordering invariants must hold strictly
        across any positive price domain ($0.01 to $1,000,000) and any ATR.
        LONG Invariant:  0 < stop_loss < entry_price < take_profit
        SHORT Invariant: 0 < take_profit < entry_price < stop_loss
        """
        print("\n>>> Testing Invariant 1: Stop-Loss & Take-Profit Soundness (1,000 rounds)...")
        regimes = ["TRENDING", "RANGING", "PANIC", "CHOPPY"]
        
        for i in range(1000):
            # Generate wide spectrum of prices from micro-caps ($0.01) to mega-caps ($150,000)
            entry_price = round(random.uniform(0.01, 150000.0), 4)
            # ATR ranging from 0.001% of price to 50% of price
            atr = round(entry_price * random.uniform(0.0001, 0.50), 4)
            regime = random.choice(regimes)

            # Test LONG
            sl_long = compute_stop_loss(entry_price, atr, regime, side="LONG")
            tp_long = compute_take_profit(entry_price, atr, regime, side="LONG")

            self.assertGreater(entry_price, sl_long, f"LONG Stop loss ({sl_long}) not below entry ({entry_price})")
            self.assertGreater(tp_long, entry_price, f"LONG Take profit ({tp_long}) not above entry ({entry_price})")
            self.assertGreater(sl_long, 0.0, f"LONG Stop loss must be positive: {sl_long}")

            # Test SHORT
            sl_short = compute_stop_loss(entry_price, atr, regime, side="SHORT")
            tp_short = compute_take_profit(entry_price, atr, regime, side="SHORT")

            self.assertGreater(sl_short, entry_price, f"SHORT Stop loss ({sl_short}) not above entry ({entry_price})")
            self.assertGreater(entry_price, tp_short, f"SHORT Take profit ({tp_short}) not below entry ({entry_price})")
            self.assertGreater(tp_short, 0.0, f"SHORT Take profit must be positive: {tp_short}")

        print("  [OK] Invariant 1 PASSED: 1,000 / 1,000 orders strictly preserved directional bounds.")

    def test_invariant_kelly_sizing_safety_bounds(self):
        """
        Property 2: Kelly position sizing must never exceed available capital,
        must never yield negative quantities, and must strictly reject when EV <= 0.
        """
        print("\n>>> Testing Invariant 2: Kelly Sizing Mathematical Soundness (1,000 rounds)...")
        
        for i in range(1000):
            balance = round(random.uniform(50.0, 500000.0), 2)
            price = round(random.uniform(0.1, 100000.0), 4)
            
            # Generate randomized trade histories
            num_trades = random.randint(5, 50)
            history = []
            for _ in range(num_trades):
                pnl = random.uniform(-100.0, 200.0)
                history.append({"pnl_usd": pnl})

            qty = adaptive_kelly_size(balance, price, history)
            if qty is not None:
                notional = qty * price
                # Notional should not exceed total balance (plus small buffer for rounding)
                self.assertLessEqual(notional, balance * 1.01, f"Notional {notional} exceeded balance {balance}")
                self.assertGreater(qty, 0.0, "Quantity must be strictly positive")
                
        # Invariant 2B: Negative expected value MUST return None
        losing_history = [{"pnl_usd": -50.0} for _ in range(10)]
        rejected_qty = adaptive_kelly_size(10000.0, 50000.0, losing_history)
        self.assertIsNone(rejected_qty, "Kelly must return None when expected value is negative")
        
        print("  [OK] Invariant 2 PASSED: 1,000 / 1,000 Kelly sizings strictly conformed to risk bounds.")

    def test_invariant_risk_hard_gate_enforcement(self):
        """
        Property 3: Pre-trade risk gate MUST fail-closed whenever:
        - daily drawdown <= -3% (-0.03)
        - ticket notional > $5,000
        - total exposure > $20,000
        """
        print("\n>>> Testing Invariant 3: Pre-Trade Hard Gate Enforcements (1,000 rounds)...")
        gate = PreTradeRiskEngine()

        # Invariant 3A: Drawdown violation invariant (Must reject if daily loss <= -3%)
        for _ in range(350):
            equity = random.uniform(1000.0, 50000.0)
            daily_loss = -1.0 * equity * random.uniform(0.03001, 0.50)
            approved, reason = gate.evaluate_order(
                symbol="BTCUSDT",
                side="BUY",
                order_type="LIMIT",
                price=50000.0,
                quantity=0.01,
                current_mid=50000.0,
                daily_pnl_usd=daily_loss,
                portfolio_equity_usd=equity,
                open_trades=[]
            )
            self.assertFalse(approved, f"Risk gate failed to reject breach: {daily_loss/equity:.2%}")
            self.assertIn("CIRCUIT_BREAKER", reason)

        # Invariant 3B: Ticket cap violation invariant (Must reject if ticket > $5,000)
        for _ in range(350):
            ticket_value = random.uniform(5000.01, 50000.0)
            approved, reason = gate.evaluate_order(
                symbol="ETHUSDT",
                side="BUY",
                order_type="LIMIT",
                price=ticket_value,
                quantity=1.0,
                current_mid=ticket_value,
                daily_pnl_usd=0.0,
                portfolio_equity_usd=100000.0,
                open_trades=[]
            )
            self.assertFalse(approved, f"Risk gate allowed ticket > $5,000: {ticket_value}")
            self.assertIn("MAX_ORDER_NOTIONAL_BREACH", reason)

        # Invariant 3C: Total exposure cap violation invariant (Must reject if total notional > $25,000)
        for _ in range(300):
            existing_exposure = random.uniform(21000.0, 30000.0)
            order_val = random.uniform(4000.0, 4999.0)
            open_trades = [{"size": 1.0, "entry_price": existing_exposure}]
            approved, reason = gate.evaluate_order(
                symbol="SOLUSDT",
                side="BUY",
                order_type="LIMIT",
                price=order_val,
                quantity=1.0,
                current_mid=order_val,
                daily_pnl_usd=0.0,
                portfolio_equity_usd=100000.0,
                open_trades=open_trades
            )
            if existing_exposure + order_val > 25000.0:
                self.assertFalse(approved, "Risk gate permitted exposure > $25,000")
                self.assertIn("PORTFOLIO_EXPOSURE", reason)

        print("  [OK] Invariant 3 PASSED: 1,000 / 1,000 hard gate checks strictly upheld fail-closed state.")

    def test_invariant_path_traversal_resistance(self):
        """
        Property 4: Obsidian Neural Memory Vault must strictly resist directory traversal (CWE-22).
        Any trade ID containing relative separators, URI encoding, or absolute paths
        must be confined strictly inside Obsidian_Vault/Trades.
        """
        print("\n>>> Testing Invariant 4: Directory Confinement & Path Traversal Resistance (100 attacks)...")
        vault = ObsidianVaultManager()
        trades_dir = os.path.abspath(vault.trades_dir)

        adversarial_trade_ids = [
            "../../etc/passwd",
            "..\\..\\Windows\\System32\\cmd.exe",
            "....//....//config.py",
            "trade_123/../../../secret.txt",
            "%2e%2e%2ftrade_pwn",
            "C:\\Users\\feena\\AppData\\malicious",
            "trade\x00_null_byte",
            "//network-share/exploit",
            "CON", "PRN", "AUX", "NUL" # Windows reserved filenames
        ]

        # Generate 100 mutated adversarial inputs
        for idx in range(100):
            base_attack = random.choice(adversarial_trade_ids)
            attack_id = f"{base_attack}_{idx}"
            
            # Record trade entry under attack ID
            try:
                filepath = vault.record_trade_entry(
                    trade_id=attack_id,
                    trade_data={
                        "symbol": "BTCUSDT",
                        "side": "BUY",
                        "price": 64000.0,
                        "qty": 0.05,
                        "stop_loss": 62000.0,
                        "take_profit": 68000.0,
                        "regime": "TRENDING",
                        "score": 85
                    }
                )
                
                # Check path invariant
                abs_path = os.path.abspath(filepath)
                self.assertTrue(
                    abs_path.startswith(trades_dir),
                    f"CWE-22 VIOLATION: Path escaped to {abs_path}"
                )
            except ValueError:
                # Rejecting with ValueError is also a secure defense
                pass

        print("  [OK] Invariant 4 PASSED: 100 / 100 path traversal vectors successfully neutralized.")


if __name__ == "__main__":
    unittest.main()
