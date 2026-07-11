"""Load the non-secret system configuration from ``config/config.yaml``.

Everything tunable (universe, strategy choice, risk limits, engine cadence)
lives in the YAML so nothing operational is hard-coded. Secrets stay in .env
(see :mod:`config.settings`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG_PATH = os.path.join(_HERE, "config.yaml")


@dataclass
class RiskConfig:
    max_position_pct: float = 0.15
    max_gross_exposure: float = 1.0
    max_position_usd: float = 20_000
    stop_loss_pct: float = 0.08
    take_profit_pct: float = 0.20


@dataclass
class StrategyConfig:
    name: str = "ma_crossover"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineConfig:
    starting_equity: float = 100_000
    poll_seconds: int = 60
    order_type: str = "market"
    bars_lookback_days: int = 400


@dataclass
class BacktestConfig:
    years: int = 3
    timeframe: str = "day"


@dataclass
class Config:
    universe: list[str]
    strategy: StrategyConfig
    risk: RiskConfig
    engine: EngineConfig
    backtest: BacktestConfig
    raw: dict = field(default_factory=dict, repr=False)


def load_config(path: str = DEFAULT_CONFIG_PATH) -> Config:
    """Parse ``config.yaml`` into a typed :class:`Config`."""
    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    return Config(
        universe=[s.upper() for s in raw.get("universe", ["AAPL", "MSFT", "SPY"])],
        strategy=StrategyConfig(**{**{"name": "ma_crossover", "params": {}},
                                   **raw.get("strategy", {})}),
        risk=RiskConfig(**raw.get("risk", {})),
        engine=EngineConfig(**raw.get("engine", {})),
        backtest=BacktestConfig(**raw.get("backtest", {})),
        raw=raw,
    )
