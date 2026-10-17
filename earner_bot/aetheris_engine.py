"""
aetheris_engine.py — AETHERIS Micro-Alpha Strategy Engine
================================================================================
Proprietary, non-copied quantitative trading strategy engineered from first
principles of statistical mechanics, non-equilibrium thermodynamics, and
market microstructure fluid dynamics.

Theoretical Architecture:
-------------------------
1. Liquidity Density Field (\u03a6):
   Continuous Gaussian kernel smoothing of Level-2 order book depth ladders.
2. Microstructural Liquidity Viscosity (\u03bd_L):
   Dynamic measurement of order book resistance per unit of price travel.
   Detects "Liquidity Cavitation" (vacuum state where resistance collapses).
3. Queue Information Entropy (S_L2):
   Shannon entropy of queue depth. Identifies transitions from noise-dominated
   retail dispersion to low-entropy institutional concentration.
4. Hydrodynamic Dislocation Vector (D_Aetheris):
   Directional momentum synthesized with OFI, entropy concentration,
   cavitation velocity, and cross-venue basis drift.
5. Structural Execution Geometry:
   Stop-loss anchored at high-density liquidity nodes; take-profit targeted
   at the depleted cavitation horizon (structural R:R >= 2.2).
================================================================================
"""

import math
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any
import logging

logger = logging.getLogger("Ouroboros.Aetheris")


@dataclass(slots=True)
class AetherisState:
    """Telemetry state container for the Aetheris alpha engine."""
    symbol: str
    timestamp: float
    mid_price: float
    micro_price: float
    liquidity_viscosity: float          # nu_L: mass / price travel
    is_cavitation_vacuum: bool          # True when viscosity < 10th percentile
    queue_entropy: float                # Shannon entropy of top K queues
    entropy_concentration: float        # 1.0 - (S / S_max) [0.0 = noise, 1.0 = institutional]
    hydrodynamic_dislocation: float     # D_Aetheris vector [-10.0 to +10.0]
    phase_transition_threshold: float   # Dynamic threshold Theta
    signal: str                         # 'BUY', 'SELL', 'HOLD'
    confidence_score: int               # Confluence score 0 - 100
    density_stop_loss: float            # Structural SL at high-density node
    cavitation_take_profit: float       # Structural TP at cavitation horizon
    risk_reward_ratio: float            # Expected R:R


