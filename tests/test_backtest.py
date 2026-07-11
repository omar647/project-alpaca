"""Unit tests for the backtest engine (no network)."""

import numpy as np
import pandas as pd

from backtest.engine import run_backtest
from backtest.metrics import compute_metrics, drawdown_series


def _frame(n=252):
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    close = pd.Series(np.linspace(100, 150, n), index=idx)
    return pd.DataFrame({"close": close}, index=idx)


def test_backtest_long_only_matches_buyhold_when_always_long():
    df = _frame()
    always = pd.Series(1, index=df.index)
    res = run_backtest(df, always, initial_capital=100_000)
    # Always-long equity should end near buy&hold return of the price path.
    ret = df["close"].iloc[-1] / df["close"].iloc[0] - 1
    assert abs((res.equity.iloc[-1] / 100_000 - 1) - ret) < 1e-6


def test_flat_signal_keeps_capital_flat():
    df = _frame()
    flat = pd.Series(0, index=df.index)
    res = run_backtest(df, flat, initial_capital=100_000)
    assert abs(res.equity.iloc[-1] - 100_000) < 1e-6


def test_drawdown_is_non_positive():
    df = _frame()
    res = run_backtest(df, pd.Series(1, index=df.index), initial_capital=100_000)
    assert drawdown_series(res.equity).max() <= 1e-9


def test_metrics_keys_present():
    df = _frame()
    res = run_backtest(df, pd.Series(1, index=df.index), initial_capital=100_000)
    m = compute_metrics(res)
    for k in ("Total Return", "CAGR", "Volatility", "Sharpe", "Max Drawdown"):
        assert k in m
