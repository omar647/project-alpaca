"""Systematic strategies → target signals.

A *signal* is a target position in {0, 1} per symbol: 1 = hold a long position,
0 = be flat (cash). Long-only, no shorting. Two interchangeable strategies:

  * :class:`MACrossover` — **trend following**. Go long when a fast SMA is above
    a slow SMA; exit to cash when it crosses back below. Intuition: momentum
    persists — an uptrend (fast > slow) tends to continue, so the strategy rides
    it and steps aside in downtrends to dodge the worst drawdowns.

  * :class:`MLStrategy` — **model based**. Engineer technical features, compress
    them with PCA, and train a classifier to predict "next-day return > 0". Go
    long when the model's probability of an up day exceeds a threshold (0.60).
    Intuition: many weak technical signals, combined by a model, can tilt the
    odds of the next day slightly in its favour.

Each strategy exposes:
  * ``signal_series(bars)`` — a full 0/1 series over history (for the backtest).
  * ``latest_signal(bars)`` — the target for the most recent bar (for live).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .indicators import sma
from .ml_model import train_signal_model


@dataclass
class LatestSignal:
    symbol: str
    signal: int          # 1 = long, 0 = flat
    reason: str          # human-readable explanation for the UI/logs
    price: float
    detail: dict


class Strategy:
    """Common interface. Subclasses implement ``signal_series``."""

    name = "base"

    def signal_series(self, bars: pd.DataFrame) -> pd.Series:  # pragma: no cover
        raise NotImplementedError

    def latest_signal(self, symbol: str, bars: pd.DataFrame) -> LatestSignal:
        sig = self.signal_series(bars)
        last = int(sig.iloc[-1]) if len(sig) else 0
        price = float(bars["close"].iloc[-1])
        return LatestSignal(symbol=symbol, signal=last,
                            reason=self._describe(bars, last),
                            price=price, detail={})

    def _describe(self, bars: pd.DataFrame, last: int) -> str:  # pragma: no cover
        return "long" if last else "flat"


# --------------------------------------------------------------------------- #
class MACrossover(Strategy):
    name = "ma_crossover"

    def __init__(self, fast: int = 20, slow: int = 50, **_ignore):
        self.fast = int(fast)
        self.slow = int(slow)

    def signal_series(self, bars: pd.DataFrame) -> pd.Series:
        close = bars["close"]
        fast = sma(close, self.fast)
        slow = sma(close, self.slow)
        return (fast > slow).astype(int).fillna(0)

    def _describe(self, bars: pd.DataFrame, last: int) -> str:
        close = bars["close"]
        f = sma(close, self.fast).iloc[-1]
        s = sma(close, self.slow).iloc[-1]
        rel = "above" if f >= s else "below"
        return (f"SMA{self.fast}=${f:.2f} {rel} SMA{self.slow}=${s:.2f} → "
                f"{'LONG' if last else 'FLAT'}")


# --------------------------------------------------------------------------- #
class MLStrategy(Strategy):
    name = "ml"

    def __init__(self, model: str = "gradient_boosting", threshold: float = 0.60, **_ignore):
        self.model = model
        self.threshold = float(threshold)
        self._cache: dict[int, object] = {}

    def _fit(self, bars: pd.DataFrame):
        key = len(bars)
        if key not in self._cache:
            self._cache[key] = train_signal_model(
                bars, model=self.model, threshold=self.threshold, test_size=0.30
            )
        return self._cache[key]

    def signal_series(self, bars: pd.DataFrame) -> pd.Series:
        sm = self._fit(bars)
        # Signal over the held-out test window; flat (0) elsewhere so the
        # backtest only credits out-of-sample decisions.
        full = pd.Series(0, index=bars.index)
        full.loc[sm.signal.index] = sm.signal.values
        return full

    def latest_signal(self, symbol: str, bars: pd.DataFrame) -> LatestSignal:
        sm = self._fit(bars)
        info = sm.latest_signal()
        return LatestSignal(
            symbol=symbol, signal=int(info["signal"]),
            reason=f"P(up)={info['probability']:.3f} vs {self.threshold:.2f} → {info['label']}",
            price=float(info["close"]), detail=info,
        )


# --------------------------------------------------------------------------- #
def make_strategy(name: str, params: dict | None = None) -> Strategy:
    """Factory used by the engine/backtest to build the configured strategy."""
    params = params or {}
    name = (name or "ma_crossover").lower()
    if name in ("ma_crossover", "ma", "trend"):
        return MACrossover(**params)
    if name in ("ml", "model"):
        return MLStrategy(**params)
    raise ValueError(f"Unknown strategy {name!r} (use 'ma_crossover' or 'ml').")
