"""Unit tests for the risk manager (no network)."""

from config.config import RiskConfig
from risk.manager import RiskManager


def _rm():
    return RiskManager(RiskConfig(
        max_position_pct=0.15, max_gross_exposure=1.0, max_position_usd=20_000,
        stop_loss_pct=0.08, take_profit_pct=0.20,
    ))


def test_size_long_respects_pct_cap():
    d = _rm().size_long("X", price=100, equity=100_000,
                        current_position_value=0, gross_exposure=0)
    # 15% of 100k = $15k → 150 shares at $100.
    assert d.approved and d.qty == 150


def test_size_long_respects_usd_cap():
    # Huge equity → $ cap ($20k) binds, not the % cap.
    d = _rm().size_long("X", price=100, equity=10_000_000,
                        current_position_value=0, gross_exposure=0)
    assert d.qty == 200  # $20,000 / $100


def test_size_long_blocked_at_gross_cap():
    d = _rm().size_long("X", price=100, equity=100_000,
                        current_position_value=0, gross_exposure=100_000)
    assert not d.approved and d.qty == 0


def test_size_long_capped_by_buying_power():
    # % cap allows $15k, but only $2k buying power → ~19 shares (95% buffer).
    d = _rm().size_long("X", price=100, equity=100_000, current_position_value=0,
                        gross_exposure=0, buying_power=2_000)
    assert d.approved and d.qty == 19  # int(2000*0.95 / 100)


def test_size_long_blocked_when_no_buying_power():
    d = _rm().size_long("X", price=100, equity=100_000, current_position_value=0,
                        gross_exposure=0, buying_power=50)
    assert not d.approved and d.qty == 0


def test_stop_loss_and_take_profit():
    rm = _rm()
    assert rm.exit_reason(100, 91) and "stop" in rm.exit_reason(100, 91)
    assert rm.exit_reason(100, 121) and "take-profit" in rm.exit_reason(100, 121)
    assert rm.exit_reason(100, 105) is None
