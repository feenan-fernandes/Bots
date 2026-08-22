"""
watchdog.py — Ouroboros Bot 3.1 Emergency Systems
Halt flag management, emergency close with crash-proof error handling,
and consecutive exception counter.
"""
import os
import logging
from typing import Dict, Optional
from audit import audit
from notifier import send_telegram

logger = logging.getLogger("Ouroboros.watchdog")
HALT_FILE = os.path.join("output", "Ouroboros_halt.flag")


def create_halt_flag(reason: str) -> None:
    """Create a halt flag file to stop all trading on next cycle."""
    try:
        os.makedirs("output", exist_ok=True)
        with open(HALT_FILE, "w") as f:
            f.write(reason)
        logger.critical("HALT FLAG CREATED: %s", reason)
        audit("HALT_FLAG", {"reason": reason})
    except Exception as e:
        logger.critical("FAILED to create halt flag: %s", e)


def is_halted() -> bool:
    """Check if the halt flag file exists."""
    return os.path.exists(HALT_FILE)


def clear_halt() -> None:
    """Remove the halt flag to resume trading."""
    try:
        if os.path.exists(HALT_FILE):
            os.remove(HALT_FILE)
        logger.info("Halt flag cleared")
        audit("HALT_CLEARED")
    except Exception as e:
        logger.error("Failed to clear halt flag: %s", e)


def emergency_close_all(state_mgr) -> None:
    """
    Emergency sell all open positions and halt the bot.
    Crash-proof: wrapped in try/except so even if a sell fails,
    the halt flag is ALWAYS created.
    """
    assets_sold = {}
    result_status = "success"

    try:
        import config
        from broker_binance import get_balances, execute_sell_safe, execute_buy_safe, get_current_price

        # Use safe balance fetch with try/except
        balances = get_balances()
        if balances is None:
            logger.error("Emergency close: balance fetch failed")
            result_status = "balance_fetch_failed"
        else:
            for trade in state_mgr.open_trades:
                symbol = trade["symbol"]
                side = trade.get("side", "LONG")
                asset = symbol.replace("USDT", "")
                
                # Use the original trade qty for closing
                qty = float(trade.get("qty", 0.0))
                
                if qty > 0:
                    logger.critical(f"Emergency closing {qty:.8f} {asset}")
                    if side == "LONG":
                        order = execute_sell_safe(symbol, qty)
                    else:
                        if config.PAPER_MODE:
                            order = {"paper": True, "qty": qty, "status": "FILLED"}
                        else:
                            order = execute_buy_safe(symbol, qty)
                        
                    if order:
                        assets_sold[asset] = qty
                    else:
                        result_status = "partial_failure"
                        
            if assets_sold:
                send_telegram(f"🚨 EMERGENCY CLOSE EXECUTED. Assets sold: {assets_sold}. Bot halted.")
            else:
                send_telegram(f"🚨 EMERGENCY CLOSE COMPLETED with no assets sold. Bot halted.")

    except Exception as e:
        logger.critical("Exception during emergency close: %s", e)
        result_status = f"exception: {str(e)}"
        try:
            send_telegram(f"🚨 EMERGENCY CLOSE EXCEPTION: {str(e)} — manual intervention required!")
        except Exception:
            pass  # Last resort: can't even send telegram

    # ALWAYS audit and clear state, even if sell fails
    audit("EMERGENCY_CLOSE", {"assets_sold": assets_sold, "result": result_status})
    state_mgr.open_trades = []
    state_mgr.save()
    # ALWAYS create halt flag — this is the safety net
    create_halt_flag("EMERGENCY_CLOSE")


class ExceptionCounter:
    """Track consecutive exceptions. Triggers halt after threshold failures."""

    def __init__(self, threshold: int = 3):
        self.count: int = 0
        self.threshold: int = threshold

    def record_failure(self) -> bool:
        """Record a failure. Returns True if threshold reached."""
        self.count += 1
        return self.count >= self.threshold

    def record_success(self) -> None:
        """Reset counter on successful cycle."""
        self.count = 0
