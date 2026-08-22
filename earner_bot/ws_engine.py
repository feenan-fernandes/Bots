import time
import logging
import threading
from threading import Thread
from binance import ThreadedWebsocketManager
import config
import broker_binance
from state import StateManager
from market_scanner import get_top_symbols

logger = logging.getLogger("Ouroboros.ws")

class WebSocketEngine:
    def __init__(self, state_mgr: StateManager):
        from concurrent.futures import ThreadPoolExecutor
        self.state_mgr = state_mgr
        self.twm = None
        self.active_symbols = set()
        self.conn_keys = {}
        self.last_message_time = {}
        self.last_eval_time = {}
        self.executor = ThreadPoolExecutor(max_workers=3)
        self.ws_lock = threading.Lock()
        self.running = False
        self.reconnect_thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        logger.info("Starting WebSocket Engine...")
        self.twm = ThreadedWebsocketManager(api_key=config.BINANCE_API_KEY, api_secret=config.BINANCE_SECRET)
        self.twm.start()
        
        self.reconnect_thread = Thread(target=self._maintenance_loop, daemon=True)
        self.reconnect_thread.start()

    def stop(self):
        self.running = False
        if self.twm:
            self.twm.stop()
            logger.info("WebSocket Engine stopped.")
            with self.ws_lock:
                self.active_symbols.clear()
                self.conn_keys.clear()
                self.last_message_time.clear()

    def _maintenance_loop(self):
        """Periodically update the top symbols and resubscribe if needed."""
        while self.running:
            try:
                # 1. Autonomous position reconciliation (Decoupled from frontend UI)
                from reconcile import reconcile_all_positions
                reconcile_all_positions(self.state_mgr)

                # 1.5. Polling Fallback for TP/SL (Critical for illiquid assets or Paper Mode when WS is silent)
                from broker_binance import get_current_price
                from risk import check_stop_take, portfolio_value_usd
                from app import _execute_exit
                from broker_binance import get_balances
                
                open_trade_symbols = {t["symbol"] for t in self.state_mgr.open_trades}
                if open_trade_symbols:
                    balances = get_balances()
                    for sym in open_trade_symbols:
                        trade = self.state_mgr.get_trade(sym)
                        if trade:
                            curr_price = get_current_price(sym)
                            if curr_price:
                                self.state_mgr.update_highest_price(sym, curr_price)
                                self.state_mgr.update_lowest_price(sym, curr_price)
                                curr_atr = trade.get("atr_at_entry", curr_price * 0.01)
                                trigger = check_stop_take(trade, curr_price, curr_atr)
                                if trigger:
                                    logger.info(f"Fallback Polling triggered {trigger} for {sym} at {curr_price}")
                                    port_usd = portfolio_value_usd(balances, {sym: curr_price})
                                    self.executor.submit(_execute_exit, trigger, trade, curr_price, port_usd)

                # 2. Maintain websocket subscriptions
                top_symbols = set(get_top_symbols(broker_binance.client, limit=20, user_blacklist=config.BLACKLIST_SYMBOLS))
                target_symbols = open_trade_symbols.union(top_symbols)
                
                current_time = time.time()
                with self.ws_lock:
                    dead_syms = []
                    for sym in self.active_symbols:
                        last_time = self.last_message_time.get(sym, current_time)
                        if current_time - last_time > 180:
                            logger.error(f"WS connection for {sym} seems dead. Unsubscribing to force reconnect.")
                            dead_syms.append(sym)
                            
                    for sym in dead_syms:
                        conn_key = self.conn_keys.get(sym)
                        if conn_key:
                            try:
                                self.twm.stop_socket(conn_key)
                            except Exception as e:
                                logger.error(f"Error stopping socket for {sym}: {e}")
                            del self.conn_keys[sym]
                        self.active_symbols.remove(sym)
                        if sym in self.last_message_time:
                            del self.last_message_time[sym]
                with self.ws_lock:
                    to_remove = []
                    for sym in self.active_symbols:
                        if sym not in target_symbols:
                            logger.info(f"WS Unsubscribing from {sym} klines...")
                            conn_key = self.conn_keys.get(sym)
                            if conn_key:
                                self.twm.stop_socket(conn_key)
                                del self.conn_keys[sym]
                            to_remove.append(sym)
                    for sym in to_remove:
                        self.active_symbols.remove(sym)
                        if sym in self.last_message_time:
                            del self.last_message_time[sym]
                    
                    for sym in target_symbols:
                        if sym not in self.active_symbols:
                            logger.info(f"WS Subscribing to {sym} klines...")
                            conn_key = self.twm.start_kline_socket(callback=self._handle_kline_message, symbol=sym, interval=config.INTERVAL_PRIMARY)
                            self.conn_keys[sym] = conn_key
                            self.active_symbols.add(sym)
                            self.last_message_time[sym] = current_time
                
            except Exception as e:
                logger.error(f"Maintenance loop error: {e}")
            
            # Run every 60 seconds
            time.sleep(60)

    def _handle_kline_message(self, msg):
        if msg['e'] != 'kline':
            return
        
        kline = msg['k']
        is_closed = kline['x']
        symbol = kline['s']
        current_price = float(kline['c'])
        
        with self.ws_lock:
            self.last_message_time[symbol] = time.time()
        
        # 1. Update highest and lowest price for trailing stops
        self.state_mgr.update_highest_price(symbol, current_price)
        self.state_mgr.update_lowest_price(symbol, current_price)
        
        # 1.5. Immediate TP/SL evaluation on every tick (Critical for Scalping & Paper Mode)
        trade = self.state_mgr.get_trade(symbol)
        if trade:
            from risk import check_stop_take
            current_atr = trade.get("atr_at_entry", current_price * 0.01)
            exit_trigger = check_stop_take(trade, current_price, current_atr)
            if exit_trigger:
                from app import _execute_exit
                from broker_binance import get_balances
                from risk import portfolio_value_usd
                balances = get_balances()
                prices = {symbol: current_price}
                port_usd = portfolio_value_usd(balances, prices)
                self.executor.submit(_execute_exit, exit_trigger, trade, current_price, port_usd)

        # 2. On close, evaluate for new trade entries
        if is_closed:
            logger.info(f"Candle closed for {symbol}, queuing background evaluation...")
            from app import _evaluate_symbol_async
            # Use bounded thread pool to prevent bursting Binance API limit
            self.executor.submit(_evaluate_symbol_async, symbol, current_price)
