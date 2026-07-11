"""Shared logging: a rotating file log + an in-memory event log for the UI.

Every meaningful event (data update, signal, order, fill, risk block, error) is
pushed to a thread-safe :class:`EventLog`. The engine writes to it; the UI reads
from it. The same events are also mirrored to ``logs/system.log``.
"""

from __future__ import annotations

import logging
import os
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(_HERE, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# ----------------------------- file logger -------------------------------- #
_file_logger = logging.getLogger("project_alpaca")
if not _file_logger.handlers:
    _file_logger.setLevel(logging.INFO)
    _fh = logging.FileHandler(os.path.join(LOG_DIR, "system.log"))
    _fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s"))
    _file_logger.addHandler(_fh)


@dataclass
class Event:
    time: datetime
    kind: str        # DATA | SIGNAL | ORDER | FILL | RISK | INFO | ERROR
    message: str

    def as_row(self) -> dict:
        return {
            "time": self.time.astimezone().strftime("%H:%M:%S"),
            "kind": self.kind,
            "message": self.message,
        }


class EventLog:
    """Thread-safe ring buffer of recent events, shared engine ↔ UI."""

    def __init__(self, maxlen: int = 500):
        self._events: deque[Event] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def add(self, kind: str, message: str) -> None:
        ev = Event(datetime.now(timezone.utc), kind.upper(), message)
        with self._lock:
            self._events.append(ev)
        level = logging.ERROR if kind.upper() == "ERROR" else logging.INFO
        _file_logger.log(level, "[%s] %s", ev.kind, message)

    # convenience shortcuts
    def data(self, m: str) -> None: self.add("DATA", m)
    def signal(self, m: str) -> None: self.add("SIGNAL", m)
    def order(self, m: str) -> None: self.add("ORDER", m)
    def fill(self, m: str) -> None: self.add("FILL", m)
    def risk(self, m: str) -> None: self.add("RISK", m)
    def info(self, m: str) -> None: self.add("INFO", m)
    def error(self, m: str) -> None: self.add("ERROR", m)

    def recent(self, n: int = 100, kinds: tuple[str, ...] | None = None) -> list[Event]:
        with self._lock:
            evs = list(self._events)
        if kinds:
            evs = [e for e in evs if e.kind in kinds]
        return evs[-n:][::-1]  # most recent first


# A process-wide default log so the UI and engine share one instance.
GLOBAL_LOG = EventLog()
