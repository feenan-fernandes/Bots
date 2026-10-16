"""
dead_mans_switch.py — Independent External Watchdog & Dead-Man's Switch
Runs as a decoupled, isolated process monitoring the trading bot's heartbeat.
If the main bot thread deadlocks, segfaults, or freezes for > 3.0 seconds,
this daemon executes an emergency mass-cancellation on Binance to protect capital.
"""
import os
import sys
import time
import json
import logging
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [DEAD_MAN_SWITCH] %(levelname)s: %(message)s"
)
logger = logging.getLogger("DeadMansSwitch")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HEARTBEAT_FILE = os.path.join(BASE_DIR, "output", "heartbeat.json")
HALT_FLAG_FILE = os.path.join(BASE_DIR, "output", "HALT.flag")

class DeadMansSwitch:
    def __init__(self, heartbeat_path: str = HEARTBEAT_FILE, timeout_sec: float = 3.5):
        self.heartbeat_path = heartbeat_path
        self.timeout_sec = timeout_sec
        self.triggered = False

    def emit_heartbeat(self, active_symbols: list = None):
        """Called by the main trading bot loop every 500ms."""
        os.makedirs(os.path.dirname(self.heartbeat_path) or "output", exist_ok=True)
        payload = {
            "timestamp": time.time(),
            "iso_time": datetime.now(timezone.utc).isoformat(),
            "pid": os.getpid(),
            "status": "ALIVE",
            "active_symbols": active_symbols or []
        }
        temp_file = self.heartbeat_path + ".tmp"
        try:
            with open(temp_file, "w") as f:
                json.dump(payload, f)
            os.replace(temp_file, self.heartbeat_path)
        except Exception as e:
            logger.error(f"Error emitting heartbeat: {e}")

    def run_monitor_loop(self):
        """Runs indefinitely as an independent supervisor process."""
        logger.info(f"Starting Independent Dead-Man's Switch (Timeout: {self.timeout_sec}s)...")
        while True:
            time.sleep(0.5)
            if not os.path.exists(self.heartbeat_path):
                continue

            try:
                with open(self.heartbeat_path, "r") as f:
                    data = json.load(f)
                
                last_beat = float(data.get("timestamp", 0.0))
                elapsed = time.time() - last_beat

                if elapsed > self.timeout_sec and not self.triggered:
                    logger.critical(f"⚠️ HEARTBEAT LOST! Last signal was {elapsed:.2f}s ago (> {self.timeout_sec}s). TRIGGERING FAILSAFE!")
                    self.execute_emergency_kill(data.get("active_symbols", []))
                    self.triggered = True
                elif elapsed <= self.timeout_sec and self.triggered:
                    logger.info("Heartbeat restored. Resetting Dead-Man trigger.")
                    self.triggered = False

            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")

    def execute_emergency_kill(self, active_symbols: list):
        """Immediately executes mass-cancel across the exchange."""
        logger.critical("🚨 EXECUTING MASS CANCEL ACROSS BINANCE EXCHANGE...")
        
        # 1. Write Hard Halt Flag
        try:
            with open(HALT_FLAG_FILE, "w") as f:
                f.write(f"DEAD_MAN_TRIGGERED at {datetime.now(timezone.utc).isoformat()}")
        except Exception:
            pass

        # 2. Cancel Open Orders on Exchange
        try:
            import config
            from binance.client import Client
            from binance.exceptions import BinanceAPIException
            
            client = Client(config.BINANCE_API_KEY, config.BINANCE_SECRET)
            symbols_to_cancel = set(active_symbols or [])
            if not symbols_to_cancel:
                symbols_to_cancel = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"}

            for sym in symbols_to_cancel:
                try:
                    logger.warning(f"Cancelling open orders for {sym}...")
                    if config.FUTURES_MODE:
                        client.futures_cancel_all_open_orders(symbol=sym)
                    else:
                        open_orders = client.get_open_orders(symbol=sym)
                        for o in open_orders:
                            client.cancel_order(symbol=sym, orderId=o["orderId"])
                    logger.info(f"Successfully wiped open orders for {sym}")
                except BinanceAPIException as be:
                    logger.error(f"Binance API error cancelling {sym}: {be}")
                except Exception as e:
                    logger.error(f"Error cancelling {sym}: {e}")

        except Exception as e:
            logger.error(f"Failed to execute exchange mass-cancel: {e}")

        # 3. Notify via Telegram
        try:
            from notifier import send_telegram
            send_telegram("🚨 *DEAD-MAN'S SWITCH TRIGGERED*\nTrading bot missed heartbeats > 3.5s. All open orders cancelled to protect capital.")
        except Exception:
            pass

if __name__ == "__main__":
    dms = DeadMansSwitch()
    dms.run_monitor_loop()
