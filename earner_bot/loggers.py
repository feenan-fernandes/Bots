import logging
from logging.handlers import RotatingFileHandler
import os

os.makedirs("logs", exist_ok=True)

def setup_loggers():
    """Configure centralized logging for errors and trades."""
    # Base formatter
    base_fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    # 1. Error File Handler (Catches ERROR and CRITICAL globally)
    error_handler = RotatingFileHandler("logs/Ouroboros_errors.log", maxBytes=5*1024*1024, backupCount=5)
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(base_fmt)
    
    # Attach to the root logger so it catches everything
    logging.getLogger().addHandler(error_handler)

    # 2. Trade Specific Logger
    trade_logger = logging.getLogger("Ouroboros.trades")
    trade_logger.setLevel(logging.INFO)
    
    trade_handler = RotatingFileHandler("logs/Ouroboros_trades.log", maxBytes=5*1024*1024, backupCount=5)
    trade_fmt = logging.Formatter("%(asctime)s | TRADE | %(message)s")
    trade_handler.setFormatter(trade_fmt)
    
    trade_logger.addHandler(trade_handler)
    trade_logger.propagate = True  # Also print trades to console

    return trade_logger

trade_logger = setup_loggers()
