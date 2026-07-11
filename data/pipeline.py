"""Data pipeline: continuously collect quotes for the universe and store them.

Two roles:
  * :class:`DataPipeline` — thin façade over :class:`AlpacaConnector` giving the
    rest of the system daily bars (for signals/backtest) and latest quotes.
  * :class:`QuoteCollector` — a background thread that polls the whole universe
    on a fixed cadence, stores each snapshot in a thread-safe table + appends to
    a CSV, and logs every update (timestamp / price / volume-ish size).

REST polling (rather than a websocket per symbol) keeps this robust off-hours,
which matters for a live demo — Alpaca still returns the last known quote.
"""

from __future__ import annotations

import csv
import os
import threading
import time
from datetime import datetime, timezone

import pandas as pd

from config.settings import Settings
from logutil import EventLog
from .connector import AlpacaConnector

_STORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "store")
os.makedirs(_STORE_DIR, exist_ok=True)
QUOTES_CSV = os.path.join(_STORE_DIR, "quotes.csv")


class DataPipeline:
    """Façade the strategy/backtest/engine use to get market data."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.connector = AlpacaConnector(settings)

    def daily_bars(self, symbol: str, days: int = 400) -> pd.DataFrame:
        return self.connector.get_daily_bars(symbol, days=days)

    def latest_quote(self, symbol: str) -> dict:
        """Latest bid/ask/last snapshot for one symbol (REST)."""
        return self.connector.get_latest_snapshot(symbol)

    def snapshot_universe(self, universe: list[str]) -> dict[str, dict]:
        """One-shot latest quote for every symbol in the universe."""
        return {sym: self.latest_quote(sym) for sym in universe}


class QuoteStore:
    """Thread-safe table of the latest quote per symbol."""

    def __init__(self):
        self._rows: dict[str, dict] = {}
        self._lock = threading.Lock()

    def update(self, symbol: str, quote: dict) -> None:
        with self._lock:
            self._rows[symbol] = quote

    def all(self) -> dict[str, dict]:
        with self._lock:
            return dict(self._rows)

    def as_frame(self) -> pd.DataFrame:
        rows = self.all()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).T
        return df


class QuoteCollector:
    """Background poller: snapshots the universe every ``interval`` seconds."""

    def __init__(
        self,
        pipeline: DataPipeline,
        universe: list[str],
        log: EventLog,
        interval: int = 60,
        store: QuoteStore | None = None,
    ):
        self.pipeline = pipeline
        self.universe = universe
        self.log = log
        self.interval = interval
        self.store = store or QuoteStore()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # -------------------------- lifecycle -------------------------------- #
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="quote-collector", daemon=True)
        self._thread.start()
        self.log.info(f"Data pipeline started — polling {len(self.universe)} symbols "
                      f"every {self.interval}s")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        self.log.info("Data pipeline stopped")

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # --------------------------- internals ------------------------------- #
    def poll_once(self) -> None:
        """Fetch every symbol once, store it, log it, append to CSV."""
        stamp = datetime.now(timezone.utc)
        new_rows = []
        for sym in self.universe:
            try:
                q = self.pipeline.latest_quote(sym)
            except Exception as exc:  # noqa: BLE001 — keep the loop alive
                self.log.error(f"quote fetch failed for {sym}: {exc}")
                continue
            self.store.update(sym, q)
            price = q.get("last_price") or q.get("bid_price")
            size = q.get("last_size") or q.get("bid_size")
            if price is not None:
                self.log.data(f"{sym}: ${price:.2f}  size={size}")
                new_rows.append({
                    "time": stamp.isoformat(), "symbol": sym, "price": price,
                    "bid": q.get("bid_price"), "ask": q.get("ask_price"), "size": size,
                })
        _append_csv(QUOTES_CSV, new_rows)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.poll_once()
            self._stop.wait(self.interval)


def _append_csv(path: str, rows: list[dict]) -> None:
    if not rows:
        return
    exists = os.path.exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        if not exists:
            writer.writeheader()
        writer.writerows(rows)
