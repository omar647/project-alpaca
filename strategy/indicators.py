"""Technical indicators, implemented in pure pandas/numpy (no TA-Lib).

Categories:
  Trend      : SMA, EMA, MACD, ADX
  Momentum   : RSI, Stochastic Oscillator, Williams %R
  Volatility : Bollinger Bands, ATR
  Volume     : OBV, Chaikin Money Flow (CMF)
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ------------------------------- Trend ------------------------------------- #
def sma(close: pd.Series, n: int = 20) -> pd.Series:
    return close.rolling(n).mean()


def ema(close: pd.Series, n: int = 20) -> pd.Series:
    return close.ewm(span=n, adjust=False).mean()


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def _wilder(series: pd.Series, n: int) -> pd.Series:
    """Wilder's smoothing (used by ATR/ADX/RSI)."""
    return series.ewm(alpha=1 / n, adjust=False).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    return _wilder(tr, n)


def adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14):
    """Return (adx, +DI, -DI)."""
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index)

    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    atr_ = _wilder(tr, n)

    plus_di = 100 * _wilder(plus_dm, n) / atr_
    minus_di = 100 * _wilder(minus_dm, n) / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_line = _wilder(dx, n)
    return adx_line, plus_di, minus_di


# ------------------------------ Momentum ----------------------------------- #
def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = _wilder(gain, n)
    avg_loss = _wilder(loss, n)
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def stochastic(high, low, close, n: int = 14, d: int = 3):
    """Return (%K, %D)."""
    lowest = low.rolling(n).min()
    highest = high.rolling(n).max()
    k = 100 * (close - lowest) / (highest - lowest).replace(0, np.nan)
    return k, k.rolling(d).mean()


def williams_r(high, low, close, n: int = 14) -> pd.Series:
    highest = high.rolling(n).max()
    lowest = low.rolling(n).min()
    return -100 * (highest - close) / (highest - lowest).replace(0, np.nan)


# ----------------------------- Volatility ---------------------------------- #
def bollinger(close: pd.Series, n: int = 20, k: float = 2.0):
    """Return (upper, middle, lower)."""
    mid = close.rolling(n).mean()
    std = close.rolling(n).std()
    return mid + k * std, mid, mid - k * std


# ------------------------------- Volume ------------------------------------ #
def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def cmf(high, low, close, volume, n: int = 20) -> pd.Series:
    rng = (high - low).replace(0, np.nan)
    mf_mult = ((close - low) - (high - close)) / rng
    mf_vol = mf_mult * volume
    return mf_vol.rolling(n).sum() / volume.rolling(n).sum()


# ------------------------- convenience: add all ---------------------------- #
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``df`` with all indicator columns added."""
    out = df.copy()
    c, h, l, v = out["close"], out["high"], out["low"], out["volume"]

    out["sma20"] = sma(c, 20)
    out["sma50"] = sma(c, 50)
    out["ema20"] = ema(c, 20)
    out["ema50"] = ema(c, 50)
    out["ema200"] = ema(c, 200)
    out["macd"], out["macd_signal"], out["macd_hist"] = macd(c)
    out["adx"], out["plus_di"], out["minus_di"] = adx(h, l, c)
    out["rsi"] = rsi(c)
    out["stoch_k"], out["stoch_d"] = stochastic(h, l, c)
    out["williams_r"] = williams_r(h, l, c)
    out["bb_upper"], out["bb_mid"], out["bb_lower"] = bollinger(c)
    out["atr"] = atr(h, l, c)
    out["obv"] = obv(c, v)
    out["cmf"] = cmf(h, l, c, v)
    return out
