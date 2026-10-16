"""
pre_trade_risk.py — Deterministic In-Memory Pre-Trade Risk Engine
Performs strict O(1) synchronous pre-flight checks before any order touches the network.
Prevents fat-finger errors, excessive drawdown, rate-limit bans, and portfolio overexposure.
"""
import time
import logging
from dataclasses import dataclass, field
from typing import Tuple, List, Dict, Any, Optional

logger = logging.getLogger("Ouroboros.pre_trade_risk")

@dataclass
class RiskLimits:
    max_daily_drawdown_pct: float = 0.03      # 3.0% circuit breaker (Hard Halt)
    max_order_notional_usd: float = 5000.0    # Max single order ticket in USD
    max_portfolio_exposure_usd: float = 25000.0 # Max cumulative open position notional
    max_price_deviation_pct: float = 0.015    # Fat-finger collar (1.5% max distance from mid)
    max_orders_per_second: int = 20           # Leaky bucket rate-limit guard

class PreTradeRiskEngine:
    def __init__(self, limits: Optional[RiskLimits] = None):
        self.limits = limits or RiskLimits()
        self.orders_this_sec: int = 0
        self.last_sec_timestamp: int = 0

    def evaluate_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        price: float,
        quantity: float,
        current_mid: float,
        daily_pnl_usd: float,
        portfolio_equity_usd: float,
        open_trades: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[bool, str]:
        """
        Executes strict, deterministic O(1) in-memory checks.
        Returns (approved: bool, reason: str).
        """
        # 0. Basic Sanity Check
        if price <= 0 or quantity <= 0:
            return False, "INVALID_PRICE_OR_QUANTITY"

        order_notional = price * quantity
        now_sec = int(time.time())

        # 1. Daily Drawdown Circuit Breaker (Hard Halt)
        if portfolio_equity_usd > 0:
            drawdown_ratio = daily_pnl_usd / portfolio_equity_usd
            if drawdown_ratio <= -self.limits.max_daily_drawdown_pct:
                logger.critical(f"RISK REJECT: Daily drawdown {drawdown_ratio*100:.2f}% breached limit {-self.limits.max_daily_drawdown_pct*100:.2f}%")
                return False, f"CIRCUIT_BREAKER_ACTIVE: Daily drawdown {drawdown_ratio*100:.2f}% <= -{self.limits.max_daily_drawdown_pct*100:.1f}%"

        # 2. Max Single Order Notional
        if order_notional > self.limits.max_order_notional_usd:
            logger.warning(f"RISK REJECT: Order notional ${order_notional:.2f} exceeds cap ${self.limits.max_order_notional_usd:.2f}")
            return False, f"MAX_ORDER_NOTIONAL_BREACH: ${order_notional:.2f} > ${self.limits.max_order_notional_usd:.2f}"

        # 3. Post-Execution Total Exposure Cap
        active_trades = open_trades or []
        current_exposure = sum(float(t.get("price", 0.0)) * float(t.get("qty", 0.0)) for t in active_trades)
        projected_exposure = current_exposure + order_notional
        if projected_exposure > self.limits.max_portfolio_exposure_usd:
            logger.warning(f"RISK REJECT: Projected exposure ${projected_exposure:.2f} exceeds cap ${self.limits.max_portfolio_exposure_usd:.2f}")
            return False, f"PORTFOLIO_EXPOSURE_BREACH: ${projected_exposure:.2f} > ${self.limits.max_portfolio_exposure_usd:.2f}"

        # 4. Fat-Finger Price Collar Check
        if current_mid > 0:
            price_skew = abs(price - current_mid) / current_mid
            if price_skew > self.limits.max_price_deviation_pct:
                logger.warning(f"RISK REJECT: Price deviation {price_skew*100:.2f}% exceeds collar {self.limits.max_price_deviation_pct*100:.2f}%")
                return False, f"FAT_FINGER_PRICE_COLLAR_BREACH: Deviation {price_skew*100:.2f}% from mid ${current_mid:.2f}"

        # 5. Token Bucket Rate Limiter
        if now_sec == self.last_sec_timestamp:
            if self.orders_this_sec >= self.limits.max_orders_per_second:
                logger.warning(f"RISK REJECT: Rate limit hit ({self.orders_this_sec} orders/sec)")
                return False, f"RATE_LIMIT_EXCEEDED: {self.orders_this_sec} >= {self.limits.max_orders_per_second} req/sec"
            self.orders_this_sec += 1
        else:
            self.last_sec_timestamp = now_sec
            self.orders_this_sec = 1

        return True, "APPROVED"

# Global Pre-Trade Risk Engine instance
risk_gate = PreTradeRiskEngine()
