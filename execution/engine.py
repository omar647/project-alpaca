"""Trading engine — turns strategy signals into paper orders on a loop.

Each cycle, for every symbol in the universe:
  1. pull daily bars (data pipeline)
  2. compute the strategy's target position (1 = long, 0 = flat)
  3. read the current position + account equity from the broker
  4. apply risk: stop-loss / take-profit can force an exit
  5. reconcile target vs. holding → a buy / sell / hold decision
  6. size the order via the RiskManager, submit it (paper), and log everything

Runs on a background daemon thread; the UI polls :meth:`state` for a snapshot.
The engine also drives the :class:`QuoteCollector` so "start" spins up both the
live data feed and the trading loop together.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone

from config.config import Config
from config.settings import Settings
from data.pipeline import DataPipeline, QuoteCollector, QuoteStore
from execution.broker import PaperBroker
from logutil import EventLog
from risk.manager import RiskManager
from strategy.signals import make_strategy


@dataclass
class SymbolState:
    symbol: str
    signal: int = 0
    reason: str = ""
    price: float = 0.0
    position_qty: float = 0.0
    last_action: str = "—"
    updated: datetime | None = None


@dataclass
class EngineState:
    running: bool = False
    mode: str = "paper"
    last_cycle: datetime | None = None
    cycles: int = 0
    account: dict = field(default_factory=dict)
    positions: dict = field(default_factory=dict)
    symbols: dict[str, SymbolState] = field(default_factory=dict)
    equity_curve: list = field(default_factory=list)  # (ts, equity)


class TradingEngine:
    def __init__(self, settings: Settings, config: Config, log: EventLog):
        self.settings = settings
        self.config = config
        self.log = log

        self.pipeline = DataPipeline(settings)
        self.broker = PaperBroker(settings)
        self.risk = RiskManager(config.risk)
        self.strategy = make_strategy(config.strategy.name, config.strategy.params)

        self.quote_store = QuoteStore()
        self.collector = QuoteCollector(
            self.pipeline, config.universe, log,
            interval=config.engine.poll_seconds, store=self.quote_store,
        )

        self._state = EngineState(mode="paper")
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ----------------------------- lifecycle ----------------------------- #
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.collector.start()
        self._thread = threading.Thread(target=self._run, name="trading-engine", daemon=True)
        self._thread.start()
        with self._lock:
            self._state.running = True
        self.log.info(f"Engine started — strategy '{self.strategy.name}', "
                      f"{len(self.config.universe)} symbols")

    def stop(self) -> None:
        self._stop.set()
        self.collector.stop()
        if self._thread:
            self._thread.join(timeout=3)
        with self._lock:
            self._state.running = False
        self.log.info("Engine stopped")

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------- loop -------------------------------- #
    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as exc:  # noqa: BLE001 — never let the loop die
                self.log.error(f"cycle error: {exc}")
            self._stop.wait(self.config.engine.poll_seconds)

    def run_once(self) -> None:
        """One full evaluation pass over the universe."""
        account = self.broker.account()
        positions = self.broker.positions()
        equity = account.get("equity", self.config.engine.starting_equity)
        gross = sum(p["market_value"] for p in positions.values())

        sym_states: dict[str, SymbolState] = {}
        for symbol in self.config.universe:
            state = self._evaluate_symbol(symbol, account, positions, equity, gross)
            sym_states[symbol] = state
            # keep gross exposure current as we add positions this cycle
            if state.last_action.startswith("BUY"):
                gross += state.position_qty * state.price

        with self._lock:
            self._state.account = account
            self._state.positions = self.broker.positions()  # refresh post-trades
            self._state.symbols = sym_states
            self._state.last_cycle = datetime.now(timezone.utc)
            self._state.cycles += 1
            self._state.equity_curve.append(
                (self._state.last_cycle, self.broker.account().get("equity", equity))
            )

    def _evaluate_symbol(self, symbol, account, positions, equity, gross) -> SymbolState:
        bars = self.pipeline.daily_bars(symbol, days=self.config.engine.bars_lookback_days)
        if bars is None or bars.empty or len(bars) < 60:
            return SymbolState(symbol, reason="insufficient data", updated=_now())

        ls = self.strategy.latest_signal(symbol, bars)
        held = positions.get(symbol)
        held_qty = held["qty"] if held else 0.0
        st = SymbolState(symbol, signal=ls.signal, reason=ls.reason,
                         price=ls.price, position_qty=held_qty, updated=_now())
        self.log.signal(f"{symbol}: {ls.reason}")

        # 1) risk exits take priority over the model.
        if held_qty > 0:
            reason = self.risk.exit_reason(held["avg_entry_price"], ls.price)
            if reason:
                res = self.broker.submit_market(symbol, held_qty, "sell")
                self._log_order(res, extra=f"risk exit — {reason}")
                st.last_action = f"SELL {held_qty:g} ({reason})"
                return st

        # 2) reconcile target vs. holding.
        if ls.signal == 1 and held_qty == 0:
            decision = self.risk.size_long(
                symbol, ls.price, equity,
                current_position_value=0.0, gross_exposure=gross,
            )
            if not decision.approved:
                self.log.risk(f"{symbol}: order blocked — {decision.reason}")
                st.last_action = f"BLOCKED ({decision.reason})"
                return st
            res = self.broker.submit_market(symbol, decision.qty, "buy")
            self._log_order(res, extra=decision.reason)
            st.position_qty = decision.qty
            st.last_action = f"BUY {decision.qty} @ ${ls.price:.2f}"
        elif ls.signal == 0 and held_qty > 0:
            res = self.broker.submit_market(symbol, held_qty, "sell")
            self._log_order(res, extra="signal flat")
            st.last_action = f"SELL {held_qty:g} (flat)"
        else:
            st.last_action = "HOLD" if held_qty > 0 else "—"
        return st

    def _log_order(self, res, extra: str = "") -> None:
        if res.ok:
            self.log.order(f"{res.side.upper()} {res.qty:g} {res.symbol} → "
                           f"{res.status} (id={res.order_id[:8] if res.order_id else '?'}) {extra}")
        else:
            self.log.error(f"order FAILED {res.side} {res.qty:g} {res.symbol}: {res.error}")

    # ------------------------------ readout ------------------------------ #
    def state(self) -> EngineState:
        with self._lock:
            return self._state


def _now() -> datetime:
    return datetime.now(timezone.utc)
