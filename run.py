"""Command-line entry point for project-alpaca (no UI).

    python run.py backtest                 # run the configured strategy on history
    python run.py backtest --years 3 --strategy ml
    python run.py paper --cycles 1         # run N live paper-trading cycles then exit
    python run.py paper                     # run the live loop until Ctrl-C

The UI (`streamlit run ui/app.py`) is the primary interface; this CLI is handy
for backtests, cron jobs, and quick smoke tests. Paper mode is Alpaca paper only.
"""

from __future__ import annotations

import argparse
import time

from config.config import load_config
from config.settings import load_settings
from logutil import GLOBAL_LOG
from backtest.runner import run_backtest_mode
from execution.engine import TradingEngine
from strategy.signals import make_strategy


def cmd_backtest(args) -> None:
    cfg = load_config()
    if args.strategy:
        cfg.strategy.name = args.strategy
    strat = make_strategy(cfg.strategy.name, cfg.strategy.params)
    print(f"Backtesting '{cfg.strategy.name}' over {args.years}y on "
          f"{len(cfg.universe)} symbols…")
    rep = run_backtest_mode(load_settings(), cfg, strategy=strat,
                            days=int(args.years * 365.25))
    m, b = rep.strategy_metrics, rep.buyhold_metrics

    def line(name, d):
        return (f"{name:12s} TotRet {d.get('Total Return', 0)*100:7.2f}%  "
                f"CAGR {d.get('CAGR', 0)*100:6.2f}%  Sharpe {d.get('Sharpe', 0):5.2f}  "
                f"MaxDD {d.get('Max Drawdown', 0)*100:6.2f}%  "
                f"Trades {d.get('Trades', 0):3d}  Hit {d.get('Hit Rate', 0)*100:4.0f}%")

    print("\n=== Portfolio (equal-weight) ===")
    print(line("Strategy", m))
    print(line("Buy&Hold", b))
    print("\n=== Per symbol (total return) ===")
    for s, r in rep.per_symbol.items():
        print(f"  {s:6s} strategy {r['strategy']['Total Return']*100:7.2f}%   "
              f"buy&hold {r['buyhold']['Total Return']*100:7.2f}%")


def cmd_paper(args) -> None:
    cfg = load_config()
    if args.strategy:
        cfg.strategy.name = args.strategy
    engine = TradingEngine(load_settings(), cfg, GLOBAL_LOG)
    acct = engine.broker.account()
    print(f"Connected to PAPER account {acct['account_number']} "
          f"(equity ${acct['equity']:,.2f}). Strategy: {cfg.strategy.name}.")

    if args.cycles:
        for i in range(args.cycles):
            print(f"\n--- cycle {i + 1}/{args.cycles} ---")
            engine.run_once()
            for s in engine.state().symbols.values():
                print(f"  {s.symbol:6s} signal={s.signal} action={s.last_action}")
        return

    print("Running live loop (Ctrl-C to stop)…")
    engine.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        engine.stop()
        print("\nStopped.")


def main() -> None:
    ap = argparse.ArgumentParser(description="project-alpaca CLI (Alpaca paper trading)")
    sub = ap.add_subparsers(dest="command", required=True)

    bt = sub.add_parser("backtest", help="run the strategy on historical data")
    bt.add_argument("--years", type=float, default=3)
    bt.add_argument("--strategy", choices=["ma_crossover", "ml"], default=None)
    bt.set_defaults(func=cmd_backtest)

    pp = sub.add_parser("paper", help="run the live paper-trading engine")
    pp.add_argument("--cycles", type=int, default=0, help="run N cycles then exit (0 = loop)")
    pp.add_argument("--strategy", choices=["ma_crossover", "ml"], default=None)
    pp.set_defaults(func=cmd_paper)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
