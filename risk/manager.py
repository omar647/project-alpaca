"""Risk management — position sizing and pre-trade limit checks.

Enforced on every intended order *before* it reaches the broker:
  * max % of equity in any one name        (``max_position_pct``)
  * hard $ cap per name                     (``max_position_usd``)
  * max gross exposure / no leverage        (``max_gross_exposure``)

Plus post-trade monitoring of open positions:
  * stop-loss  — exit if a position is down ``stop_loss_pct`` from entry
  * take-profit — exit if a position is up ``take_profit_pct`` from entry
"""

from __future__ import annotations

from dataclasses import dataclass

from config.config import RiskConfig


@dataclass
class SizingDecision:
    approved: bool
    qty: int
    reason: str


class RiskManager:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg

    # ----------------------- position sizing ----------------------------- #
    def size_long(
        self,
        symbol: str,
        price: float,
        equity: float,
        current_position_value: float,
        gross_exposure: float,
        buying_power: float | None = None,
    ) -> SizingDecision:
        """Decide how many shares to BUY for a fresh long, within all limits.

        ``gross_exposure`` is the $ value of all current long positions.
        ``buying_power`` is Alpaca's actual available buying power — the order is
        also capped by it (with a small buffer) so the engine never submits an order
        the broker will reject for insufficient funds.
        """
        if price <= 0:
            return SizingDecision(False, 0, "invalid price")

        # Target notional = min(% cap, $ cap), minus the current holding.
        pct_cap = self.cfg.max_position_pct * equity
        target_notional = min(pct_cap, self.cfg.max_position_usd)
        room_in_name = max(0.0, target_notional - current_position_value)

        # Respect gross-exposure / no-leverage ceiling across the book.
        gross_cap = self.cfg.max_gross_exposure * equity
        room_gross = max(0.0, gross_cap - gross_exposure)

        budget = min(room_in_name, room_gross)

        # Never exceed real buying power (leave a 5% buffer for price slippage).
        if buying_power is not None:
            budget = min(budget, buying_power * 0.95)

        qty = int(budget // price)
        if qty < 1:
            bp_txt = f", buying power ${buying_power:,.0f}" if buying_power is not None else ""
            return SizingDecision(False, 0,
                                  f"no room (per-name ${room_in_name:,.0f}, "
                                  f"gross ${room_gross:,.0f}{bp_txt})")
        return SizingDecision(True, qty,
                              f"buy {qty} @ ${price:.2f} (${qty * price:,.0f})")

    # ----------------------- stop / take-profit -------------------------- #
    def exit_reason(self, entry_price: float, last_price: float) -> str | None:
        """Return 'stop-loss' / 'take-profit' if an open long should be closed."""
        if entry_price <= 0:
            return None
        ret = last_price / entry_price - 1.0
        if ret <= -self.cfg.stop_loss_pct:
            return f"stop-loss ({ret * 100:.1f}%)"
        if ret >= self.cfg.take_profit_pct:
            return f"take-profit (+{ret * 100:.1f}%)"
        return None
