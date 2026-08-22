"""
broker_binance.py — Ouroboros Bot 3.1 Exchange Integration
All Binance API communication with retry logic, filter compliance,
order confirmation, and null-safe error handling.
"""
import math
import time
import logging
from typing import Optional, Dict, Any
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException
from requests.exceptions import ConnectionError, Timeout
import config
from threading import Lock

logger = logging.getLogger("Ouroboros.broker")

# ─── Single shared client (imported by strategy.py, reconcile.py, etc.) ──
client = None

from requests.adapters import HTTPAdapter

def init_client():
    global client
    client = Client(config.BINANCE_API_KEY, config.BINANCE_SECRET)
    
    # Expand the connection pool to prevent urllib3 dropping connections
    adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20)
    client.session.mount('https://', adapter)
    client.session.mount('http://', adapter)

init_client()

def init_futures_margin(symbol: str):
    """Ensure symbol is on Isolated Margin and 1x Leverage to strictly bound risk."""
    if not config.FUTURES_MODE or config.PAPER_MODE:
        return
    try:
        client.futures_change_margin_type(symbol=symbol, marginType='ISOLATED')
    except Exception as e:
        if '-4046' not in str(e): # Ignore 'No need to change margin type' error
            logger.error(f"Failed to set isolated margin for {symbol}: {e}")
    try:
        client.futures_change_leverage(symbol=symbol, leverage=1)
    except Exception as e:
        logger.error(f"Failed to set 1x leverage for {symbol}: {e}")

RETRYABLE_CODES = {-1001, -1007, -1021, -1099}
_filters_cache: Dict[str, Dict] = {}


def safe_api_call(fn, *args, retries: int = 3, delay: float = 2.0, **kwargs) -> Any:
    """
    Retry wrapper with exponential backoff for Binance API calls.
    Returns None on all failures instead of raising.
    """
    for attempt in range(1, retries + 1):
        try:
            return fn(*args, **kwargs)
        except BinanceAPIException as e:
            if e.code in RETRYABLE_CODES and attempt < retries:
                logger.warning("Binance transient %d retry %d", e.code, attempt)
                time.sleep(delay * attempt)
            else:
                logger.error("Non-retryable Binance error: %d — %s", e.code, str(e))
                return None
        except (BinanceRequestException, ConnectionError, Timeout) as e:
            logger.warning("Network error attempt %d: %s", attempt, e)
            if attempt < retries:
                time.sleep(delay * attempt)
            else:
                return None
        except Exception as e:
            logger.error("Unexpected broker error: %s", e)
            return None
    return None


def get_exchange_filters(symbol: str = None) -> Optional[Dict]:
    """Get exchange trading rules (lot size, min notional) with caching."""
    if not symbol:
        raise ValueError("symbol parameter is required")
    if symbol in _filters_cache:
        return _filters_cache[symbol]
        
    if config.FUTURES_MODE:
        info_resp = safe_api_call(client.futures_exchange_info)
        if not info_resp:
            return None
        info = next((s for s in info_resp["symbols"] if s["symbol"] == symbol), None)
    else:
        info = safe_api_call(client.get_symbol_info, symbol)
        
    if info is None:
        return None
    filters = {f["filterType"]: f for f in info["filters"]}
    _filters_cache[symbol] = filters
    return filters


def quantize_qty(symbol: str, qty: float) -> Optional[float]:
    """Round quantity down to exchange step size."""
    filters = get_exchange_filters(symbol)
    if filters is None:
        return None
    step = float(filters["LOT_SIZE"]["stepSize"])
    precision = int(round(-math.log10(step)))
    return round(math.floor(qty / step) * step, precision)


def quantize_price(symbol: str, price: float) -> Optional[float]:
    """Round price to exchange tick size."""
    filters = get_exchange_filters(symbol)
    if filters is None:
        return None
    tick = float(filters["PRICE_FILTER"]["tickSize"])
    precision = int(round(-math.log10(tick)))
    return round(round(price / tick) * tick, precision)


def get_best_bid_ask(symbol: str = None) -> Optional[tuple[float, float]]:
    """Fetch live top-of-book bid and ask for limit order placement."""
    if not symbol:
        raise ValueError("symbol parameter is required")
    if config.FUTURES_MODE:
        book = safe_api_call(client.futures_order_book, symbol=symbol, limit=5)
    else:
        book = safe_api_call(client.get_order_book, symbol=symbol, limit=5)
    if not book:
        return None
    return float(book["bids"][0][0]), float(book["asks"][0][0])


def validate_notional(symbol: str, qty: float, price: float) -> bool:
    """Check if order meets minimum notional value."""
    filters = get_exchange_filters(symbol)
    if filters is None:
        return False
    notional = filters.get("NOTIONAL", filters.get("MIN_NOTIONAL", {}))
    min_n = float(notional.get("minNotional", 5.0))
    return qty * price >= min_n


