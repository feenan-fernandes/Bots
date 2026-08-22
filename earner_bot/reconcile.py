"""
reconcile.py - Ouroboros Bot 3.1 Position Reconciliation
Compares local bot state vs actual Binance balance every cycle.
Multi-Coin and Futures compatible.
"""
import logging
from typing import Dict, Optional, List
from broker_binance import safe_api_call, client, get_current_price
from audit import audit
import config

logger = logging.getLogger("Ouroboros.reconcile")

def reconcile_all_positions(state_mgr) -> None:
    """
    Sync local multi-coin trade state with actual exchange balances.
    Skips if PAPER_MODE is True.
    Checks Futures positions if FUTURES_MODE is True, else Spot balances.
    """
    if config.PAPER_MODE:
        return  # Paper trades don't exist on the exchange

    if config.FUTURES_MODE:
        _reconcile_futures(state_mgr)
    else:
        _reconcile_spot(state_mgr)

def _reconcile_futures(state_mgr):
    positions_resp = safe_api_call(client.futures_position_information)
    if not positions_resp:
        return
        
    actual_positions = {}
    for pos in positions_resp:
        amt = float(pos["positionAmt"])
        if abs(amt) > 0:
            actual_positions[pos["symbol"]] = amt

    _reconcile_generic(state_mgr, actual_positions)

def _reconcile_spot(state_mgr):
    from broker_binance import get_balances
    balances = get_balances()
    if not balances:
        return
        
    actual_positions = {}
    for trade in state_mgr.open_trades:
        sym = trade["symbol"]
        base_asset = sym.replace("USDT", "")
        if base_asset in balances:
            actual_positions[sym] = balances[base_asset]

    _reconcile_generic(state_mgr, actual_positions)

def _reconcile_generic(state_mgr, actual_positions: Dict[str, float]):
    open_trades = state_mgr.open_trades
    local_symbols = {t["symbol"]: t for t in open_trades}

    # 1. Ghost trades (Local trade exists, but no exchange position)
    for sym, trade in local_symbols.items():
        if sym not in actual_positions:
            logger.warning(f"Ghost position detected for {sym} - clearing state")
            audit("RECONCILE", {"case": "ghost", "symbol": sym})
            state_mgr.remove_trade(sym)
            
    # 2. Phantom trades (Exchange position exists, but no local trade)
    for sym, amt in actual_positions.items():
        if sym not in local_symbols:
            price = get_current_price(sym) or 0.0
            min_notional = 5.0
            if abs(amt) * price > min_notional:
                logger.warning(f"Phantom position found for {sym}: {amt} - restoring state")
                audit("RECONCILE", {"case": "phantom", "symbol": sym, "amt": amt})
                side = "LONG" if amt > 0 else "SHORT"
                state_mgr.add_open_trade(
                    symbol=sym, price=price, qty=abs(amt), regime="UNKNOWN",
                    stop_loss=price * (0.95 if side == "LONG" else 1.05),
                    take_profit=price * (1.05 if side == "LONG" else 0.95),
                    atr=price * 0.01, side=side
                )

    # 3. Mismatches
    for sym, amt in actual_positions.items():
        if sym in local_symbols:
            trade = local_symbols[sym]
            expected = trade["qty"]
            if abs(abs(amt) - expected) / max(expected, 1e-9) > 0.05:
                logger.warning(f"Qty mismatch for {sym}: local={expected} actual={abs(amt)}")
                audit("RECONCILE", {"case": "mismatch", "symbol": sym, "expected": expected, "actual": abs(amt)})
                with state_mgr.lock:
                    for t in state_mgr.state["open_trades"]:
                        if t["symbol"] == sym:
                            t["qty"] = abs(amt)
                    state_mgr.save()
