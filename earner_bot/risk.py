"""
risk.py — Ouroboros Bot 3.1 Risk Management Engine
Adaptive Kelly position sizing, ATR-based dynamic stops, trailing stops,
time-based exits, AED portfolio tracking, and 3-tier capital protection.
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple, Any

from config import (
    MAX_DAILY_LOSS_PCT, MAX_CONSECUTIVE_LOSSES, MIN_REGIME_WIN_RATE, AED_USD_RATE,
    STOP_LOSS_ATR_MULT, TAKE_PROFIT_ATR_MULT,
    TRAILING_STOP_ACTIVATE_PCT, TRAILING_STOP_ATR_MULT,
    MAX_HOLD_HOURS,
)

logger = logging.getLogger("Ouroboros.risk")

# ─── Capital Protection Thresholds ────────────────────────────────
TIER_1_WARNING_PCT = 0.03
TIER_2_REDUCE_PCT  = 0.05
TIER_3_HALT_PCT    = MAX_DAILY_LOSS_PCT
WEEKLY_HALT_PCT    = 0.10
MONTHLY_HALT_PCT   = 0.15

# ─── Kelly Defaults (used when < 30 trades in history) ────────────
FALLBACK_WIN_RATE = 0.50
FALLBACK_AVG_WIN  = 0.020
FALLBACK_AVG_LOSS = 0.015
MIN_TRADES_FOR_ADAPTIVE = 30
ROUND_TRIP_FEE = 0.002  # 0.2% round-trip exchange fee penalty


# ═══════════════════════════════════════════════════════════════════
#  POSITION SIZING — Adaptive Kelly Criterion
# ═══════════════════════════════════════════════════════════════════

def compute_kelly_from_history(trade_history: List[Dict]) -> Tuple[float, float, float]:
    """
    Compute win_rate, avg_win, avg_loss from actual trade results.
    Analyzes only the last 10 trades to actively prioritize present market edge.
    """
    recent_trades = trade_history[-10:] if trade_history else []
    
    if len(recent_trades) < MIN_TRADES_FOR_ADAPTIVE:
        return FALLBACK_WIN_RATE, FALLBACK_AVG_WIN, FALLBACK_AVG_LOSS

    wins  = [t for t in recent_trades if t.get("pnl_pct", 0) > 0]
    losses = [t for t in recent_trades if t.get("pnl_pct", 0) <= 0]

    win_rate = len(wins) / len(recent_trades) if recent_trades else FALLBACK_WIN_RATE
    avg_win  = abs(sum(t["pnl_pct"] for t in wins) / len(wins)) if wins else FALLBACK_AVG_WIN
    avg_loss = abs(sum(t["pnl_pct"] for t in losses) / len(losses)) if losses else FALLBACK_AVG_LOSS

    # Convert from percentage to decimal and apply rigid FEE PENALTY
    avg_win  = (avg_win / 100.0) - ROUND_TRIP_FEE
    avg_loss = (avg_loss / 100.0) + ROUND_TRIP_FEE

    return win_rate, max(avg_win, 0.0001), max(avg_loss, 0.001)


def constrained_multi_asset_kelly(mu_vector: List[float], cov_matrix: List[List[float]], lambda_reg=0.02, kelly_fraction=0.25) -> List[float]:
    """
    Computes regularized multi-asset Kelly weights to prevent over-exposure 
    in highly correlated assets using Tikhonov (Ridge) Regularization.
    """
    import numpy as np
    from scipy.linalg import inv
    
    mu = np.array(mu_vector)
    cov = np.array(cov_matrix)
    n_assets = len(mu)
    
    # Apply Ridge Regularization (Covariance Shrinkage)
    regularized_cov = cov + (lambda_reg * np.eye(n_assets))
    
    try:
        inv_cov = inv(regularized_cov)
    except np.linalg.LinAlgError:
        inv_cov = np.linalg.pinv(regularized_cov)
        
    raw_kelly_weights = inv_cov.dot(mu)
    final_weights = kelly_fraction * raw_kelly_weights
    
    # Constrain weights between 0.05 and 0.25 to prevent leverage blowouts
    return np.clip(final_weights, 0.05, 0.25).tolist()

def check_consecutive_losses(trade_history: List[Dict]) -> bool:
    """
    Returns True if the last MAX_CONSECUTIVE_LOSSES trades were all losses
    AND the most recent loss was less than 30 minutes ago.
    
    This implements a cooldown instead of a permanent deadlock:
    after 3 consecutive losses, the bot pauses for 30 minutes to let
    the market settle, then resumes trading automatically.
    """
    if len(trade_history) < MAX_CONSECUTIVE_LOSSES:
        return False
        
    recent_trades = trade_history[-MAX_CONSECUTIVE_LOSSES:]
    losses = sum(1 for t in recent_trades if t.get("pnl_usd", 0.0) < 0)
    
    if losses < MAX_CONSECUTIVE_LOSSES:
        return False
    
    # Cooldown: only block if the last loss was within 30 minutes
    from datetime import datetime, timezone, timedelta
    last_exit = recent_trades[-1].get("exit_time", "")
    if last_exit:
        try:
            last_exit_dt = datetime.fromisoformat(last_exit)
            cooldown_end = last_exit_dt + timedelta(minutes=30)
            if datetime.now(timezone.utc) > cooldown_end:
                return False  # Cooldown expired, allow trading again
        except (ValueError, TypeError):
            pass
    
    return True

def adaptive_kelly_size(capital_balance: float, asset_price: float,
                        trade_history: List[Dict], current_regime: str = None, 
                        stats_by_regime: dict = None) -> Optional[float]:
    """
    Half-Kelly position sizing with adaptive parameters from trade history.
    Reduces sizing by 50% if the current regime has a low historical win rate.
    Returns quantity in BTC, or None if Kelly says don't trade.
    """
    win_rate, avg_win, avg_loss = compute_kelly_from_history(trade_history)

    if avg_loss == 0:
        return None

    R = avg_win / avg_loss
    kelly = win_rate - (1 - win_rate) / R

    # CRITICAL FIX: If Kelly is negative, expected value is negative — DON'T TRADE
    if kelly <= 0:
        logger.info("Kelly negative (%.4f) — no trade edge detected", kelly)
        return None

    # Half-Kelly with 10%–25% bounds (raised floor from 5% to 10% for small accounts)
    frac = max(0.10, min(kelly / 2, 0.25))
    
    # Regime-Aware Deleveraging
    if current_regime and stats_by_regime and current_regime in stats_by_regime:
        regime_stats = stats_by_regime[current_regime]
        if regime_stats["trades"] >= 5: # Need a minimum sample size per regime
            regime_win_rate = regime_stats["wins"] / regime_stats["trades"]
            if regime_win_rate < MIN_REGIME_WIN_RATE:
                logger.warning(f"Regime {current_regime} has poor win rate ({regime_win_rate:.1%}). Deleveraging 50%.")
                frac = frac * 0.5

    qty  = (capital_balance * frac) / asset_price

    # Smart minimum notional floor: ensure we always clear Binance's $10 minimum
    MIN_NOTIONAL = 11.0  # $11 to give buffer above Binance's $10 floor
    if qty * asset_price < MIN_NOTIONAL:
        # Bump to minimum if the account can afford it (up to 15% of capital)
        if capital_balance >= MIN_NOTIONAL and MIN_NOTIONAL / capital_balance <= 0.15:
            qty = MIN_NOTIONAL / asset_price
            logger.info("Kelly below min notional — bumped to $%.2f (%.1f%% of capital)", 
                       MIN_NOTIONAL, (MIN_NOTIONAL/capital_balance)*100)
        else:
            logger.info("Kelly qty %.8f below min notional and account too small to bump", qty)
            return None

    logger.info("Kelly: raw=%.4f half=%.4f frac=%.4f qty=%.8f (wr=%.2f R=%.2f)",
                kelly, kelly / 2, frac, qty, win_rate, R)
    return qty


# ═══════════════════════════════════════════════════════════════════
#  DYNAMIC STOP-LOSS / TAKE-PROFIT / TRAILING STOP
# ═══════════════════════════════════════════════════════════════════

def compute_stop_loss(entry_price: float, atr: float, regime: str, side: str = "LONG") -> float:
    """ATR-based stop-loss with minimum distance floor to survive market noise."""
    multiplier = STOP_LOSS_ATR_MULT
    if regime == "RANGING":
        multiplier *= 0.9  # Slightly tighter in ranges, but not suicidally tight
    elif regime == "TRENDING":
        multiplier *= 1.2  # Wider stops to let trends breathe
    elif regime == "PANIC":
        multiplier *= 1.5  # Wider stops during high volatility

    atr_distance = atr * multiplier
    
    # Floor: SL must be at least 0.35% from entry to survive normal market noise
    min_distance = entry_price * 0.0035
    distance = max(atr_distance, min_distance)

    if side == "SHORT":
        stop = entry_price + distance
    else:
        stop = entry_price - distance
        
    logger.info("Stop-loss computed: entry=%.2f ATR=%.2f mult=%.1f stop=%.2f side=%s dist=%.4f%%",
                entry_price, atr, multiplier, stop, side, (distance/entry_price)*100)
    return stop


def compute_take_profit(entry_price: float, atr: float, regime: str, side: str = "LONG") -> float:
    """ATR-based take-profit with minimum distance floor to ensure fee viability."""
    multiplier = TAKE_PROFIT_ATR_MULT
    if regime == "TRENDING":
        multiplier *= 1.3  # Let profits run in trends
    elif regime == "RANGING":
        multiplier *= 0.9  # Slightly tighter in ranges

    atr_distance = atr * multiplier
    
    # Floor: TP must be at least 0.25% from entry to always cover fees
    min_distance = entry_price * 0.0025
    distance = max(atr_distance, min_distance)

    if side == "SHORT":
        target = entry_price - distance
    else:
        target = entry_price + distance
        
    logger.info("Take-profit computed: entry=%.2f ATR=%.2f mult=%.1f target=%.2f side=%s dist=%.4f%%",
                entry_price, atr, multiplier, target, side, (distance/entry_price)*100)
    return target


def check_trailing_stop(entry_price: float, current_price: float,
                        highest_price: float, lowest_price: float, atr: float, side: str = "LONG") -> Tuple[bool, float]:
    """
    Trailing stop activates after price gains TRAILING_STOP_ACTIVATE_PCT
    above entry (or below for shorts), then trails by TRAILING_STOP_ATR_MULT * ATR.

    Returns (triggered: bool, trail_level: float).
    """
    if side == "SHORT":
        gain_pct = (entry_price - lowest_price) / entry_price
        
        if gain_pct < TRAILING_STOP_ACTIVATE_PCT:
            return False, 0.0
            
        trail_level = lowest_price + (atr * TRAILING_STOP_ATR_MULT)
        trail_level = min(trail_level, entry_price * 0.999)
        
        triggered = current_price >= trail_level
        return triggered, trail_level
    else:
        gain_pct = (highest_price - entry_price) / entry_price
    
        # Not yet activated
        if gain_pct < TRAILING_STOP_ACTIVATE_PCT:
            return False, 0.0
    
        trail_level = highest_price - (atr * TRAILING_STOP_ATR_MULT)
    
        # Trail level must be above entry to be a profit-protecting stop
        trail_level = max(trail_level, entry_price * 1.001)
    
        triggered = current_price <= trail_level
        return triggered, trail_level


def check_time_exit(entry_time_str: str) -> bool:
    """Check if position has exceeded maximum hold duration."""
    try:
        entry_time = datetime.fromisoformat(entry_time_str)
        elapsed = (datetime.now(timezone.utc) - entry_time).total_seconds() / 3600
        return elapsed >= MAX_HOLD_HOURS
    except (ValueError, TypeError):
        return False


def check_stop_take(trade: Dict, current_price: float, current_atr: float) -> Optional[str]:
    """
    Check all exit conditions for an open trade.
    Returns trigger name or None.
    Priority: STOP_LOSS > TRAILING_STOP > TIME_EXIT > TAKE_PROFIT
    """
    entry_price   = trade["price"]
    stop_loss     = trade.get("stop_loss", 0)
    take_profit   = trade.get("take_profit", float("inf") if trade.get("side", "LONG") == "LONG" else 0)
    highest_price = trade.get("highest_price", entry_price)
    lowest_price  = trade.get("lowest_price", entry_price)
    atr_at_entry  = trade.get("atr_at_entry", current_atr)
    side          = trade.get("side", "LONG")

    # 1. Hard stop-loss
    if side == "SHORT" and current_price >= stop_loss:
        return "STOP_LOSS"
    elif side == "LONG" and current_price <= stop_loss:
        return "STOP_LOSS"

    # 2. Trailing stop
    triggered, _ = check_trailing_stop(entry_price, current_price,
                                       highest_price, lowest_price, atr_at_entry, side)
    if triggered:
        return "TRAILING_STOP"

    # 3. Time-based exit
    if check_time_exit(trade.get("entry_time", "")):
        return "TIME_EXIT"

    # 4. Take-profit
    if side == "SHORT" and current_price <= take_profit:
        return "TAKE_PROFIT"
    elif side == "LONG" and current_price >= take_profit:
        return "TAKE_PROFIT"

    return None


def check_fee_viability(entry_price: float, take_profit: float, side: str, min_distance_pct: float = 0.0012) -> bool:
    """
    Validates if the target take_profit mathematically covers round-trip exchange fees.
    Defaults to 0.12% distance requirement to cover ~0.10% entry + 0.10% exit.
    (Binance spot fees are 0.1% each side, often less with BNB discount)
    """
    if entry_price <= 0:
        return False
    
    distance = abs(take_profit - entry_price) / entry_price
    if distance < min_distance_pct:
        logger.warning(f"Trade rejected: TP distance ({distance:.4%}) is below fee threshold ({min_distance_pct:.4%})")
        return False
    return True


# ═══════════════════════════════════════════════════════════════════
#  AED PORTFOLIO TRACKING
# ═══════════════════════════════════════════════════════════════════

def portfolio_value_usd(balances: dict, prices: dict) -> float:
    """Calculate total portfolio value in USD from all held assets."""
    total = balances.get('USDT', 0.0)
    for asset, qty in balances.items():
        if asset == 'USDT' or qty < 0.00001:  # skip dust
            continue
        symbol = f"{asset}USDT"
        price = prices.get(symbol, 0)
        total += qty * price
    return total


def portfolio_value_aed(balances: dict, prices: dict) -> float:
    """Calculate total portfolio value in AED."""
    return portfolio_value_usd(balances, prices) * AED_USD_RATE


# ═══════════════════════════════════════════════════════════════════
#  CAPITAL PROTECTION TIERS (with proper reset support)
# ═══════════════════════════════════════════════════════════════════

class CapitalProtectionTiers:
    """
    3-tier capital protection with daily/weekly/monthly circuit breakers.
    Serializable to/from dict for persistent state storage.
    """

    def __init__(self, start_usd: float = 0, from_dict: Optional[Dict] = None):
        if from_dict:
            self.start       = from_dict.get("start", start_usd)
            self.week_start  = from_dict.get("week_start", start_usd)
            self.month_start = from_dict.get("month_start", start_usd)
            self.hwm         = from_dict.get("hwm", start_usd)
            self.floor       = from_dict.get("floor", start_usd * (1 - TIER_3_HALT_PCT))
            self.last_reset_day   = from_dict.get("last_reset_day")
            self.last_reset_week  = from_dict.get("last_reset_week")
            self.last_reset_month = from_dict.get("last_reset_month")
        else:
            self.start       = start_usd
            self.week_start  = start_usd
            self.month_start = start_usd
            self.hwm         = start_usd
            self.floor       = start_usd * (1 - TIER_3_HALT_PCT)
            self.last_reset_day   = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            self.last_reset_week  = datetime.now(timezone.utc).strftime("%Y-W%W")
            self.last_reset_month = datetime.now(timezone.utc).strftime("%Y-%m")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for state persistence."""
        return {
            "start": self.start,
            "week_start": self.week_start,
            "month_start": self.month_start,
            "hwm": self.hwm,
            "floor": self.floor,
            "last_reset_day": self.last_reset_day,
            "last_reset_week": self.last_reset_week,
            "last_reset_month": self.last_reset_month,
        }

    def auto_reset(self, current_usd: float) -> None:
        """Automatically reset daily/weekly/monthly counters on schedule."""
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        week  = now.strftime("%Y-W%W")
        month = now.strftime("%Y-%m")

        if self.last_reset_day != today:
            logger.info("Daily reset: %.2f → %.2f", self.start, current_usd)
            self.start = current_usd
            self.last_reset_day = today

        if self.last_reset_week != week:
            logger.info("Weekly reset: %.2f → %.2f", self.week_start, current_usd)
            self.week_start = current_usd
            self.last_reset_week = week

        if self.last_reset_month != month:
            logger.info("Monthly reset: %.2f → %.2f", self.month_start, current_usd)
            self.month_start = current_usd
            self.last_reset_month = month

    def update(self, current_usd: float) -> None:
        """Update high-water mark and trailing floor."""
        if current_usd > self.hwm:
            self.hwm = current_usd
            gain = self.hwm - self.start
            self.floor = self.start + gain * 0.50

    def evaluate(self, current_usd: float) -> Tuple[str, float]:
        """
        Evaluate current capital status.
        Returns (tier_name, size_multiplier).
        """
        daily   = (self.start - current_usd)       / max(self.start, 1e-9)
        weekly  = (self.week_start - current_usd)  / max(self.week_start, 1e-9)
        monthly = (self.month_start - current_usd) / max(self.month_start, 1e-9)

        if monthly >= MONTHLY_HALT_PCT:
            return "HALT_MONTHLY", 0.0
        if weekly >= WEEKLY_HALT_PCT:
            return "HALT_WEEKLY", 0.0
        if daily >= TIER_3_HALT_PCT or current_usd < self.floor:
            return "HALT_DAILY", 0.0
        if daily >= TIER_2_REDUCE_PCT:
            return "NO_NEW_ENTRIES", 0.0
        if daily >= TIER_1_WARNING_PCT:
            return "REDUCED_SIZE", 0.5
        return "NORMAL", 1.0
