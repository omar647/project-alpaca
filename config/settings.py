"""Secret settings — Alpaca API keys, loaded from the environment / .env.

Nothing secret is ever hard-coded or committed. Copy ``.env.example`` to
``.env`` and paste your Alpaca **paper** keys there (``.env`` is git-ignored).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# Alpaca paper-trading REST endpoint. This project NEVER points at the live endpoint.
PAPER_BASE_URL = "https://paper-api.alpaca.markets"


@dataclass(frozen=True)
class Settings:
    """Alpaca credentials + data feed, sourced from environment variables."""

    api_key: str
    secret_key: str
    data_feed: str = "iex"  # "iex" (free) or "sip" (paid)
    paper: bool = True       # hard default — this project is paper-only

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key) and bool(self.secret_key)


def load_settings() -> Settings:
    """Build :class:`Settings` from the environment, or raise a helpful error."""
    settings = Settings(
        api_key=os.getenv("ALPACA_API_KEY", "").strip(),
        secret_key=os.getenv("ALPACA_SECRET_KEY", "").strip(),
        data_feed=os.getenv("ALPACA_DATA_FEED", "iex").strip() or "iex",
        paper=True,
    )
    if not settings.is_configured:
        raise RuntimeError(
            "Alpaca API keys not found. Copy .env.example to .env and set "
            "ALPACA_API_KEY and ALPACA_SECRET_KEY (use your *paper* keys)."
        )
    return settings
