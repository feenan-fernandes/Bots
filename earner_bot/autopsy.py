"""
autopsy.py — Post-Mortem Trade Autopsy Engine for Ouroboros Bot
Analyzes every closed trade, diagnoses failure root causes,
and classifies mistakes into a structured taxonomy for continuous machine learning.
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("Ouroboros.autopsy")

MISTAKE_DEFINITIONS = {
    "Mistake_CVD_Exhaustion_Trap": {
        "title": "CVD Exhaustion / Passive Absorption Trap",
        "description": "Entered in direction of price movement, but aggressive taker volume (CVD) was diverging or decelerating. Institutional limit orders absorbed the move and reversed it."
    },
    "Mistake_Noise_Overtrading": {
        "title": "False Breakout in Choppy Noise Regime",
        "description": "Attempted trend-following breakout during a compressed NOISE regime without sufficient macro directional conviction."
    },
    "Mistake_Overextended_Entry": {
        "title": "Overextended Mean-Reversion Chase",
        "description": "Entered at extreme VWAP Z-score deviation (|Z| > 2.8) without waiting for localized stabilization or candlestick exhaustion confirmation."
    },
    "Mistake_Illiquid_Spread_Slippage": {
        "title": "High Spread & Slippage Friction",
        "description": "Trade suffered from wide bid-ask spread (> 12 bps) or thin orderbook depth at fill, causing negative expected value purely on transaction friction."
    },
    "Mistake_MTF_Conflict": {
        "title": "Macro Multi-Timeframe Trend Conflict",
        "description": "Trade direction directly contradicted the 1-Hour macro EMA alignment, getting crushed by higher-timeframe momentum."
    },
    "Mistake_Adverse_Volatility_Spike": {
        "title": "Adverse Volatility Expansion / Shakeout",
        "description": "Normal directional premise was interrupted by a sharp volatility surge or sudden market-wide candle spike."
    }
}

class TradeAutopsyEngine:
    def __init__(self):
        pass

    def perform_autopsy(self, trade_data: Dict[str, Any], exit_data: Dict[str, Any], orderflow: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Conducts post-mortem analysis on a closed trade.
        Returns diagnostic taxonomy, explanation, and adaptation guidance.
        """
        pnl_pct = float(exit_data.get("pnl_pct", 0.0))
        pnl_usd = float(exit_data.get("pnl_usd", 0.0))
        trigger = exit_data.get("trigger", "UNKNOWN")
        regime = trade_data.get("regime", "UNKNOWN")
        side = trade_data.get("side", "BUY")
        score = trade_data.get("score", 0)
        breakdown = trade_data.get("breakdown", {})
        
        of = orderflow or {}
        spread_bps = of.get("spread_bps", 0.0)
        ofi = of.get("ofi", 0.0)
        cvd_delta = of.get("cvd_delta", 0.0)

        # If it was a winning trade, record success pattern
        if pnl_usd >= 0:
            return {
                "outcome": "WIN",
                "mistake_id": None,
                "mistake_title": "Profitable Institutional Alignment",
                "description": "Trade successfully executed and hit take profit target or trailing stop in profit.",
                "notes": f"Trade closed with net gain of +{pnl_pct:.2f}% (${pnl_usd:.2f} USD). Execution was in synergy with order flow and regime.",
                "adaptation_action": f"Pattern reinforced: Confluence confidence validated for {regime} setups."
            }

        # Otherwise, diagnose the failure pattern
        mistake_id = None
        notes = []

        # 1. Check for Spread / Slippage Friction
        if spread_bps > 12.0:
            mistake_id = "Mistake_Illiquid_Spread_Slippage"
            notes.append(f"Spread at entry was {spread_bps:.1f} bps (high friction). Slippage degraded the edge before the trade could breathe.")

        # 2. Check for CVD / OFI Exhaustion Trap
        elif side == "BUY" and (ofi < -0.20 or cvd_delta < 0):
            mistake_id = "Mistake_CVD_Exhaustion_Trap"
            notes.append("Buy signal was triggered while order book imbalance (OFI) was skewed negative. Aggressive sellers were in control despite price appearance.")
        elif side == "SHORT" and (ofi > 0.20 or cvd_delta > 0):
            mistake_id = "Mistake_CVD_Exhaustion_Trap"
            notes.append("Short signal was triggered into heavy passive bid absorption. Limit buyers absorbed all market selling.")

        # 3. Check for False Breakout in NOISE
        elif regime == "NOISE":
            mistake_id = "Mistake_Noise_Overtrading"
            notes.append("Market was diagnosed as NOISE regime. Mean reversion failed due to lack of structural volume and liquidity.")

        # 4. Check for Overextended Entry
        elif breakdown.get("extreme_deviation", 0) > 0 and abs(trade_data.get("z_score", 0)) > 2.8:
            mistake_id = "Mistake_Overextended_Entry"
            notes.append("Entry occurred at extreme statistical standard deviation without wait for pullback confirmation.")

        # 5. Fallback to Volatility Shakeout
        else:
            mistake_id = "Mistake_Adverse_Volatility_Spike"
            notes.append(f"Trade hit {trigger} due to adverse market volatility. Directional follow-through failed to materialize.")

        definition = MISTAKE_DEFINITIONS.get(mistake_id, {
            "title": "Unclassified Trading Loss",
            "description": "Market variance or unexpected regime change."
        })

        return {
            "outcome": "LOSS",
            "mistake_id": mistake_id,
            "mistake_title": definition["title"],
            "description": definition["description"],
            "notes": " ".join(notes),
            "adaptation_action": f"Penalty activated: Applying -20 score penalty to {mistake_id} patterns until win-rate re-establishes."
        }

autopsy_engine = TradeAutopsyEngine()
