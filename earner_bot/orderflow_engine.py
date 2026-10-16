"""
orderflow_engine.py — High-Frequency Order Flow & Microstructure Engine
Captures Order Flow Imbalance (OFI), Level-2 Bid/Ask queue depletion,
and Futures-to-Spot lead-lag metrics before retail public charts update.
"""
import time
import logging
from typing import Dict, Any, Optional, Tuple, List
import config

logger = logging.getLogger("Ouroboros.orderflow")

class OrderFlowEngine:
    def __init__(self, client=None):
        self.client = client
        self._last_snapshot_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 2.0  # seconds

    def get_orderflow_snapshot(self, client, symbol: str) -> Dict[str, Any]:
        """
        Fetches sub-second Level-2 order book depth and calculates:
        1. Order Flow Imbalance (OFI)
        2. Bid-Ask Spread in Basis Points (bps)
        3. Top 5 Bids and Asks queue sizes
        4. Binance Futures-to-Spot lead-lag price velocity
        """
        now = time.time()
        cached = self._last_snapshot_cache.get(symbol)
        if cached and (now - cached.get("timestamp", 0)) < self._cache_ttl:
            return cached

        snapshot = {
            "symbol": symbol,
            "timestamp": now,
            "ofi": 0.0,
            "spread_bps": 0.0,
            "best_bid": 0.0,
            "best_ask": 0.0,
            "mid_price": 0.0,
            "total_bid_depth": 0.0,
            "total_ask_depth": 0.0,
            "futures_lead_pct": 0.0,
            "cvd_delta": 0.0,
            "top_bids": [],
            "top_asks": [],
            "liquidity_skew": "NEUTRAL"
        }

        try:
            from broker_binance import safe_api_call
            c = client or self.client
            if not c:
                return snapshot

            # 1. Fetch Level-2 Order Book (Top 5 levels)
            depth = safe_api_call(c.get_order_book, symbol=symbol, limit=5)
            if depth and "bids" in depth and "asks" in depth and depth["bids"] and depth["asks"]:
                top_bids = [(float(p), float(q)) for p, q in depth["bids"][:5]]
                top_asks = [(float(p), float(q)) for p, q in depth["asks"][:5]]
                
                snapshot["top_bids"] = top_bids
                snapshot["top_asks"] = top_asks
                
                best_bid = top_bids[0][0]
                best_ask = top_asks[0][0]
                mid_price = (best_bid + best_ask) / 2.0
                
                snapshot["best_bid"] = best_bid
                snapshot["best_ask"] = best_ask
                snapshot["mid_price"] = mid_price

                # Calculate Spread in basis points
                if mid_price > 0:
                    spread_bps = ((best_ask - best_bid) / mid_price) * 10000.0
                    snapshot["spread_bps"] = round(spread_bps, 2)

                # Calculate Micro-Price (Volume-Weighted Mid) & Skew
                v_bid = top_bids[0][1]
                v_ask = top_asks[0][1]
                if (v_bid + v_ask) > 0:
                    micro_price = (v_ask * best_bid + v_bid * best_ask) / (v_bid + v_ask)
                    snapshot["micro_price"] = round(micro_price, 4)
                    if mid_price > 0:
                        snapshot["micro_skew_bps"] = round(((micro_price - mid_price) / mid_price) * 10000.0, 2)

                # Calculate Order Flow Imbalance (OFI) across top 5 levels
                sum_bid_qty = sum(q for _, q in top_bids)
                sum_ask_qty = sum(q for _, q in top_asks)
                snapshot["total_bid_depth"] = round(sum_bid_qty, 4)
                snapshot["total_ask_depth"] = round(sum_ask_qty, 4)

                total_depth = sum_bid_qty + sum_ask_qty
                if total_depth > 0:
                    ofi = (sum_bid_qty - sum_ask_qty) / total_depth
                    snapshot["ofi"] = round(ofi, 3)
                    if ofi > 0.40:
                        snapshot["liquidity_skew"] = "HEAVY_BID_PRESSURE"
                    elif ofi < -0.40:
                        snapshot["liquidity_skew"] = "HEAVY_ASK_PRESSURE"

            # 2. Futures-to-Spot Lead-Lag Check
            try:
                # Query Futures price if accessible
                f_ticker = safe_api_call(c.futures_symbol_ticker, symbol=symbol)
                if f_ticker and "price" in f_ticker and snapshot["mid_price"] > 0:
                    f_price = float(f_ticker["price"])
                    lead_pct = ((f_price - snapshot["mid_price"]) / snapshot["mid_price"]) * 100.0
                    snapshot["futures_lead_pct"] = round(lead_pct, 4)
            except Exception:
                pass  # Gracefully ignore if Futures endpoint is not available or restricted

            # 3. Short-term Taker Volume & Realized Volatility
            try:
                recent_trades = safe_api_call(c.get_recent_trades, symbol=symbol, limit=20)
                if recent_trades:
                    buy_vol = sum(float(t["qty"]) for t in recent_trades if not t["isBuyerMaker"])
                    sell_vol = sum(float(t["qty"]) for t in recent_trades if t["isBuyerMaker"])
                    snapshot["cvd_delta"] = round(buy_vol - sell_vol, 4)
                    
                    # Compute Realized Micro-Volatility in bps
                    prices = [float(t["price"]) for t in recent_trades]
                    if len(prices) >= 5:
                        import numpy as np
                        log_returns = np.diff(np.log(prices))
                        if len(log_returns) > 0:
                            snapshot["realized_vol_bps"] = round(float(np.std(log_returns) * 10000.0), 2)
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Error computing order flow snapshot for {symbol}: {e}")

        self._last_snapshot_cache[symbol] = snapshot
        return snapshot

orderflow_engine = OrderFlowEngine()