def get_current_price(symbol: str = None) -> Optional[float]:
    """Fetch current ticker price with retry wrapper."""
    if not symbol:
        raise ValueError("symbol parameter is required")
    if config.FUTURES_MODE:
        ticker = safe_api_call(client.futures_symbol_ticker, symbol=symbol)
    else:
        ticker = safe_api_call(client.get_symbol_ticker, symbol=symbol)
    if ticker is None:
        return None
    return float(ticker["price"])


_balances_cache = {}
_balances_cache_time = 0
_balances_lock = Lock()

def get_balances(cache_ttl: float = 2.0) -> Dict[str, float]:
    """Fetch all non-zero asset balances with caching."""
    global _balances_cache, _balances_cache_time
    
    with _balances_lock:
        if time.time() - _balances_cache_time < cache_ttl:
            return _balances_cache

        if config.FUTURES_MODE:
            account = safe_api_call(client.futures_account)
            if account is None:
                return {}
            res = {b["asset"]: float(b["availableBalance"])
                    for b in account["assets"] if float(b["availableBalance"]) > 0}
        else:
            account = safe_api_call(client.get_account)
            if account is None:
                return {}
            res = {b["asset"]: float(b["free"])
                    for b in account["balances"] if float(b["free"]) > 0}
                    
        _balances_cache = res
        _balances_cache_time = time.time()
        return res


