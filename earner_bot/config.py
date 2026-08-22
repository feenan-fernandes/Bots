"""
config.py — Ouroboros Bot 3.1 Configuration Loader
Loads all environment variables into typed Python constants.
All trading parameters are configurable via .env without code changes.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ─── API Credentials ──────────────────────────────────────────────
BINANCE_API_KEY:    str = os.environ["BINANCE_API_KEY"]
BINANCE_SECRET:     str = os.environ["BINANCE_SECRET"]
TELEGRAM_BOT_TOKEN: str = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID:   str = os.environ["TELEGRAM_CHAT_ID"]

# ─── Mode & Symbols ───────────────────────────────────────────────
PAPER_MODE:        bool = os.getenv("PAPER_MODE", "true").lower() == "true"
FUTURES_MODE:      bool = os.getenv("FUTURES_MODE", "false").lower() == "true"
BLACKLIST_SYMBOLS: str  = os.getenv("BLACKLIST_SYMBOLS", "")
INTERVAL_PRIMARY:  str  = os.getenv("INTERVAL_PRIMARY", "4h")
MAX_OPEN_TRADES:   int  = int(os.getenv("MAX_OPEN_TRADES", "5"))
# ─── Data ─────────────────────────────────────────────────────────
# Must be >= 300 for indicator warmup (MACD=33, BB=20, ADX=14, rolling=25, Hurst=150)
LOOKBACK: int = int(os.getenv("LOOKBACK", 350))

# ─── Capital Protection ────────────────────────────────────────────
MAX_DAILY_LOSS_PCT: float = float(os.getenv("MAX_DAILY_LOSS_PCT", 0.05))
MAX_CONSECUTIVE_LOSSES: int = int(os.getenv("MAX_CONSECUTIVE_LOSSES", 3))
MIN_REGIME_WIN_RATE: float = float(os.getenv("MIN_REGIME_WIN_RATE", 0.35))

# ─── Risk Parameters ─────────────────────────────────────────────
MAX_RISK_PCT:       float = float(os.getenv("MAX_RISK_PCT", 0.20))

# ─── ATR-Based Dynamic Stops ─────────────────────────────────────
STOP_LOSS_ATR_MULT:  float = float(os.getenv("STOP_LOSS_ATR_MULT", 3.0))
TAKE_PROFIT_ATR_MULT: float = float(os.getenv("TAKE_PROFIT_ATR_MULT", 4.0))

# ─── Trailing Stop ───────────────────────────────────────────────
TRAILING_STOP_ACTIVATE_PCT: float = float(os.getenv("TRAILING_STOP_ACTIVATE_PCT", 0.005))
TRAILING_STOP_ATR_MULT:     float = float(os.getenv("TRAILING_STOP_ATR_MULT", 1.0))

# ─── Time-Based Exit ─────────────────────────────────────────────
MAX_HOLD_HOURS: int = int(os.getenv("MAX_HOLD_HOURS", 720))

# ─── Confluence Scoring ──────────────────────────────────────────
MIN_CONFLUENCE_SCORE: int = int(os.getenv("MIN_CONFLUENCE_SCORE", 50))

# ─── Currency ─────────────────────────────────────────────────────
# UAE Dirham pegged to USD at 3.6725 (Central Bank of UAE fixed rate)
AED_USD_RATE: float = float(os.getenv("AED_USD_RATE", 3.6725))

# ─── Black Swan Detection ────────────────────────────────────────
ATR_MULTIPLIER: float = float(os.getenv("ATR_MULTIPLIER", 3.5))
