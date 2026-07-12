"""Broker wrapper around Alpaca's PAPER trading API.

Every method is pinned to the paper endpoint via ``TradingClient(paper=True)``,
so this module can never touch a live account. It exposes just what the engine
needs: account snapshot, open positions, submit/cancel market orders, and order
status — with error handling so a bad order never crashes the loop.
"""

from __future__ import annotations

from dataclasses import dataclass

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, QueryOrderStatus, TimeInForce
from alpaca.trading.requests import GetOrdersRequest, MarketOrderRequest

from config.settings import Settings


@dataclass
class OrderResult:
    ok: bool
    symbol: str
    side: str
    qty: float
    status: str
    order_id: str | None
    error: str | None = None


class PaperBroker:
    """Thin, defensive wrapper over Alpaca paper trading."""

    def __init__(self, settings: Settings):
        # paper=True is non-negotiable for this project.
        self.client = TradingClient(settings.api_key, settings.secret_key, paper=True)

    # ----------------------------- account ------------------------------- #
    def account(self) -> dict:
        a = self.client.get_account()
        return {
            "account_number": a.account_number,
            "status": str(a.status),
            "equity": float(a.equity),
            "cash": float(a.cash),
            "buying_power": float(a.buying_power),
            "portfolio_value": float(a.portfolio_value),
            "long_market_value": float(getattr(a, "long_market_value", 0) or 0),
            "last_equity": float(getattr(a, "last_equity", 0) or 0),
        }

    def clock(self) -> dict:
        """Market clock: is it open, and when does it next open/close."""
        try:
            c = self.client.get_clock()
            return {"is_open": bool(c.is_open),
                    "next_open": c.next_open, "next_close": c.next_close}
        except Exception:  # noqa: BLE001
            return {"is_open": None, "next_open": None, "next_close": None}

    def positions(self) -> dict[str, dict]:
        """Map symbol → {qty, avg_entry_price, market_value, unrealized_pl, ...}."""
        out: dict[str, dict] = {}
        for p in self.client.get_all_positions():
            out[p.symbol] = {
                "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "market_value": float(p.market_value),
                "current_price": float(p.current_price),
                "unrealized_pl": float(p.unrealized_pl),
                "unrealized_plpc": float(p.unrealized_plpc),
            }
        return out

    def position_qty(self, symbol: str) -> float:
        try:
            return float(self.client.get_open_position(symbol).qty)
        except Exception:  # noqa: BLE001 — no open position
            return 0.0

    # ----------------------------- orders -------------------------------- #
    def submit_market(self, symbol: str, qty: float, side: str) -> OrderResult:
        """Submit a market order (paper). ``side`` is 'buy' or 'sell'."""
        order_side = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
        try:
            req = MarketOrderRequest(
                symbol=symbol, qty=qty, side=order_side, time_in_force=TimeInForce.DAY
            )
            o = self.client.submit_order(req)
            return OrderResult(True, symbol, side, qty, str(o.status), str(o.id))
        except Exception as exc:  # noqa: BLE001 — rejected/invalid/network
            return OrderResult(False, symbol, side, qty, "rejected", None, str(exc))

    def recent_orders(self, limit: int = 25) -> list[dict]:
        try:
            req = GetOrdersRequest(status=QueryOrderStatus.ALL, limit=limit)
            orders = self.client.get_orders(req)
        except Exception:  # noqa: BLE001
            return []
        rows = []
        for o in orders:
            rows.append({
                "symbol": o.symbol,
                "side": str(o.side).split(".")[-1].lower(),
                "qty": float(o.qty) if o.qty else None,
                "filled_qty": float(o.filled_qty) if o.filled_qty else 0.0,
                "status": str(o.status).split(".")[-1],
                "type": str(o.order_type).split(".")[-1],
                "submitted_at": o.submitted_at,
                "filled_avg_price": float(o.filled_avg_price) if o.filled_avg_price else None,
            })
        return rows

    def open_order_symbols(self) -> set[str]:
        """Symbols that currently have an open (unfilled) order.

        The engine skips new orders for these so a closed-market cycle can't
        re-submit the same buy every poll while fills are pending.
        """
        try:
            req = GetOrdersRequest(status=QueryOrderStatus.OPEN, limit=100)
            return {o.symbol for o in self.client.get_orders(req)}
        except Exception:  # noqa: BLE001
            return set()

    def cancel_all(self) -> None:
        try:
            self.client.cancel_orders()
        except Exception:  # noqa: BLE001
            pass