def verify_order_filled(symbol: str, order_id: int, timeout_sec: int = 30) -> Optional[Dict]:
    """Poll until order is FILLED, CANCELED, or timeout."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if config.FUTURES_MODE:
            order = safe_api_call(client.futures_get_order, symbol=symbol, orderId=order_id)
        else:
            order = safe_api_call(client.get_order, symbol=symbol, orderId=order_id)
        if order is None:
            time.sleep(2)
            continue
        status = order.get("status")
        if status == "FILLED":
            return order
        if status in ("CANCELED", "REJECTED", "EXPIRED"):
            logger.error("Order %s status=%s", order_id, status)
            return None
        if status == "PARTIALLY_FILLED":
            logger.warning("Order %s partially filled — waiting...", order_id)
        time.sleep(2)
    logger.error("Order %s not confirmed in %ds", order_id, timeout_sec)
    return None


def _chase_order(symbol: str, side: str, total_qty: float) -> Optional[Dict]:
    """
    Advanced Limit Order Chaser Engine.
    Places a LIMIT order at the best bid/ask to capture Maker fees and zero slippage.
    Waits 10 seconds. If unfilled, cancels and reprices. Repeats 5 times.
    Falls back to MARKET order for any remaining dust.
    """
    remaining_qty = quantize_qty(symbol, total_qty)
    if not remaining_qty or remaining_qty <= 0: 
        return None
    
    total_executed = 0.0
    total_quote = 0.0 
    
    for attempt in range(5):
        best_prices = get_best_bid_ask(symbol)
        if not best_prices: 
            break
            
        best_bid, best_ask = best_prices
        target_price = best_bid if side == "BUY" else best_ask
        target_price = quantize_price(symbol, target_price)
        
        if not validate_notional(symbol, remaining_qty, target_price):
            logger.warning("Remaining qty %f below min notional", remaining_qty)
            break
            
        logger.info("Chaser %s attempt %d: LIMIT @ %.2f for qty %.8f", side, attempt+1, target_price, remaining_qty)
        
        if side == "BUY":
            if config.FUTURES_MODE:
                order = safe_api_call(client.futures_create_order, symbol=symbol, side='BUY', type='LIMIT', timeInForce='GTC', quantity=remaining_qty, price=target_price)
            else:
                order = safe_api_call(client.order_limit_buy, symbol=symbol, quantity=remaining_qty, price=target_price)
        else:
            if config.FUTURES_MODE:
                order = safe_api_call(client.futures_create_order, symbol=symbol, side='SELL', type='LIMIT', timeInForce='GTC', quantity=remaining_qty, price=target_price)
            else:
                order = safe_api_call(client.order_limit_sell, symbol=symbol, quantity=remaining_qty, price=target_price)
            
        if not order:
            logger.error("Failed to place limit %s", side)
            break
            
        order_id = order["orderId"]
        time.sleep(10)
        
        if config.FUTURES_MODE:
            check = safe_api_call(client.futures_get_order, symbol=symbol, orderId=order_id)
        else:
            check = safe_api_call(client.get_order, symbol=symbol, orderId=order_id)
            
        if not check:
            if config.FUTURES_MODE:
                safe_api_call(client.futures_cancel_order, symbol=symbol, orderId=order_id)
            else:
                safe_api_call(client.cancel_order, symbol=symbol, orderId=order_id)
            break
            
        status = check.get("status")
        executed = float(check.get("executedQty", 0.0))
        cummulative_quote = float(check.get("cummulativeQuoteQty", 0.0))
        
        if status == "FILLED":
            total_executed += executed
            total_quote += cummulative_quote
            remaining_qty = 0.0
            break
            
        elif status in ["NEW", "PARTIALLY_FILLED"]:
            if config.FUTURES_MODE:
                canceled = safe_api_call(client.futures_cancel_order, symbol=symbol, orderId=order_id)
            else:
                canceled = safe_api_call(client.cancel_order, symbol=symbol, orderId=order_id)
                
            if canceled:
                if config.FUTURES_MODE:
                    final_check = safe_api_call(client.futures_get_order, symbol=symbol, orderId=order_id)
                else:
                    final_check = safe_api_call(client.get_order, symbol=symbol, orderId=order_id)
                if final_check:
                    executed = float(final_check.get("executedQty", 0.0))
                    cummulative_quote = float(final_check.get("cummulativeQuoteQty", 0.0))
            
            total_executed += executed
            total_quote += cummulative_quote
            
            remaining_raw = total_qty - total_executed
            remaining_qty = quantize_qty(symbol, remaining_raw)
            if not remaining_qty or remaining_qty <= 0:
                break
        else:
            break

    if remaining_qty and remaining_qty > 0:
        price_check = get_current_price(symbol)
        if price_check and validate_notional(symbol, remaining_qty, price_check):
            logger.warning("Chaser incomplete. MARKET FALLBACK %s for %.8f", side, remaining_qty)
            if side == "BUY":
                if config.FUTURES_MODE:
                    m_order = safe_api_call(client.futures_create_order, symbol=symbol, side='BUY', type='MARKET', quantity=remaining_qty)
                else:
                    m_order = safe_api_call(client.order_market_buy, symbol=symbol, quantity=remaining_qty)
            else:
                if config.FUTURES_MODE:
                    m_order = safe_api_call(client.futures_create_order, symbol=symbol, side='SELL', type='MARKET', quantity=remaining_qty)
                else:
                    m_order = safe_api_call(client.order_market_sell, symbol=symbol, quantity=remaining_qty)
                
            if m_order:
                m_check = verify_order_filled(symbol, m_order["orderId"])
                if m_check:
                    total_executed += float(m_check.get("executedQty", 0.0))
                    total_quote += float(m_check.get("cummulativeQuoteQty", 0.0))

    avg_price = (total_quote / total_executed) if total_executed > 0 else 0.0
    if total_executed > 0:
        return {"status": "FILLED", "qty": total_executed, "price": avg_price}
    return None


def execute_buy_safe(symbol: str, qty: float) -> Optional[Dict]:
    """Safe Buy executing the Limit Order Chaser with Paper tracking."""
    if config.PAPER_MODE:
        price = get_current_price(symbol)
        logger.info("[PAPER] BUY %.8f %s @ %.2f (Simulated Maker Execution)", qty, symbol, price)
        return {"paper": True, "qty": qty, "price": price, "status": "FILLED"}
    return _chase_order(symbol, "BUY", qty)


def execute_sell_safe(symbol: str, qty: float) -> Optional[Dict]:
    """Safe Sell executing the Limit Order Chaser with Paper tracking."""
    if config.PAPER_MODE:
        price = get_current_price(symbol)
        logger.info("[PAPER] SELL %.8f %s @ %.2f (Simulated Maker Execution)", qty, symbol, price)
        return {"paper": True, "qty": qty, "price": price, "status": "FILLED"}
    return _chase_order(symbol, "SELL", qty)


def place_bracket_orders(symbol: str, side: str, qty: float, stop_loss: float, take_profit: float) -> bool:
    """
    Places native STOP_MARKET and TAKE_PROFIT_MARKET orders directly on Binance Futures.
    Ensures that if the bot loses connection, the capital is protected natively on the exchange.
    """
    if not config.FUTURES_MODE or config.PAPER_MODE:
        return True # Handled synthetically in paper/spot mode
        
    opp_side = "SELL" if side == "BUY" else "BUY"
    
    sl_price = quantize_price(symbol, stop_loss)
    tp_price = quantize_price(symbol, take_profit)
    q = quantize_qty(symbol, qty)
    
    logger.info(f"Placing native brackets for {symbol}: SL={sl_price}, TP={tp_price}")
    
    success = True
    # Stop Loss
    sl_order = safe_api_call(client.futures_create_order, 
                             symbol=symbol, 
                             side=opp_side, 
                             type='STOP_MARKET', 
                             stopPrice=sl_price, 
                             closePosition=True,
                             timeInForce='GTC')
    if not sl_order:
        logger.error(f"Failed to place native STOP_MARKET for {symbol}")
        success = False

    # Take Profit
    tp_order = safe_api_call(client.futures_create_order, 
                             symbol=symbol, 
                             side=opp_side, 
                             type='TAKE_PROFIT_MARKET', 
                             stopPrice=tp_price, 
                             closePosition=True,
                             timeInForce='GTC')
    if not tp_order:
        logger.error(f"Failed to place native TAKE_PROFIT_MARKET for {symbol}")
        success = False
        
    return success

