"""Unit tests for strategy signal generation (no network)."""

import numpy as np
import pandas as pd

from strategy.signals import MACrossover, make_strategy


def _trending_up(n=120):
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    close = pd.Series(np.linspace(100, 200, n), index=idx)
    return pd.DataFrame({
        "open": close, "high": close + 1, "low": close - 1,
        "close": close, "volume": 1e6,
    }, index=idx)


def test_ma_crossover_long_in_uptrend():
    strat = MACrossover(fast=10, slow=30)
    sig = strat.signal_series(_trending_up())
    # A clean uptrend should be long (fast above slow) at the end.
    assert sig.iloc[-1] == 1
    assert set(sig.unique()).issubset({0, 1})


def test_ma_crossover_flat_in_downtrend():
    df = _trending_up()
    df["close"] = df["close"].iloc[::-1].values  # reverse → downtrend
    strat = MACrossover(fast=10, slow=30)
    assert strat.signal_series(df).iloc[-1] == 0


def test_latest_signal_shape():
    strat = MACrossover(fast=10, slow=30)
    ls = strat.latest_signal("TEST", _trending_up())
    assert ls.signal in (0, 1)
    assert ls.symbol == "TEST" and ls.price > 0 and ls.reason


def test_factory_returns_correct_type():
    assert make_strategy("ma_crossover", {"fast": 5, "slow": 20}).name == "ma_crossover"
    assert make_strategy("ml", {"threshold": 0.6}).name == "ml"
