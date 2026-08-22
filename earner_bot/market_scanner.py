"""
market_scanner.py — Ouroboros Bot 3.1
Dynamically fetches top-performing, highly liquid assets from Binance.
Filters out meme coins, stablecoins, and user-defined blacklisted assets.
"""
from typing import List
import logging
from binance.client import Client

logger = logging.getLogger("Ouroboros.scanner")

# Default exclusions: Meme coins and Stablecoins
CORE_BLACKLIST = {
    # Memes
    "DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "FLOKIUSDT", "BONKUSDT", 
    "WIFUSDT", "BOMEUSDT", "MEMEUSDT", "NOTUSDT", "BRETTUSDT",
    # Stablecoins / Fiat pegged
    "USDCUSDT", "FDUSDUSDT", "TUSDUSDT", "EURUSDT", "BUSDUSDT", "DAIUSDT", "AEURUSDT",
    # Privacy Coins (UAE VARA Compliance Ban)
    "XMRUSDT", "ZECUSDT", "DASHUSDT", "FIROUSDT", "ZENUSDT", "SCRTUSDT", "XVGUSDT"
}

def get_top_symbols(client: Client, limit: int = 10, user_blacklist: str = "") -> List[str]:
    """
    Fetches the top `limit` USDT pairs by 24h trading volume.
    Excludes meme coins, stablecoins, and custom blacklisted pairs.
    """
    try:
        tickers = client.get_ticker()
    except Exception as e:
        logger.error(f"Failed to fetch market tickers: {e}")
        return ["BTCUSDT"]  # Fallback to safe default
    
    # Process user custom blacklist (comma separated)
    custom_bans = set()
    if user_blacklist:
        custom_bans = {s.strip().upper() for s in user_blacklist.split(",") if s.strip()}
        # Ensure they all end in USDT for matching
        custom_bans = {s if s.endswith("USDT") else f"{s}USDT" for s in custom_bans}

    full_blacklist = CORE_BLACKLIST.union(custom_bans)

    valid_pairs = []
    for t in tickers:
        symbol = t['symbol']
        # Only trade USDT pairs, exclude leverage tokens (UP/DOWN)
        if symbol.endswith("USDT") and not symbol.endswith("UPUSDT") and not symbol.endswith("DOWNUSDT"):
            if symbol not in full_blacklist:
                try:
                    vol = float(t['quoteVolume'])
                    high = float(t['highPrice'])
                    low = float(t['lowPrice'])
                    
                    # Volatility Filter: Skip if daily range is less than 1.5% (likely a stablecoin or dead asset)
                    if low > 0 and (high - low) / low < 0.015:
                        continue
                        
                    valid_pairs.append({"symbol": symbol, "volume": vol})
                except (ValueError, KeyError, ZeroDivisionError):
                    continue

    # Sort by quote volume descending
    valid_pairs.sort(key=lambda x: x["volume"], reverse=True)
    
    # Extract top symbols
    top_symbols = [pair["symbol"] for pair in valid_pairs[:limit]]
    
    if not top_symbols:
        logger.warning("No valid symbols found after filtering. Defaulting to BTCUSDT.")
        return ["BTCUSDT"]

    return top_symbols
