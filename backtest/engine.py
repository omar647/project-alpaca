"""Reusable long-only backtesting engine.

Assumptions: initial capital $100,000, long-only, no leverage, no shorting.
A target-position series (1 = fully invested, 0 = all cash) is applied on the
*next* bar to avoid look-ahead bias.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class BacktestResult:
    equity: pd.Series          # portfolio value over time
    returns: pd.Series         # daily strategy returns
    position: pd.Series        # 0/1 position actually held each day
    trades: pd.DataFrame       # one row per completed round-trip trade
    initial_capital: float


def run_backtest(
    df: pd.DataFrame, signal: pd.Series, initial_capital: float = 100_000.0
) -> BacktestResult:
    """Backtest a 0/1 target-position ``signal`` on ``df['close']``."""
    price = df["close"]
    asset_ret = price.pct_change().fillna(0.0)

    # Act on the next bar (decision made at close of day t, executed day t+1).
    position = signal.shift(1).fillna(0.0).clip(0, 1)
    strat_ret = position * asset_ret
    equity = initial_capital * (1 + strat_ret).cumprod()

    trades = _extract_trades(price, position)
    return BacktestResult(
        equity=equity, returns=strat_ret, position=position,
        trades=trades, initial_capital=initial_capital,
    )


def _extract_trades(price: pd.Series, position: pd.Series) -> pd.DataFrame:
    """Identify round-trip trades (entry 0->1 ... exit 1->0) and their returns."""
    rows = []
    in_trade = False
    entry_date = entry_price = None
    for date, pos in position.items():
        if not in_trade and pos == 1:
            in_trade, entry_date, entry_price = True, date, price.loc[date]
        elif in_trade and pos == 0:
            exit_price = price.loc[date]
            rows.append({
                "entry_date": entry_date, "exit_date": date,
                "entry_price": entry_price, "exit_price": exit_price,
                "return": exit_price / entry_price - 1,
            })
            in_trade = False
    # Close any open trade at the last price (mark-to-market).
    if in_trade:
        exit_price = price.iloc[-1]
        rows.append({
            "entry_date": entry_date, "exit_date": price.index[-1],
            "entry_price": entry_price, "exit_price": exit_price,
            "return": exit_price / entry_price - 1,
        })
    return pd.DataFrame(rows)
