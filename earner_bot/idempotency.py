"""
idempotency.py — Ouroboros Bot 3.1 Decision Deduplication (Persistent)
SHA-256 fingerprints each decision. Same candle/signal never fires twice.
Persists to disk so Cloud Run restarts don't break deduplication.
"""
import hashlib
import json
import os
import logging
import threading
from datetime import datetime, timezone
from typing import Dict

logger = logging.getLogger("Ouroboros.idempotency")

CACHE_FILE = os.path.join("output", "idempotency_cache.json")
MAX_CACHE_SIZE = 200


def make_decision_id(symbol: str, candle_ts: str, regime: str, signal: str) -> str:
    """Create a unique fingerprint for a trading decision."""
    raw = f"{symbol}:{candle_ts}:{regime}:{signal}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class IdempotencyGuard:
    """Persistent idempotency cache that survives process restarts."""

    def __init__(self, state_cache: Dict = None):
        """Initialize from state manager's cache dict."""
        self._executed: Dict[str, str] = state_cache if state_cache is not None else {}
        self.lock = threading.RLock()

    def is_duplicate(self, decision_id: str) -> bool:
        with self.lock:
            return decision_id in self._executed

    def mark_executed(self, decision_id: str) -> None:
        with self.lock:
            self._executed[decision_id] = datetime.now(timezone.utc).isoformat()
            # Evict oldest entries if cache exceeds limit
            while len(self._executed) > MAX_CACHE_SIZE:
                oldest_key = next(iter(self._executed))
                del self._executed[oldest_key]

    def get_cache(self) -> Dict:
        """Return the cache dict for state persistence."""
        with self.lock:
            return self._executed
