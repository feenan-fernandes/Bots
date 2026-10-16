"""
learning_memory.py — Self-Learning Reinforcement Engine for Ouroboros Bot
Persists trade setup fingerprints and dynamically computes confidence penalties or boosts
so the bot actively learns from mistakes and suppresses recurring failure patterns.
"""
import os
import json
import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger("Ouroboros.memory")

MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "learning_memory.json")

class LearningMemoryEngine:
    def __init__(self, memory_filepath: str = MEMORY_FILE):
        self.filepath = memory_filepath
        self.memory: Dict[str, Dict[str, Any]] = self._load()

    def _load(self) -> Dict[str, Dict[str, Any]]:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading learning memory: {e}")
        return {}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.filepath) or "output", exist_ok=True)
            with open(self.filepath + ".tmp", "w", encoding="utf-8") as f:
                json.dump(self.memory, f, indent=2)
            os.replace(self.filepath + ".tmp", self.filepath)
        except Exception as e:
            logger.error(f"Error saving learning memory: {e}")

    @staticmethod
    def make_fingerprint(regime: str, side: str, ofi_skew: str = "NEUTRAL", cvd_aligned: bool = True) -> str:
        """Constructs a normalized pattern fingerprint."""
        cvd_tag = "CVD_ALIGNED" if cvd_aligned else "CVD_DIVERGENT"
        return f"{regime}::{side}::{ofi_skew}::{cvd_tag}"

    def record_outcome(self, fingerprint: str, is_win: bool, pnl_usd: float):
        """Records the outcome of a trade under this setup fingerprint."""
        if fingerprint not in self.memory:
            self.memory[fingerprint] = {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "net_pnl_usd": 0.0,
                "win_rate": 0.5,
                "penalty": 0
            }

        rec = self.memory[fingerprint]
        rec["trades"] += 1
        if is_win:
            rec["wins"] += 1
        else:
            rec["losses"] += 1
        rec["net_pnl_usd"] = round(rec["net_pnl_usd"] + pnl_usd, 4)
        rec["win_rate"] = round(rec["wins"] / rec["trades"], 3)

        # Dynamic Penalty Matrix Calculation
        # If >= 3 samples and win rate is poor (< 40%), penalize
        if rec["trades"] >= 3:
            if rec["win_rate"] < 0.25:
                rec["penalty"] = -25  # Severe penalty
            elif rec["win_rate"] < 0.40:
                rec["penalty"] = -15  # Moderate penalty
            elif rec["win_rate"] >= 0.65:
                rec["penalty"] = +10  # Confidence boost
            else:
                rec["penalty"] = 0
        else:
            rec["penalty"] = 0

        self._save()
        logger.info(f"Updated memory for [{fingerprint}]: {rec['trades']} trades, {rec['win_rate']*100:.1f}% WR, penalty: {rec['penalty']}")

    def get_pattern_penalty(self, fingerprint: str) -> int:
        """Returns the dynamic confidence adjustment (-25 to +10)."""
        rec = self.memory.get(fingerprint)
        if rec and rec.get("trades", 0) >= 3:
            return rec.get("penalty", 0)
        return 0

learning_memory = LearningMemoryEngine()
