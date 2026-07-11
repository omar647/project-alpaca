"""Data Connector Module.

Wraps Alpaca's Market Data API to:
  * download historical OHLCV bars (REST),
  * fetch the latest quote/trade snapshot (REST), and
  * stream real-time bid/ask quotes and trades (WebSocket) on a background thread.

All live updates land in a thread-safe :class:`LiveQuoteStore` that the UI polls.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd

from alpaca.data.enums import DataFeed
from alpaca.data.historical import (
    CryptoHistoricalDataClient,
    StockHistoricalDataClient,
)
from alpaca.data.live import CryptoDataStream, StockDataStream
from alpaca.data.requests import (
    CryptoBarsRequest,
    CryptoLatestQuoteRequest,
    CryptoLatestTradeRequest,
    StockBarsRequest,
    StockLatestQuoteRequest,
    StockLatestTradeRequest,
)
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from config.settings import Settings


def _feed(settings: Settings) -> DataFeed:
    return DataFeed.SIP if settings.data_feed.lower() == "sip" else DataFeed.IEX


def is_crypto(symbol: str) -> bool:
    """Crypto pairs are written with a slash, e.g. ``BTC/USD``. Stocks aren't."""
    return "/" in symbol


def _sane_quote(bid, ask, ref) -> bool:
    """Reject zero / crossed / absurd-spread quotes (common off-hours on IEX).

    A stale one-sided quote like bid=$0.01 / ask=$275 would otherwise corrupt the
    spread read-out and crater the chart's mid-price line.
    """
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return False
    mid = (bid + ask) / 2.0
    if (ask - bid) > 0.25 * mid:  # >25% spread → not a real two-sided market
        return False
    if ref and not (0.5 * ref <= mid <= 1.5 * ref):  # far from recent price → stale
        return False
    return True


