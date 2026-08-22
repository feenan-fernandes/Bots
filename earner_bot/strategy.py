"""
strategy.py - Ouroboros Bot 4.0 Institutional Strategy Engine
Decoupled Regime-Based Router using Hurst Exponent, Kalman Filters, 
VWAP Z-Scores, and Cumulative Volume Delta (CVD).
"""
import pandas as pd
import numpy as np
import logging
from typing import Dict, Tuple, Any, Optional
from config import ATR_MULTIPLIER

logger = logging.getLogger("Ouroboros.strategy")

def get_data(client, symbol: str, interval: str, lookback: int = 200) -> pd.DataFrame:
    """Fetch OHLCV candles from Binance and return a clean DataFrame."""
    candles = client.get_klines(symbol=symbol, interval=interval, limit=lookback)
    df = pd.DataFrame(candles, columns=[
        "time", "open", "high", "low", "close", "volume",
        "ct", "qa", "nt", "tbv", "tqv", "ignore"])
    for col in ["open", "high", "low", "close", "volume", "tbv", "tqv"]:
        df[col] = df[col].astype(float)
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    return df.set_index("time")

def drop_incomplete_candle(df: pd.DataFrame) -> pd.DataFrame:
    """Drop the last row if it's a still-forming candle to prevent repainting."""
    if len(df) < 2:
        return df
    return df.iloc[:-1].copy()

# =====================================================================
# ADVANCED QUANTITATIVE INDICATORS
# =====================================================================

def calculate_hurst_exponent(ts: pd.Series, max_lag: int = 20) -> float:
    """
    Calculate the Hurst Exponent using variance of differences.
    """
    if len(ts) < max_lag * 2:
        return 0.5
    lags = range(2, max_lag)
    tau = [np.sqrt(np.std(np.subtract(ts[lag:], ts[:-lag]))) for lag in lags]
    # Use a linear fit to estimate the Hurst Exponent
    poly = np.polyfit(np.log(lags), np.log(tau), 1)
    return poly[0] * 2.0

def apply_kalman_filter(prices: pd.Series) -> pd.Series:
    """
    1D Kalman Filter for dynamic zero-lag trend estimation.
    """
    n = len(prices)
    kalman_states = np.zeros(n)
    
    Q = 1e-5
    R = 0.01 
    
    xhat = prices.iloc[0]
    P = 1.0
    
    for i in range(n):
        xhat_minus = xhat
        P_minus = P + Q
        
        K = P_minus / (P_minus + R)
        xhat = xhat_minus + K * (prices.iloc[i] - xhat_minus)
        P = (1 - K) * P_minus
        
        kalman_states[i] = xhat
        
    return pd.Series(kalman_states, index=prices.index)

