"""Backtest mode — run the configured strategy over historical data.

Runs the *same* strategy object used live against historical daily bars, so
backtest and paper trading share one code path. Produces, per symbol and for an
equal-weight portfolio: cumulative P&L, drawdown, number of trades, and hit
rate, benchmarked against Buy & Hold.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from config.config import Config
from config.settings import Settings
from data.pipeline import DataPipeline
from strategy.signals import Strategy, make_strategy
from .engine import BacktestResult, run_backtest
from .metrics import compute_metrics, drawdown_series


@dataclass
class BacktestReport:
    per_symbol: dict[str, dict]           # symbol -> {"strategy": metrics, "buyhold": metrics}
    strategy_equity: pd.Series            # equal-weight portfolio equity (strategy)
    buyhold_equity: pd.Series             # equal-weight portfolio equity (buy & hold)
    strategy_metrics: dict                # portfolio-level metrics (strategy)
    buyhold_metrics: dict                 # portfolio-level metrics (buy & hold)
    results: dict[str, BacktestResult]    # raw per-symbol strategy results


def run_backtest_mode(
    settings: Settings, config: Config, strategy: Strategy | None = None,
    days: int | None = None,
) -> BacktestReport:
    pipeline = DataPipeline(settings)
    strategy = strategy or make_strategy(config.strategy.name, config.strategy.params)
    days = days or int(config.backtest.years * 365.25)
    capital = config.engine.starting_equity
    per_name_capital = capital / max(1, len(config.universe))

    per_symbol: dict[str, dict] = {}
    results: dict[str, BacktestResult] = {}
    strat_curves, bh_curves = [], []

    for symbol in config.universe:
        bars = pipeline.daily_bars(symbol, days=days)
        if bars is None or bars.empty or len(bars) < 60:
            continue
        signal = strategy.signal_series(bars)
        strat_res = run_backtest(bars, signal, initial_capital=per_name_capital)
        bh_res = run_backtest(bars, pd.Series(1, index=bars.index),
                              initial_capital=per_name_capital)
        results[symbol] = strat_res
        per_symbol[symbol] = {
            "strategy": compute_metrics(strat_res),
            "buyhold": compute_metrics(bh_res),
        }
        strat_curves.append(strat_res.equity.rename(symbol))
        bh_curves.append(bh_res.equity.rename(symbol))

    # Equal-weight portfolio = sum of per-name equities (aligned on dates).
    strat_equity = _combine(strat_curves)
    bh_equity = _combine(bh_curves)

    return BacktestReport(
        per_symbol=per_symbol,
        strategy_equity=strat_equity,
        buyhold_equity=bh_equity,
        strategy_metrics=_portfolio_metrics(strat_equity, results),
        buyhold_metrics=_portfolio_metrics(bh_equity, {}),
        results=results,
    )


def _combine(curves: list[pd.Series]) -> pd.Series:
    if not curves:
        return pd.Series(dtype=float)
    df = pd.concat(curves, axis=1).ffill().dropna(how="all")
    return df.sum(axis=1)


def _portfolio_metrics(equity: pd.Series, results: dict[str, BacktestResult]) -> dict:
    if equity.empty:
        return {}
    ret = equity.pct_change().fillna(0.0)
    TRADING_DAYS = 252
    years = len(equity) / TRADING_DAYS
    total_return = equity.iloc[-1] / equity.iloc[0] - 1
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1 if years > 0 else float("nan")
    vol = ret.std() * (TRADING_DAYS ** 0.5)
    sharpe = ret.mean() / ret.std() * (TRADING_DAYS ** 0.5) if ret.std() > 0 else float("nan")
    max_dd = drawdown_series(equity).min()

    # Trade count + hit rate aggregated across symbols (strategy only).
    trades = pd.concat([r.trades for r in results.values()]) if results else pd.DataFrame()
    n_trades = len(trades)
    hit_rate = (trades["return"] > 0).mean() if n_trades else float("nan")

    return {
        "Total Return": total_return, "CAGR": cagr, "Volatility": vol,
        "Sharpe": sharpe, "Max Drawdown": max_dd,
        "Trades": n_trades, "Hit Rate": hit_rate,
    }