# --------------------------------------------------------------------------- #
# Thread-safe store for the latest live values
# --------------------------------------------------------------------------- #
@dataclass
class LiveQuoteStore:
    """Holds the most recent bid/ask/last-trade for one symbol, thread-safely."""

    symbol: Optional[str] = None
    bid_price: Optional[float] = None
    ask_price: Optional[float] = None
    bid_size: Optional[float] = None
    ask_size: Optional[float] = None
    last_price: Optional[float] = None
    last_size: Optional[float] = None
    quote_time: Optional[datetime] = None
    trade_time: Optional[datetime] = None
    error: Optional[str] = None
    # Rolling intraday price series for the live chart: each entry is a dict
    # {"ts", "mid", "bid", "ask"}. Seeded from REST intraday bars, then extended
    # by every incoming quote so the line is continuous and never starts empty.
    _history: deque = field(default_factory=lambda: deque(maxlen=6000), repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def reset(self, symbol: str) -> None:
        with self._lock:
            self.symbol = symbol
            self.bid_price = self.ask_price = None
            self.bid_size = self.ask_size = None
            self.last_price = self.last_size = None
            self.quote_time = self.trade_time = None
            self.error = None
            self._history.clear()

    def seed_history(self, bars: "pd.DataFrame") -> None:
        """Prime the chart with recent intraday closes (bid/ask unknown → None)."""
        if bars is None or bars.empty:
            return
        seeded = [
            {"ts": row.timestamp, "mid": float(row.close), "bid": None, "ask": None}
            for row in bars.itertuples(index=False)
        ]
        with self._lock:
            existing = list(self._history)
            self._history.clear()
            self._history.extend(seeded)
            self._history.extend(existing)  # keep any live points captured already

    def update_quote(self, bid, ask, bid_size, ask_size, ts) -> None:
        with self._lock:
            ref = self._history[-1]["mid"] if self._history else self.last_price
            if not _sane_quote(bid, ask, ref):
                return  # ignore stale/garbage quotes so cards + chart stay clean
            self.bid_price, self.ask_price = bid, ask
            self.bid_size, self.ask_size = bid_size, ask_size
            self.quote_time = ts
            self._history.append(
                {"ts": ts, "mid": (bid + ask) / 2.0, "bid": bid, "ask": ask}
            )

    def update_trade(self, price, size, ts) -> None:
        with self._lock:
            self.last_price, self.last_size = price, size
            self.trade_time = ts

    def price_history(self) -> list:
        """Time-ordered copy of the rolling price series for the UI to plot."""
        with self._lock:
            return list(self._history)

    def set_error(self, message: str) -> None:
        with self._lock:
            self.error = message

    def snapshot(self) -> dict:
        """Return a plain-dict copy for the UI to render."""
        with self._lock:
            return {
                "symbol": self.symbol,
                "bid_price": self.bid_price,
                "ask_price": self.ask_price,
                "bid_size": self.bid_size,
                "ask_size": self.ask_size,
                "last_price": self.last_price,
                "last_size": self.last_size,
                "spread": (
                    round(self.ask_price - self.bid_price, 4)
                    if self.bid_price is not None and self.ask_price is not None
                    else None
                ),
                "quote_time": self.quote_time,
                "trade_time": self.trade_time,
                "error": self.error,
            }


# --------------------------------------------------------------------------- #
# Connector
# --------------------------------------------------------------------------- #
class AlpacaConnector:
    """Historical + live market data access for a single Alpaca account."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.feed = _feed(settings)
        self._hist = StockHistoricalDataClient(settings.api_key, settings.secret_key)
        self._crypto_hist = CryptoHistoricalDataClient(settings.api_key, settings.secret_key)
        self._stream = None  # StockDataStream or CryptoDataStream
        self._thread: Optional[threading.Thread] = None

    # ----------------------- Daily bars (for signals) --------------------- #
    def get_daily_bars(self, symbol: str, days: int = 400) -> pd.DataFrame:
        """Daily OHLCV bars indexed by date — the input to strategy signals.

        Returns columns: open, high, low, close, volume (indexed by naive date).
        """
        symbol = symbol.upper().strip()
        start = datetime.now(timezone.utc) - timedelta(days=days)
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=start,
            feed=self.feed,
        )
        bars = self._hist.get_stock_bars(request)
        df = bars.df
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.reset_index()
        if "symbol" in df.columns:
            df = df[df["symbol"] == symbol].drop(columns="symbol")
        df = df.rename(columns={"timestamp": "date"}).set_index("date")
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df[["open", "high", "low", "close", "volume"]]

    # ----------------------- Historical (REST) ---------------------------- #
    def get_historical_bars(
        self, symbol: str, days: int = 30, timeframe_minutes: int = 5
    ) -> pd.DataFrame:
        """Download OHLCV bars for ``symbol`` over the last ``days`` days.

        Returns a tidy DataFrame with columns:
        timestamp, open, high, low, close, volume (and trade_count, vwap).
        """
        symbol = symbol.upper().strip()
        timeframe = TimeFrame(timeframe_minutes, TimeFrameUnit.Minute)
        start = datetime.now(timezone.utc) - timedelta(days=days)

        if is_crypto(symbol):
            request = CryptoBarsRequest(
                symbol_or_symbols=symbol, timeframe=timeframe, start=start,
            )
            bars = self._crypto_hist.get_crypto_bars(request)
        else:
            request = StockBarsRequest(
                symbol_or_symbols=symbol, timeframe=timeframe, start=start, feed=self.feed,
            )
            bars = self._hist.get_stock_bars(request)
        df = bars.df  # MultiIndex (symbol, timestamp)
        if df is None or df.empty:
            return pd.DataFrame()

        df = df.reset_index()
        if "symbol" in df.columns:
            df = df[df["symbol"] == symbol].drop(columns="symbol")
        return df.reset_index(drop=True)

    def get_intraday_bars(self, symbol: str, minutes: int = 1) -> pd.DataFrame:
        """Recent 1-/5-minute bars used to seed the live chart so it's never empty.

        Pulls a couple of days back and keeps the most recent session's worth of
        points; off-hours this surfaces the last active session.
        """
        df = self.get_historical_bars(symbol, days=2, timeframe_minutes=minutes)
        if df is None or df.empty:
            return pd.DataFrame()
        return df.tail(390).reset_index(drop=True)

    def get_latest_snapshot(self, symbol: str) -> dict:
        """One-shot latest quote + trade via REST (works even when streaming is idle)."""
        symbol = symbol.upper().strip()
        out: dict = {"symbol": symbol}
        crypto = is_crypto(symbol)
        try:
            if crypto:
                q = self._crypto_hist.get_crypto_latest_quote(
                    CryptoLatestQuoteRequest(symbol_or_symbols=symbol)
                )[symbol]
            else:
                q = self._hist.get_stock_latest_quote(
                    StockLatestQuoteRequest(symbol_or_symbols=symbol, feed=self.feed)
                )[symbol]
            out.update(
                bid_price=q.bid_price,
                ask_price=q.ask_price,
                bid_size=q.bid_size,
                ask_size=q.ask_size,
                quote_time=q.timestamp,
            )
        except Exception as exc:  # noqa: BLE001 — surfaced in the UI
            out["error"] = f"quote: {exc}"
        try:
            if crypto:
                t = self._crypto_hist.get_crypto_latest_trade(
                    CryptoLatestTradeRequest(symbol_or_symbols=symbol)
                )[symbol]
            else:
                t = self._hist.get_stock_latest_trade(
                    StockLatestTradeRequest(symbol_or_symbols=symbol, feed=self.feed)
                )[symbol]
            out.update(last_price=t.price, last_size=t.size, trade_time=t.timestamp)
        except Exception as exc:  # noqa: BLE001
            out["error"] = f"{out.get('error', '')} trade: {exc}".strip()
        return out

    # ----------------------- Live (WebSocket) ----------------------------- #
    def start_stream(self, symbol: str, store: LiveQuoteStore) -> None:
        """Subscribe to live quotes + trades for ``symbol`` on a daemon thread.

        Any existing stream is stopped first so we only ever stream one symbol.
        """
        symbol = symbol.upper().strip()
        self.stop_stream()
        store.reset(symbol)

        if is_crypto(symbol):
            stream = CryptoDataStream(self.settings.api_key, self.settings.secret_key)
        else:
            stream = StockDataStream(
                self.settings.api_key, self.settings.secret_key, feed=self.feed
            )

        async def on_quote(q):
            store.update_quote(
                bid=q.bid_price,
                ask=q.ask_price,
                bid_size=q.bid_size,
                ask_size=q.ask_size,
                ts=q.timestamp,
            )

        async def on_trade(t):
            store.update_trade(price=t.price, size=t.size, ts=t.timestamp)

        stream.subscribe_quotes(on_quote, symbol)
        stream.subscribe_trades(on_trade, symbol)

        def runner():
            try:
                stream.run()  # blocking; runs its own asyncio loop
            except Exception as exc:  # noqa: BLE001
                store.set_error(str(exc))

        self._stream = stream
        self._thread = threading.Thread(target=runner, name="alpaca-stream", daemon=True)
        self._thread.start()

    def stop_stream(self) -> None:
        """Stop the live stream and let its thread wind down."""
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception:  # noqa: BLE001 — stop is best-effort
                pass
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._stream = None
        self._thread = None

    @property
    def is_streaming(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
