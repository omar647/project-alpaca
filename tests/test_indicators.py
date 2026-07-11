"""Unit tests for technical indicators (no network)."""

import numpy as np
import pandas as pd

from strategy.indicators import sma, ema, rsi, add_indicators


def _price_frame(n=120):
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    close = pd.Series(np.linspace(100, 160, n), index=idx)
    return pd.DataFrame({
        "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": 1_000_000,
    }, index=idx)


def test_sma_matches_rolling_mean():
    s = pd.Series(range(10), dtype=float)
    assert sma(s, 3).iloc[-1] == (7 + 8 + 9) / 3


def test_ema_length_and_finiteness():
    s = pd.Series(np.arange(50), dtype=float)
    e = ema(s, 10)
    assert len(e) == 50 and np.isfinite(e.iloc[-1])


def test_rsi_bounds():
    df = _price_frame()
    r = rsi(df["close"]).dropna()
    assert (r >= 0).all() and (r <= 100).all()


def test_add_indicators_adds_expected_columns():
    df = add_indicators(_price_frame())
    for col in ("sma20", "ema50", "macd", "adx", "rsi", "bb_upper", "atr", "obv", "cmf"):
        assert col in df.columns
