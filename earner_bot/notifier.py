"""
notifier.py — Ouroboros Bot 3.1 Telegram Notifications
Sends formatted alerts with AED portfolio values.
"""
import requests
import logging
from typing import Dict, Any, Optional
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, AED_USD_RATE
from audit import audit

logger = logging.getLogger("Ouroboros.notifier")


def usd_to_aed(usd: float) -> float:
    """Convert USD to AED using fixed peg rate."""
    return round(usd * AED_USD_RATE, 2)


def fmt_aed(usd: float) -> str:
    """Format a USD value as both USD and AED."""
    return f"${usd:,.2f} (AED {usd_to_aed(usd):,.2f})"


def send_telegram(message: str) -> None:
    """Send a Telegram message. Skips gracefully if token is placeholder."""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "paste_your_telegram_bot_token_here":
        print(f"[NOTIFY SKIPPED] {message}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       f"🤖 Ouroboros 3.1\n{message}",
        "parse_mode": "HTML",
    }
    try:
        r = requests.post(url, json=payload, timeout=5)
        r.raise_for_status()
    except Exception as e:
        audit("TELEGRAM_ERROR", {"error": str(e)})
        logger.error(f"Telegram error: {e}")


def send_trade_alert(action: str, qty: float, price: float, regime: str,
                     paper: bool, confluence: int = 0,
                     pnl_pct: Optional[float] = None,
                     portfolio_usd: Optional[float] = None) -> None:
    """Send a formatted trade notification with AED values."""
    emoji = "🟢" if action == "BUY" else "🔴" if "SELL" in action else "⚠️"
    mode = "📄 PAPER" if paper else "💰 LIVE"

    lines = [
        f"{emoji} <b>{action}</b> | {mode}",
        f"Qty: {qty:.6f} BTC @ ${price:,.2f}",
        f"Regime: {regime} | Confluence: {confluence}/100",
    ]
    if pnl_pct is not None:
        pnl_emoji = "✅" if pnl_pct > 0 else "❌"
        lines.append(f"PnL: {pnl_emoji} {pnl_pct:+.2f}%")
    if portfolio_usd is not None:
        lines.append(f"Portfolio: {fmt_aed(portfolio_usd)}")
    send_telegram("\n".join(lines))


def send_daily_summary(stats: Dict[str, Any], portfolio_usd: float) -> None:
    """Send end-of-day performance summary with AED values."""
    lines = [
        "📊 <b>Daily Summary</b>",
        f"Trades: {stats.get('trades', 0)} | Wins: {stats.get('wins', 0)}",
        f"Daily PnL: ${stats.get('pnl_usd', 0):.2f} (AED {stats.get('pnl_aed', 0):.2f})",
        f"Portfolio: {fmt_aed(portfolio_usd)}",
    ]
    wr = stats.get("wins", 0) / max(stats.get("trades", 1), 1) * 100
    lines.append(f"Win Rate: {wr:.0f}%")
    send_telegram("\n".join(lines))


def send_stop_loss_alert(trigger: str, price: float, stop_price: float,
                         pnl_pct: float, portfolio_usd: float) -> None:
    """Alert when a stop-loss, take-profit, or trailing stop fires."""
    emoji = {"STOP_LOSS": "🛑", "TAKE_PROFIT": "🎯", "TRAILING_STOP": "📉", "TIME_EXIT": "⏰"}
    lines = [
        f"{emoji.get(trigger, '⚠️')} <b>{trigger} TRIGGERED</b>",
        f"Exit @ ${price:,.2f} | Target was ${stop_price:,.2f}",
        f"PnL: {pnl_pct:+.2f}%",
        f"Portfolio: {fmt_aed(portfolio_usd)}",
    ]
    send_telegram("\n".join(lines))
