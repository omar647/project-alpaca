"""Performance metrics for a backtest result."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import BacktestResult

TRADING_DAYS = 252


def drawdown_series(equity: pd.Series) -> pd.Series:
    """Running drawdown (<= 0) of an equity curve."""
    return equity / equity.cummax() - 1.0


def compute_metrics(result: BacktestResult, risk_free: float = 0.0) -> dict:
    equity = result.equity
    ret = result.returns
    n = len(equity)
    years = n / TRADING_DAYS if n else np.nan

    total_return = equity.iloc[-1] / equity.iloc[0] - 1 if n else np.nan
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1 if years else np.nan

    vol = ret.std() * np.sqrt(TRADING_DAYS)
    excess = ret - risk_free / TRADING_DAYS
    sharpe = excess.mean() / ret.std() * np.sqrt(TRADING_DAYS) if ret.std() > 0 else np.nan

    downside = ret[ret < 0].std()
    sortino = excess.mean() / downside * np.sqrt(TRADING_DAYS) if downside and downside > 0 else np.nan

    max_dd = drawdown_series(equity).min()

    trades = result.trades
    win_rate = (trades["return"] > 0).mean() if len(trades) else np.nan

    return {
        "Total Return": total_return,
        "CAGR": cagr,
        "Volatility": vol,
        "Sharpe": sharpe,
        "Sortino": sortino,
        "Max Drawdown": max_dd,
        "Win Rate": win_rate,
        "Trades": len(trades),
    }


def metrics_table(results: dict[str, BacktestResult]) -> pd.DataFrame:
    """Build a comparison table (one row per strategy)."""
    rows = {name: compute_metrics(res) for name, res in results.items()}
    table = pd.DataFrame(rows).T
    # Pretty formatting
    pct = ["Total Return", "CAGR", "Volatility", "Max Drawdown", "Win Rate"]
    fmt = table.copy()
    for col in pct:
        fmt[col] = (fmt[col] * 100).map(lambda x: f"{x:.2f}%")
    for col in ["Sharpe", "Sortino"]:
        fmt[col] = fmt[col].map(lambda x: f"{x:.2f}")
    fmt["Trades"] = table["Trades"].astype(int)
    return fmt