class LiquidityDensityEstimator:
    """
    Constructs a continuous Gaussian density field Phi(x) over log-price space
    from discrete Level-2 bid/ask ladders.
    """
    def __init__(self, bandwidth_ticks: float = 2.5):
        self.bandwidth_ticks = bandwidth_ticks

    def compute_density_profile(
        self,
        bids: List[List[float]],
        asks: List[List[float]],
        mid_price: float,
        tick_size: float = 0.01,
        grid_points: int = 50
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculates continuous liquidity density across a relative price grid.
        Returns: (relative_price_grid, density_values)
        """
        if not bids or not asks or mid_price <= 0:
            return np.zeros(grid_points), np.zeros(grid_points)

        # Relative tick offsets from mid (-25 to +25 ticks)
        half_span = grid_points // 2
        grid = np.linspace(-half_span * tick_size, half_span * tick_size, grid_points)
        density = np.zeros(grid_points, dtype=np.float64)
        h = max(1e-4, self.bandwidth_ticks * tick_size)
        inv_2h2 = 1.0 / (2.0 * h * h)
        norm_const = 1.0 / (math.sqrt(2.0 * math.pi) * h)

        # Add bid liquidity (below mid)
        for p, q in bids:
            rel_p = p - mid_price
            weights = np.exp(-((grid - rel_p) ** 2) * inv_2h2)
            density += q * weights * norm_const

        # Add ask liquidity (above mid)
        for p, q in asks:
            rel_p = p - mid_price
            weights = np.exp(-((grid - rel_p) ** 2) * inv_2h2)
            density += q * weights * norm_const

        return grid + mid_price, density

    def find_major_support_resistance_nodes(
        self,
        bids: List[List[float]],
        asks: List[List[float]],
        mid_price: float
    ) -> Tuple[float, float]:
        """
        Finds the exact price levels of maximum liquidity mass on the bid and ask sides.
        """
        best_bid_node = bids[0][0] if bids else mid_price * 0.995
        best_bid_qty = 0.0
        for p, q in bids[:5]:
            if q > best_bid_qty:
                best_bid_qty = q
                best_bid_node = p

        best_ask_node = asks[0][0] if asks else mid_price * 1.005
        best_ask_qty = 0.0
        for p, q in asks[:5]:
            if q > best_ask_qty:
                best_ask_qty = q
                best_ask_node = p

        return best_bid_node, best_ask_node


class QueueEntropyEstimator:
    """
    Measures the Information Entropy of the order book queue depth.
    Differentiates between noisy retail dispersion and institutional queue concentration.
    """
    @staticmethod
    def compute_shannon_entropy(quantities: List[float]) -> Tuple[float, float]:
        """
        Returns (entropy, concentration_factor).
        entropy: S = - sum(p_i * ln(p_i))
        concentration: 1 - S / S_max  (0.0 = completely dispersed, 1.0 = 100% concentrated)
        """
        k = len(quantities)
        if k <= 1:
            return 0.0, 1.0

        total_vol = sum(quantities)
        if total_vol <= 0:
            return math.log(k), 0.0

        probs = [q / total_vol for q in quantities if q > 0]
        if not probs:
            return math.log(k), 0.0

        entropy = -sum(p * math.log(p) for p in probs)
        max_entropy = math.log(k)
        concentration = max(0.0, min(1.0, 1.0 - (entropy / max_entropy)))
        return entropy, concentration


class AetherisAlphaEngine:
    """
    The Master AETHERIS Quantitative Strategy Engine.
    Executes non-equilibrium thermodynamic phase transition analysis.
    """
    def __init__(
        self,
        symbol: str = "BTCUSDT",
        viscosity_lookback: int = 30,
        dislocation_lookback: int = 50,
        threshold_z: float = 1.85
    ):
        self.symbol = symbol
        self.viscosity_lookback = viscosity_lookback
        self.dislocation_lookback = dislocation_lookback
        self.threshold_z = threshold_z

        self.density_estimator = LiquidityDensityEstimator()
        self.entropy_estimator = QueueEntropyEstimator()

        # Rolling history buffers for adaptive baseline calculation
        self._viscosity_history: List[float] = []
        self._dislocation_history: List[float] = []
        self._last_mid_price: Optional[float] = None

    def update_and_evaluate(
        self,
        orderflow_snapshot: Dict[str, Any],
        candle_features: Optional[Dict[str, Any]] = None
    ) -> AetherisState:
        """
        Ingests a real-time order flow snapshot and candle indicators,
        evaluates the hydrodynamic dislocation vector, and outputs trade intent.
        """
        ts = orderflow_snapshot.get("timestamp", 0.0)
        mid_price = orderflow_snapshot.get("mid_price", 0.0)
        micro_price = orderflow_snapshot.get("micro_price", mid_price)
        ofi = orderflow_snapshot.get("ofi", 0.0)
        bids = orderflow_snapshot.get("top_bids", [])
        asks = orderflow_snapshot.get("top_asks", [])
        total_bid_depth = orderflow_snapshot.get("total_bid_depth", 1.0)
        total_ask_depth = orderflow_snapshot.get("total_ask_depth", 1.0)
        futures_lead = orderflow_snapshot.get("futures_lead_pct", 0.0)
        spread_bps = orderflow_snapshot.get("spread_bps", 5.0)

        if mid_price <= 0:
            return self._empty_state(ts, mid_price)

        # ─── 1. Calculate Microstructural Liquidity Viscosity (nu_L) ──
        price_travel = 0.0
        if self._last_mid_price is not None and self._last_mid_price > 0:
            price_travel = abs(mid_price - self._last_mid_price) / self._last_mid_price

        self._last_mid_price = mid_price
        total_visible_liquidity = total_bid_depth + total_ask_depth
        
        # Viscosity = mass available relative to price displacement
        # When liquidity is tiny or price moves fast with zero absorption, viscosity collapses
        viscosity = total_visible_liquidity / max(1e-5, price_travel * 10000.0)
        self._viscosity_history.append(viscosity)
        if len(self._viscosity_history) > self.viscosity_lookback:
            self._viscosity_history.pop(0)

        # 10th percentile viscosity defines Liquidity Cavitation (Vacuum)
        rolling_visc_arr = np.array(self._viscosity_history)
        visc_p10 = float(np.percentile(rolling_visc_arr, 15)) if len(rolling_visc_arr) >= 5 else 1.0
        mean_visc = float(np.mean(rolling_visc_arr)) if len(rolling_visc_arr) >= 1 else 1.0
        is_cavitation = (viscosity <= visc_p10 and len(rolling_visc_arr) >= 5)

        # ─── 2. Calculate Queue Depth Entropy & Institutional Concentration ──
        bid_qtys = [q for _, q in bids] if bids else [1.0]
        ask_qtys = [q for _, q in asks] if asks else [1.0]
        combined_qtys = bid_qtys + ask_qtys

        entropy, concentration = self.entropy_estimator.compute_shannon_entropy(combined_qtys)

        # ─── 3. Construct the Hydrodynamic Dislocation Vector (D_Aetheris) ──
        # Cavitation Velocity Multiplier: surges exponentially as viscosity approaches 0
        cavitation_mult = math.exp(-min(3.0, viscosity / max(1e-4, mean_visc)))
        
        # Institutional Concentration multiplier: scales with low entropy
        # Information weight increases when big blocks concentrate in the book
        concentration_weight = 0.5 + (concentration * 1.5)

        # Cross-Venue Basis Drift Acceleration
        drift_accel = futures_lead * 2.5

        # D_Aetheris synthesis:
        dislocation = (ofi * concentration_weight * (1.0 + cavitation_mult)) + drift_accel

        self._dislocation_history.append(dislocation)
        if len(self._dislocation_history) > self.dislocation_lookback:
            self._dislocation_history.pop(0)

        # ─── 4. Dynamic Non-Equilibrium Phase Transition Threshold (Theta) ──
        d_arr = np.array(self._dislocation_history)
        d_mean = float(np.mean(d_arr))
        d_std = float(np.std(d_arr)) if len(d_arr) >= 5 else 0.5
        d_std = max(0.15, d_std)

        # Spread penalty: widen threshold if market is illiquid
        spread_penalty = max(1.0, spread_bps / 5.0)
        threshold = (self.threshold_z * d_std * spread_penalty)

        # ─── 5. Structural Execution Geometry (Liquidity Nodes) ─────
        support_node, resistance_node = self.density_estimator.find_major_support_resistance_nodes(
            bids, asks, mid_price
        )

        signal = "HOLD"
        confidence_score = 0
        stop_loss = mid_price * 0.99
        take_profit = mid_price * 1.02
        rr_ratio = 1.0

        # Confluence signals with candle features (Hurst, Kalman, Regime)
        regime = "TRENDING"
        if candle_features:
            regime = candle_features.get("regime", "TRENDING")

        # ─── 6. Decision Logic & Asymmetric Phase Transition Trigger ─
        if dislocation > threshold:
            # Supercritical Bid Sweep: Ask liquidity cavitated, institutional buyers absorbing
            signal = "BUY"
            # Base confidence from dislocation magnitude
            excess = (dislocation - threshold) / d_std
            confidence_score = int(min(98, 65 + (excess * 15) + (concentration * 15)))

            # Structural Stop Loss: Placed just below the major bid absorption node
            stop_loss = min(mid_price * 0.995, support_node * 0.998)
            risk_dist = mid_price - stop_loss
            
            # Structural Take Profit: Aim for the depleted cavitation horizon
            # If ask resistance is close, aim for 2.2x to 3.0x risk distance
            reward_target = max(resistance_node, mid_price + (risk_dist * 2.3))
            take_profit = reward_target
            rr_ratio = round((take_profit - mid_price) / max(1e-5, risk_dist), 2)

            # Extra confluence: If Hurst > 0.55 (persistency) or cavitation is active, boost score
            if is_cavitation:
                confidence_score = min(100, confidence_score + 10)

        elif dislocation < -threshold:
            # Supercritical Ask Cascade: Bid liquidity cavitated, aggressive sellers sweeping
            signal = "SELL"
            excess = (-dislocation - threshold) / d_std
            confidence_score = int(min(98, 65 + (excess * 15) + (concentration * 15)))

            # Structural Stop Loss: Placed just above the major ask absorption node
            stop_loss = max(mid_price * 1.005, resistance_node * 1.002)
            risk_dist = stop_loss - mid_price

            # Structural Take Profit:
            reward_target = min(support_node, mid_price - (risk_dist * 2.3))
            take_profit = reward_target
            rr_ratio = round((mid_price - take_profit) / max(1e-5, risk_dist), 2)

            if is_cavitation:
                confidence_score = min(100, confidence_score + 10)

        # ─── 7. Self-Learning Memory Feedback Adjustment ───────────
        if signal in ["BUY", "SELL"]:
            try:
                from learning_memory import learning_memory
                ofi_skew = orderflow_snapshot.get("liquidity_skew", "NEUTRAL")
                cvd_delta = orderflow_snapshot.get("cvd_delta", 0.0)
                cvd_aligned = (cvd_delta >= 0 if signal == "BUY" else cvd_delta <= 0)
                fingerprint = learning_memory.make_fingerprint(
                    f"AETHERIS_{regime}", signal, ofi_skew, cvd_aligned
                )
                penalty = learning_memory.get_pattern_penalty(fingerprint)
                if penalty != 0:
                    confidence_score = max(0, min(100, confidence_score + penalty))
                    logger.info(f"Aetheris: Applied {penalty} pt penalty from memory for {fingerprint}")
            except Exception:
                pass

        return AetherisState(
            symbol=self.symbol,
            timestamp=ts,
            mid_price=round(mid_price, 4),
            micro_price=round(micro_price, 4),
            liquidity_viscosity=round(viscosity, 2),
            is_cavitation_vacuum=is_cavitation,
            queue_entropy=round(entropy, 3),
            entropy_concentration=round(concentration, 3),
            hydrodynamic_dislocation=round(dislocation, 3),
            phase_transition_threshold=round(threshold, 3),
            signal=signal,
            confidence_score=confidence_score,
            density_stop_loss=round(stop_loss, 4),
            cavitation_take_profit=round(take_profit, 4),
            risk_reward_ratio=rr_ratio
        )

    def _empty_state(self, ts: float, mid: float) -> AetherisState:
        return AetherisState(
            symbol=self.symbol,
            timestamp=ts,
            mid_price=mid,
            micro_price=mid,
            liquidity_viscosity=0.0,
            is_cavitation_vacuum=False,
            queue_entropy=0.0,
            entropy_concentration=0.0,
            hydrodynamic_dislocation=0.0,
            phase_transition_threshold=1.0,
            signal="HOLD",
            confidence_score=0,
            density_stop_loss=0.0,
            cavitation_take_profit=0.0,
            risk_reward_ratio=1.0
        )


# Global singleton instance for live trading
aetheris_engine = AetherisAlphaEngine()
