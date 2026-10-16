"""
broker_mt5.py — MetaTrader 5 (MT5) Execution Adapter for Ouroboros Bot
Allows Ouroboros to execute trades on Forex, CFDs, Gold (XAUUSD), and Prop Firms (FTMO, FundedNext)
while keeping the Microstructure Engine, Pre-Trade Risk Gate, and Obsidian Memory identical.
"""
import time
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger("Ouroboros.broker_mt5")

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    logger.warning("MetaTrader5 library not installed. Run 'pip install MetaTrader5' to enable MT5 broker mode.")

class MT5BrokerAdapter:
    def __init__(self, login: int = 0, password: str = "", server: str = "", path: str = ""):
        self.login = login
        self.password = password
        self.server = server
        self.path = path
        self.connected = False

    def initialize(self) -> bool:
        """Connects to the local MetaTrader 5 terminal instance."""
        if not MT5_AVAILABLE:
            logger.error("Cannot initialize MT5: MetaTrader5 Python package is missing.")
            return False

        init_kwargs = {}
        if self.path: init_kwargs["path"] = self.path
        if self.login: init_kwargs["login"] = self.login
        if self.password: init_kwargs["password"] = self.password
        if self.server: init_kwargs["server"] = self.server

        if not mt5.initialize(**init_kwargs):
            logger.error(f"MT5 initialize failed: {mt5.last_error()}")
            return False

        account_info = mt5.account_info()
        if account_info is None:
            logger.error(f"Failed to get MT5 account info: {mt5.last_error()}")
            return False

        logger.info(f"Connected to MT5 Account #{account_info.login} on {account_info.server} (Equity: {account_info.equity} {account_info.currency})")
        self.connected = True
        return True

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Fetches the latest tick mid-price."""
        if not self.connected and not self.initialize():
            return None
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        return (tick.bid + tick.ask) / 2.0

    def get_balances(self) -> Dict[str, float]:
        """Fetches free margin and equity."""
        if not self.connected and not self.initialize():
            return {"USDT": 0.0, "USD": 0.0}
        account = mt5.account_info()
        if not account:
            return {"USDT": 0.0, "USD": 0.0}
        return {
            "USD": float(account.balance),
            "USDT": float(account.balance),
            "equity": float(account.equity),
            "free_margin": float(account.margin_free)
        }

    def execute_buy_safe(self, symbol: str, qty: float) -> Optional[Dict[str, Any]]:
        """Sends a market or limit buy order through MT5."""
        if not self.connected and not self.initialize():
            return None

        # Ensure symbol is selected in Market Watch
        mt5.symbol_select(symbol, True)
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            logger.error(f"Failed to fetch tick for {symbol}")
            return None

        price = tick.ask
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(qty),
            "type": mt5.ORDER_TYPE_BUY,
            "price": price,
            "deviation": 20,
            "magic": 108888,
            "comment": "Ouroboros Algorithmic Buy",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"MT5 Buy Failed: code={result.retcode}, comment={result.comment}")
            return None

        logger.info(f"MT5 BUY FILLED: #{result.order} for {qty} {symbol} @ {result.price}")
        return {"status": "FILLED", "orderId": result.order, "price": result.price, "qty": qty}

    def execute_sell_safe(self, symbol: str, qty: float) -> Optional[Dict[str, Any]]:
        """Sends a market sell order (or short deal) through MT5."""
        if not self.connected and not self.initialize():
            return None

        mt5.symbol_select(symbol, True)
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            return None

        price = tick.bid
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(qty),
            "type": mt5.ORDER_TYPE_SELL,
            "price": price,
            "deviation": 20,
            "magic": 108888,
            "comment": "Ouroboros Algorithmic Sell",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"MT5 Sell Failed: code={result.retcode}, comment={result.comment}")
            return None

        logger.info(f"MT5 SELL FILLED: #{result.order} for {qty} {symbol} @ {result.price}")
        return {"status": "FILLED", "orderId": result.order, "price": result.price, "qty": qty}

    def place_bracket_orders(self, symbol: str, side: str, qty: float, stop_loss: float, take_profit: float):
        """Attaches native Stop Loss and Take Profit levels to open MT5 positions."""
        if not self.connected and not self.initialize():
            return
        positions = mt5.positions_get(symbol=symbol)
        if positions:
            for pos in positions:
                request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "symbol": symbol,
                    "sl": float(stop_loss),
                    "tp": float(take_profit)
                }
                mt5.order_send(request)
                logger.info(f"MT5 Bracket Secured for #{pos.ticket}: SL={stop_loss}, TP={take_profit}")

    def cancel_all_open_orders(self):
        """Emergency mass-cancel for Dead-Man's Switch."""
        if not self.connected and not self.initialize():
            return
        orders = mt5.orders_get()
        if orders:
            for o in orders:
                req = {"action": mt5.TRADE_ACTION_REMOVE, "order": o.ticket}
                mt5.order_send(req)
                logger.warning(f"MT5 Dead-Man cancelled order #{o.ticket}")

mt5_broker = MT5BrokerAdapter()