def calculate_vwap_and_zscore(df: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Calculate rolling VWAP and the Z-Score of the closing price relative to VWAP."""
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    
    rolling_pv = (typical_price * df['volume']).rolling(window=window).sum()
    rolling_vol = df['volume'].rolling(window=window).sum()
    df['VWAP'] = rolling_pv / rolling_vol
    
    vwap_std = typical_price.rolling(window=window).std()
    df['VWAP_Z'] = (df['close'] - df['VWAP']) / vwap_std
    return df

def calculate_cvd(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate Cumulative Volume Delta (CVD) using Taker Buy Base Volume (tbv).
    """
    buy_vol = df['tbv']
    sell_vol = df['volume'] - df['tbv']
    df['delta'] = buy_vol - sell_vol
    df['CVD'] = df['delta'].cumsum()
    df['delta_MA'] = df['delta'].rolling(window=5).mean()
    return df

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Average True Range using Wilder's Smoothing."""
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    df['ATR'] = true_range.rolling(period).mean()
    return df

def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Relative Strength Index."""
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

def detect_candlestick_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Identify key reversal and continuation candlestick patterns."""
    body = np.abs(df['close'] - df['open'])
    upper_shadow = df['high'] - np.maximum(df['close'], df['open'])
    lower_shadow = np.minimum(df['close'], df['open']) - df['low']
    range_total = df['high'] - df['low']
    
    range_total_safe = range_total.replace(0, 1e-9)
    
    df['is_hammer'] = (lower_shadow > (2 * body)) & (upper_shadow < (0.2 * range_total_safe)) & (range_total > df['ATR'] * 0.5)
    df['is_shooting_star'] = (upper_shadow > (2 * body)) & (lower_shadow < (0.2 * range_total_safe)) & (range_total > df['ATR'] * 0.5)
    
    prev_close = df['close'].shift(1)
    prev_open = df['open'].shift(1)
    df['is_bullish_engulfing'] = (prev_close < prev_open) & (df['close'] > df['open']) & \
                                 (df['close'] > prev_open) & (df['open'] < prev_close)
                                 
    df['is_bearish_engulfing'] = (prev_close > prev_open) & (df['close'] < df['open']) & \
                                 (df['close'] < prev_open) & (df['open'] > prev_close)
    
    df['is_doji'] = (body < (0.1 * range_total_safe))
    
    return df

def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all advanced indicators required for the V4 strategy."""
    if len(df) < 50:
        return df
        
    df = calculate_atr(df, 14)
    df = calculate_rsi(df, 14)
    df = detect_candlestick_patterns(df)
    
    df['Kalman'] = apply_kalman_filter(df['close'])
    df['Kalman_Slope'] = (df['Kalman'] - df['Kalman'].shift(5)) / df['Kalman'].shift(5)
    
    df = calculate_vwap_and_zscore(df, 20)
    df = calculate_cvd(df)
    
    hurst_vals = [0.5] * 50
    for i in range(50, len(df)):
        h = calculate_hurst_exponent(df['close'].iloc[i-50:i].values)
        hurst_vals.append(h)
    df['Hurst'] = hurst_vals
    
    # --- Adaptive Hurst Smoothing (V4.1 Regulatory Compliance) ---
    df['Smoothed_Hurst'] = df['Hurst'].ewm(span=100, adjust=False).mean()
    df['Hurst_STD'] = df['Hurst'].ewm(span=100, adjust=False).std().fillna(0.02)
    df['Hurst_Upper'] = 0.5 + (1.5 * df['Hurst_STD'])
    df['Hurst_Lower'] = 0.5 - (1.5 * df['Hurst_STD'])

    return df.dropna()

# =====================================================================
# REGIME DETECTION & STRATEGY ROUTER
# =====================================================================

def detect_regime(df: pd.DataFrame) -> str:
    """
    Classify regime using Hurst Exponent and Extreme ATR deviations.
    """
    if len(df) < 2:
        return "RANGING"

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # BLACK_SWAN: Extreme range exceeds ATR threshold
    true_range = max(last["high"] - last["low"], abs(last["high"] - prev["close"]), abs(last["low"] - prev["close"]))
    if true_range > (ATR_MULTIPLIER * 1.5) * last["ATR"]:
        logger.warning("BLACK_SWAN detected: TR %.2f > %.2f", true_range, (ATR_MULTIPLIER * 1.5) * last["ATR"])
        return "BLACK_SWAN"

    h = last["Hurst"]
    if h > last["Hurst_Upper"]:
        return "TRENDING"
    elif h < last["Hurst_Lower"]:
        return "RANGING"
    else:
        return "NOISE"

def trend_following_alpha(df: pd.DataFrame) -> Tuple[str, int, Dict[str, Any]]:
    """
    Alpha Generator for TRENDING regimes (Volatility Breakouts).
    Requires VWAP Z-Score breakout aligned with true order flow (CVD).
    """
    last = df.iloc[-1]
    
    breakdown = {
        "volatility_breakout": 0,
        "cvd_alignment": 0,
        "kalman_trend": 0
    }
    
    z = last.get("VWAP_Z", 0)
    
    kalman_bullish = last["close"] > last.get("Kalman", 0) and last.get("Kalman_Slope", 0) > 0
    kalman_bearish = last["close"] < last.get("Kalman", 0) and last.get("Kalman_Slope", 0) < 0
    
    cvd_bullish = last.get("delta", 0) > 0 and last.get("delta_MA", 0) > 0
    cvd_bearish = last.get("delta", 0) < 0 and last.get("delta_MA", 0) < 0
    
    if z > 1.5:  # Bullish Volatility Expansion
        breakdown["volatility_breakout"] = 50
        score = 50
        if cvd_bullish:
            breakdown["cvd_alignment"] = 30
            score += 30
        if kalman_bullish:
            breakdown["kalman_trend"] = 20
            score += 20
        # Require extremely high conviction for trend breakout
        if score >= 80:
            return "BUY", score, breakdown
            
    if z < -1.5:  # Bearish Volatility Expansion
        breakdown["volatility_breakout"] = 50
        score = 50
        if cvd_bearish:
            breakdown["cvd_alignment"] = 30
            score += 30
        if kalman_bearish:
            breakdown["kalman_trend"] = 20
            score += 20
        if score >= 80:
            return "SELL", score, breakdown
            
    return "HOLD", 0, breakdown

def mean_reversion_alpha(df: pd.DataFrame) -> Tuple[str, int, Dict[str, Any]]:
    """
    Alpha Generator for RANGING regimes (Structural Capitulation Sweep).
    Requires extreme VWAP deviation combined with Delta Exhaustion.
    """
    last = df.iloc[-1]
    
    breakdown = {
        "extreme_deviation": 0,
        "exhaustion": 0,
        "rsi_divergence": 0
    }
    
    z = last.get("VWAP_Z", 0)
    rsi = last.get("RSI", 50)
    
    # We want extreme deviation (Z < -2.5) for capitulation buys
    if z < -2.5:
        breakdown["extreme_deviation"] = 50
        score = 50
        
        # Delta > 0 while deeply oversold means passive buyers are absorbing aggressive sellers
        if last.get("delta", 0) > 0:
            breakdown["exhaustion"] = 30
            score += 30
            
        if rsi < 30:
            breakdown["rsi_divergence"] = 20
            score += 20
            
        if score >= 80:
            return "BUY", score, breakdown
            
    if z > 2.5:
        breakdown["extreme_deviation"] = 50
        score = 50
        
        if last.get("delta", 0) < 0:
            breakdown["exhaustion"] = 30
            score += 30
            
        if rsi > 70:
            breakdown["rsi_divergence"] = 20
            score += 20
            
        if score >= 80:
            return "SELL", score, breakdown
            
    return "HOLD", 0, breakdown

def get_signal(df: pd.DataFrame, regime: str, client=None, symbol: str = None) -> Dict[str, Any]:
    """
    Main strategy router.
    """
    if regime == "BLACK_SWAN":
        return {"signal": "HOLD", "score": 0, "breakdown": {}, "regime": regime}
        
    if regime == "NOISE":
        # In NOISE, still evaluate but require a much higher confidence threshold.
        # This prevents the deadlock of blocking everything while still filtering weak signals.
        signal, score, breakdown = mean_reversion_alpha(df)
        # Only allow NOISE trades with very high conviction (score >= 70)
        if score < 70:
            return {"signal": "HOLD", "score": score, "breakdown": breakdown, "regime": regime}
        return {"signal": signal, "score": score, "breakdown": breakdown, "regime": regime}

    if regime == "TRENDING":
        signal, score, breakdown = trend_following_alpha(df)
    else:
        signal, score, breakdown = mean_reversion_alpha(df)

    return {
        "signal": signal,
        "score": score,
        "breakdown": breakdown,
        "regime": regime,
    }

def multi_timeframe_gate(client, symbol: str) -> str:
    """
    Check 1H timeframe to ensure we aren't buying into a local micro-crash 
    or selling into a local micro-pump against the 4H trend.
    """
    try:
        df_1h = get_data(client, symbol, "1h", 30)
        if len(df_1h) < 21:
            return "MIXED"
            
        df_1h['EMA9'] = df_1h['close'].ewm(span=9).mean()
        df_1h['EMA21'] = df_1h['close'].ewm(span=21).mean()
        
        last_1h = df_1h.iloc[-1]
        
        if last_1h['EMA9'] > last_1h['EMA21']:
            return "CONFIRMED_BUY"
        elif last_1h['EMA9'] < last_1h['EMA21']:
            return "CONFIRMED_SELL"
            
        return "MIXED"
    except Exception as e:
        logger.error(f"MTF Gate Error for {symbol}: {e}")
        return "MIXED"
