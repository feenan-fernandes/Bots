"""
state.py — Persistent State Manager for Ouroboros Bot 3.1
Saves all bot state to JSON with atomic writes so Cloud Run restarts,
crashes, and deployments never lose trade positions or protection tiers.
"""
import json
import os
import shutil
import logging
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any

logger = logging.getLogger("Ouroboros.state")

STATE_FILE = os.path.join("output", "bot_state.json")

DEFAULT_STATE: Dict[str, Any] = {
    "version": 3,
    "open_trades": [],
    "protection": None,
    "trade_history": [],
    "daily_stats": {
        "date": None,
        "trades": 0,
        "wins": 0,
        "pnl_usd": 0.0,
        "pnl_aed": 0.0,
    },
    "idempotency_cache": {},
    "last_analysis": {
        "ts": None,
        "symbol": "BTCUSDT",
        "regime": "WAITING",
        "mtf": "WAITING",
        "signal": "WAITING",
        "score": 0,
        "action": "WAITING",
        "reason": ""
    },
    "scanned_candidates": {}
}


class StateManager:
    """Thread-safe persistent state manager with atomic JSON writes."""

    def __init__(self, filepath: str = STATE_FILE):
        self.filepath = filepath
        self.lock = threading.RLock()
        self.state = self._load()
        self.dirty = False
        threading.Thread(target=self._background_writer, daemon=True).start()

    def _background_writer(self):
        import time, copy, json
        while True:
            time.sleep(1.0)
            if self.dirty:
                with self.lock:
                    state_copy = copy.deepcopy(self.state)
                    self.dirty = False
                    
                os.makedirs(os.path.dirname(self.filepath) or "output", exist_ok=True)
                for attempt in range(5):
                    try:
                        with open(self.filepath + ".tmp", 'w') as f:
                            json.dump(state_copy, f, indent=4)
                        os.replace(self.filepath + ".tmp", self.filepath)
                        break
                    except PermissionError:
                        if attempt < 4:
                            time.sleep(0.5)
                        else:
                            logger.error("Failed to save state file: Access Denied.")

    def _load(self) -> Dict[str, Any]:
        """Load state from disk, or return defaults if missing/corrupt."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    data = json.load(f)
                # Migrate if needed
                if data.get("version", 1) < 2:
                    data = self._migrate_v1_to_v2(data)
                if data.get("version", 2) < 3:
                    data = self._migrate_v2_to_v3(data)
                logger.info(f"State loaded from {self.filepath}")
                return data
            except json.JSONDecodeError as e:
                logger.error(f"Corrupt state file, backing up and resetting: {e}")
                backup = self.filepath + f".corrupt.{int(datetime.now().timestamp())}"
                if os.path.exists(self.filepath): shutil.copy2(self.filepath, backup)
                from watchdog import create_halt_flag
                from notifier import send_telegram
                create_halt_flag("State Corrupted")
                send_telegram("CRITICAL: State corrupted!")
                return self._defaults()
            except KeyError as e:
                logger.error(f"Corrupt state file, backing up and resetting: {e}")
                backup = self.filepath + f".corrupt.{int(datetime.now().timestamp())}"
                shutil.copy2(self.filepath, backup)
                return self._defaults()
        return self._defaults()

    @staticmethod
    def _defaults() -> Dict[str, Any]:
        return json.loads(json.dumps(DEFAULT_STATE))

    @staticmethod
    def _migrate_v1_to_v2(data: Dict) -> Dict:
        """Migrate v1 state (in-memory era) to v2 (persistent)."""
        data["version"] = 2
        data.setdefault("trade_history", [])
        data.setdefault("daily_stats", DEFAULT_STATE["daily_stats"].copy())
        data.setdefault("idempotency_cache", {})
        data.setdefault("last_analysis", DEFAULT_STATE["last_analysis"].copy())
        return data

    @staticmethod
    def _migrate_v2_to_v3(data: Dict) -> Dict:
        """Migrate v2 state to v3 (multi-coin basket)."""
        data["version"] = 3
        old_trade = data.pop("open_trade", None)
        if old_trade:
            data["open_trades"] = [old_trade]
        else:
            data["open_trades"] = []
        return data

    def save(self) -> None:
        """Flags the state as dirty so the background thread can flush it without blocking the main execution loop."""
        self.dirty = True

    # ─── Trade State ──────────────────────────────────────────────

    @property
    def open_trades(self) -> List[Dict]:
        return self.state.get("open_trades", [])

    @open_trades.setter
    def open_trades(self, value: List[Dict]) -> None:
        self.state["open_trades"] = value

    def add_open_trade(self, symbol: str, price: float, qty: float, regime: str,
                       stop_loss: float, take_profit: float, atr: float, side: str = "LONG",
                       orderflow: Optional[Dict] = None, score: int = 0, breakdown: Optional[Dict] = None) -> None:
        """Record a new trade with all protective levels and microstructure telemetry."""
        trade = {
            "symbol": symbol,
            "side": side,
            "price": price,
            "qty": qty,
            "regime": regime,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "atr_at_entry": atr,
            "highest_price": price,
            "lowest_price": price,
            "entry_time": datetime.now(timezone.utc).isoformat(),
            "orderflow": orderflow or {},
            "score": score,
            "breakdown": breakdown or {}
        }
        with self.lock:
            self.state["open_trades"].append(trade)
            self.save()

    def get_trade(self, symbol: str) -> Optional[Dict]:
        """Get an active trade by symbol."""
        for t in self.state.get("open_trades", []):
            if t["symbol"] == symbol:
                return t
        return None

    def update_highest_price(self, symbol: str, current_price: float) -> None:
        """Track the highest price for trailing stop calculation."""
        with self.lock:
            trade = self.get_trade(symbol)
            if trade and current_price > trade.get("highest_price", 0):
                trade["highest_price"] = current_price
                self.save()

    def update_lowest_price(self, symbol: str, current_price: float) -> None:
        """Track the lowest price for short trailing stop calculation."""
        with self.lock:
            trade = self.get_trade(symbol)
            if trade and (trade.get("lowest_price") is None or current_price < trade["lowest_price"]):
                trade["lowest_price"] = current_price
                self.save()

    def remove_trade(self, symbol: str) -> None:
        with self.lock:
            self.state["open_trades"] = [t for t in self.state.get("open_trades", []) if t["symbol"] != symbol]
            self.save()

    # ─── Trade History ────────────────────────────────────────────

    def record_trade_result(self, symbol: str, entry_price: float, exit_price: float,
                            pnl_pct: float, pnl_usd: float, regime: str,
                            entry_time: str, aed_rate: float = 3.6725) -> None:
        """Record completed trade for adaptive Kelly and daily stats."""
        with self.lock:
            result = {
                "symbol": symbol,
                "entry_time": entry_time,
                "exit_time": datetime.now(timezone.utc).isoformat(),
                "entry_price": round(entry_price, 2),
                "exit_price": round(exit_price, 2),
                "pnl_pct": round(pnl_pct, 4),
                "pnl_usd": round(pnl_usd, 4),
                "pnl_aed": round(pnl_usd * aed_rate, 2),
                "regime": regime,
            }
            self.state["trade_history"].append(result)
            if len(self.state["trade_history"]) > 200:
                self.state["trade_history"] = self.state["trade_history"][-200:]

            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            stats = self.state["daily_stats"]
            if stats.get("date") != today:
                stats.update({"date": today, "trades": 0, "wins": 0, "pnl_usd": 0.0, "pnl_aed": 0.0})
            stats["trades"] += 1
            if pnl_pct > 0:
                stats["wins"] += 1
            stats["pnl_usd"] += pnl_usd
            stats["pnl_aed"] += pnl_usd * aed_rate
            self.save()

    def get_trade_history(self, n: int = 50) -> List[Dict]:
        """Get last N trade results for adaptive Kelly computation."""
        return self.state.get("trade_history", [])[-n:]

    @property
    def daily_stats(self) -> Dict:
        return self.state.get("daily_stats", DEFAULT_STATE["daily_stats"].copy())

    # ─── Capital Protection State ─────────────────────────────────

    @property
    def protection(self) -> Optional[Dict]:
        return self.state.get("protection")

    @protection.setter
    def protection(self, value: Optional[Dict]) -> None:
        self.state["protection"] = value

    # ─── Idempotency Cache ────────────────────────────────────────

    @property
    def idempotency_cache(self) -> Dict:
        return self.state.get("idempotency_cache", {})

    @idempotency_cache.setter
    def idempotency_cache(self, value: Dict) -> None:
        self.state["idempotency_cache"] = value

    # ─── Analysis State ───────────────────────────────────────────

    def record_analysis(self, symbol: str, regime: str, mtf: str, signal: str, score: int, action: str, reason: str = "", breakdown: Dict = None) -> None:
        with self.lock:
            self.state["last_analysis"] = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol,
                "regime": regime,
                "mtf": mtf,
                "signal": signal,
                "score": score,
                "action": action,
                "reason": reason,
                "breakdown": breakdown or {}
            }
            # Only keep top 10 scanned candidates to prevent state bloat
            self.state.setdefault("scanned_candidates", {})
            if symbol not in self.state["scanned_candidates"]:
                self.state["scanned_candidates"][symbol] = {}
            self.state["scanned_candidates"][symbol].update({
                "score": score,
                "signal": signal,
                "regime": regime,
                "breakdown": breakdown or {},
                "ts": datetime.now(timezone.utc).isoformat()
            })
            if len(self.state["scanned_candidates"]) > 20:
                # Remove oldest
                oldest = min(self.state["scanned_candidates"].items(), key=lambda x: x[1]["ts"])[0]
                del self.state["scanned_candidates"][oldest]
            # Removed self.save() to prevent massive I/O overhead locking the WS thread.

    @property
    def last_analysis(self) -> Dict:
        return self.state.get("last_analysis", DEFAULT_STATE["last_analysis"].copy())
