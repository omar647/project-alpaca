"""Feature engineering for the ML trading signal.

Builds a numeric feature matrix from OHLCV data:

  * 11 technical indicators across all four categories (from ``indicators.py``)
  * Log returns
  * Rolling mean & rolling std (of log returns)

The output is a clean, all-numeric DataFrame with no NaNs, ready to be
standardized and fed into PCA.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .indicators import add_indicators

# The columns actually used as ML features (everything the model sees).
FEATURE_COLUMNS = [
    # Trend
    "sma20", "sma50", "ema20", "ema50", "ema200",
    "macd", "macd_signal", "macd_hist",
    "adx", "plus_di", "minus_di",
    # Momentum
    "rsi", "stoch_k", "stoch_d", "williams_r",
    # Volatility
    "bb_upper", "bb_mid", "bb_lower", "bb_width", "atr",
    # Volume
    "obv", "cmf",
    # Returns / rolling stats
    "log_return",
    "roll_mean_5", "roll_mean_10", "roll_mean_20",
    "roll_std_5", "roll_std_10", "roll_std_20",
]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``df`` with all indicator + return + rolling features.

    Keeps the original OHLCV columns (needed later for the backtest) alongside
    the engineered feature columns.
    """
    out = add_indicators(df)

    close = out["close"]

    # Bollinger band width (normalised) — a volatility feature.
    out["bb_width"] = (out["bb_upper"] - out["bb_lower"]) / out["bb_mid"]

    # Log returns.
    out["log_return"] = np.log(close / close.shift(1))

    # Rolling mean & std of log returns over several windows.
    for w in (5, 10, 20):
        out[f"roll_mean_{w}"] = out["log_return"].rolling(w).mean()
        out[f"roll_std_{w}"] = out["log_return"].rolling(w).std()

    # Drop warm-up rows where long indicators (ema200) are undefined.
    out = out.dropna(subset=FEATURE_COLUMNS).copy()
    return out


def feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Just the numeric feature columns (indexed by date)."""
    return build_features(df)[FEATURE_COLUMNS]
