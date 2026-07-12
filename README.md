# ▲ project-alpaca — Systematic Trading System (Alpaca, Paper Only)

An end-to-end, modular systematic trading system built on **Alpaca**. It collects
live market data, generates rule-based / model-based signals, sizes and routes
orders through a risk layer, and exposes a **Streamlit dashboard** to monitor and
control everything — running in **backtest** or **live paper trading** mode.

> ⚠️ **PAPER TRADING ONLY.** Every order is pinned to Alpaca's paper endpoint
> (`TradingClient(..., paper=True)`). No real money, no credit card, no live keys.

---

## 1. Overview & goals

Build a *real* trading system — not a notebook — with clean separation between
data, strategy, execution, risk, and UI, so the same strategy code runs
identically in a historical backtest and against a live Alpaca paper account.

**What it does**

- **Data pipeline** — continuously polls quotes for a configurable universe
  (5–20 tickers), stores them (thread-safe table + CSV), and logs every update.
- **Systematic strategy** — a trend-following **MA crossover** or a **PCA + Gradient
  Boosting ML** model; both emit a long/flat target per symbol.
- **Risk layer** — position sizing and pre-trade limit checks (per-name %, per-name
  $, gross exposure / no leverage) plus stop-loss / take-profit exits.
- **Execution engine** — reconciles targets vs. holdings into paper orders, handles
  order states and errors (an open unfilled order blocks re-submits for that
  symbol), and never lets a bad order crash the loop.
- **UI** — a dark terminal-style Streamlit dashboard: start/stop, mode switch, a
  live quote board (bid/ask/spread/age), signals, positions & P&L, orders, session
  equity + drawdown, performance metrics, and a live event log.

---

## 2. Architecture

```
                         ┌──────────────────────────────┐
                         │            config/            │
                         │  config.yaml (universe,       │
                         │  strategy, risk, engine)      │
                         │  settings.py (.env API keys)  │
                         └───────────────┬───────────────┘
                                         │
   ┌───────────────┐   daily bars /  ┌───▼───────────┐   signals   ┌──────────────┐
   │    data/      │───latest quotes─▶   strategy/    │────────────▶│    risk/     │
   │  connector    │                 │  signals.py    │  0/1 target │  manager.py  │
   │  pipeline     │◀──universe poll─┤  MA / ML       │             │ sizing+stops │
   │  (Alpaca API) │                 └────────────────┘             └──────┬───────┘
   └───────────────┘                                                       │ sized order
           ▲                          ┌──────────────────┐                 ▼
           │ market data              │   execution/     │◀────────────────┘
           │                          │   engine.py      │  buy / sell / hold
     Alpaca Market Data               │   broker.py ─────┼──▶ Alpaca PAPER orders
     + Paper Trading API              └────────┬─────────┘
                                               │ shared state + EventLog (logutil.py)
                                      ┌────────▼─────────┐
                                      │       ui/        │  Streamlit dashboard
                                      │     app.py       │  monitor + control
                                      └──────────────────┘

   backtest/ runs the SAME strategy on historical bars → metrics vs Buy & Hold
```

Everything shared between the engine (background thread) and the UI goes through
a thread-safe `EngineState` and a thread-safe `EventLog`.

**Folder structure**

```
project-alpaca/
├── run.py                 # CLI entry (backtest / paper)
├── logutil.py             # shared file log + in-memory EventLog
├── config/
│   ├── settings.py        # Alpaca keys from .env (never hard-coded)
│   ├── config.py          # typed loader for config.yaml
│   └── config.yaml         # universe, strategy, risk limits, engine cadence
├── data/
│   ├── connector.py       # Alpaca REST + WebSocket market data (from HW1)
│   └── pipeline.py        # universe quote collector + CSV store + logging
├── strategy/
│   ├── indicators.py      # 11 technical indicators (from HW2)
│   ├── features.py        # feature matrix (from HW3)
│   ├── pca.py             # StandardScaler + PCA (from HW3)
│   ├── ml_model.py        # gradient-boosting signal model (from HW3)
│   └── signals.py         # MACrossover + MLStrategy + factory
├── execution/
│   ├── broker.py          # Alpaca PAPER order/position/account wrapper
│   └── engine.py          # signals → orders loop (background thread)
├── risk/
│   └── manager.py         # sizing + limit checks + stop/take-profit
├── backtest/
│   ├── engine.py          # long-only backtest engine (from HW2)
│   ├── metrics.py         # performance metrics (from HW2)
│   └── runner.py          # run strategy over universe vs Buy & Hold
├── ui/
│   └── app.py             # Streamlit dashboard (paper + backtest modes)
├── tests/                 # pytest unit tests (indicators, signals, risk, backtest)
├── charts/                # committed backtest chart PNGs
└── screenshots/           # dashboard captures for the writeup
```

This project reuses the three earlier homeworks: **HW1** (Alpaca data connector +
Streamlit UI), **HW2** (indicators + backtest engine + metrics), **HW3** (features,
PCA, and the ML signal model).

---

## 3. Setup

```bash
cd project-alpaca
pip3 install -r requirements.txt      # macOS: use python3 / pip3

cp .env.example .env                  # then edit .env with your Alpaca PAPER keys
```

`.env` (git-ignored — never committed):

```
ALPACA_API_KEY=PK...your_paper_key...
ALPACA_SECRET_KEY=...your_paper_secret...
ALPACA_DATA_FEED=iex
```

Get **paper** keys at <https://app.alpaca.markets> → *Paper Trading* → *API Keys*.
Paper keys start with `PK`. Do not use live keys.

---

## 4. Running

### UI (primary interface)

```bash
streamlit run ui/app.py
```

- **Paper trading** mode: pick a strategy, press **▶ Start** — the engine spins up
  the live data feed + trading loop, connects to your Alpaca paper account, and the
  dashboard streams account/positions/P&L, signals, orders, and the event log.
  Press **■ Stop** to halt.
- **Backtest** mode: choose the strategy + years and press **Run backtest** to
  compare the strategy to Buy & Hold (equity + drawdown curves, metrics, and a
  per-symbol table).

### CLI (backtests, cron, smoke tests)

```bash
python3 run.py backtest --years 3 --strategy ma_crossover
python3 run.py backtest --years 3 --strategy ml
python3 run.py paper --cycles 1        # run one live paper cycle then exit
python3 run.py paper                    # run the live loop until Ctrl-C
```

---

## 5. Strategy & risk controls

### Strategies (in `config.yaml` → `strategy.name`)

**`ma_crossover` — trend following (default).**
Go **long** when the fast SMA is above the slow SMA (default 20/50); exit to cash
when it crosses back below. *Intuition:* momentum persists — an established uptrend
tends to continue, so the strategy rides it and steps aside in downtrends to dodge
the worst drawdowns.

**`ml` — model based.**
Engineer technical features → standardize → **PCA (≥80% variance)** → **Gradient
Boosting** classifier predicting *next-day return > 0*. Go long when `P(up) > 0.60`,
else flat. *Intuition:* many weak technical signals, combined by a model, can tilt
the odds of the next day slightly in its favour.

Both are **long-only** and emit a `{0, 1}` target per symbol, so backtest and live
share one signal path.

### Risk controls (in `config.yaml` → `risk`, enforced in `risk/manager.py`)

| Control | Default | Meaning |
|---|---|---|
| `max_position_pct` | 15% | Max % of equity in any one name |
| `max_position_usd` | $20,000 | Hard $ cap per name |
| `max_gross_exposure` | 100% | Max invested — **no leverage** |
| `stop_loss_pct` | 8% | Exit a position down 8% from entry |
| `take_profit_pct` | 20% | Exit a position up 20% from entry |

Every intended buy is sized to respect the per-name and gross caps *before* it
reaches the broker; open positions are checked each cycle for stop/take-profit
exits, which override the strategy.

---

## 6. Example results & walkthrough

**Backtest — equal-weight portfolio, MA crossover vs Buy & Hold (2 years):**

| | Total Return | CAGR | Sharpe | Max Drawdown | Trades | Hit Rate |
|---|---|---|---|---|---|---|
| **Strategy** | +42.2% | 19.4% | **1.31** | **−8.1%** | 39 | 54% |
| **Buy & Hold** | +62.6% | 27.8% | 1.08 | −25.1% | — | — |

The trend strategy trails on raw return in a bull market but delivers a **higher
Sharpe with a third of the drawdown** — the point of a systematic risk-managed
system. See `charts/backtest_equity.png` and `charts/backtest_drawdown.png`.

**Live paper cycle** (`python3 run.py paper --cycles 1`):

```
Connected to PAPER account PA3GL5RGH9D9 (equity $100,175.07). Strategy: ma_crossover.
--- cycle 1/1 ---
  AAPL   signal=1 action=BUY 47 @ $315.32
  QQQ    signal=1 action=BUY 20 @ $725.60
  AMD    signal=1 action=BUY 26 @ $557.85
  MSFT   signal=0 action=—
  ...
```

Each buy is risk-sized and routed to Alpaca paper; the order appears in the Alpaca
dashboard and in the app's **Recent orders** + **Event log**.

**The dashboard** (`streamlit run ui/app.py`):

![Paper trading dashboard](screenshots/dashboard_paper.png)
![Backtest view](screenshots/dashboard_backtest.png)

## Video

[![Watch the demo](https://img.youtube.com/vi/-NZ54breupE/hqdefault.jpg)](https://youtu.be/-NZ54breupE)
---

## 7. Configuration

All operational settings live in `config/config.yaml` (universe, strategy choice
and params, risk limits, engine cadence, backtest defaults). **Secrets never go
here** — API keys are read from `.env` via `config/settings.py`. The committed
`config.yaml` uses no secrets; `.env.example` ships with dummy placeholders.

---

## 8. Logging & monitoring

- **File log:** `logs/system.log` — every data update, signal, order, fill, risk
  block, and error, timestamped.
- **Quote store:** `data/store/quotes.csv` — appended each poll (time, symbol,
  price, bid/ask, size).
- **In-app event log** + **performance metrics:** cumulative P&L, drawdown, number
  of trades, and hit rate (win/loss).

---

## 9. Testing

```bash
python3 -m pytest tests/ -q       # 18 unit tests, no network required
```

Covers indicators, signal generation (trend up/down), risk sizing + stop/take-profit,
and the backtest engine.

---

## 10. Limitations & possible improvements

- **Free IEX feed**: limited history/quote depth and **not split-adjusted** — some
  older backtests (e.g. NVDA pre-split) look distorted; SIP or an adjusted feed
  fixes this.
- **Signals on daily bars**: the live loop re-evaluates on a poll cadence (default
  60s) but decisions are daily-bar based; intraday signals would need bar streaming.
- **Sizing** is simple (equal-ish, capped); no volatility targeting or portfolio
  optimization.
- **Partial fills** are displayed (filled qty / avg price) but not actively
  re-worked; an open unfilled order blocks new orders for that symbol until it
  resolves, and market orders in paper generally fill fully.
- **Improvements:** transaction-cost modeling, more strategies + an ensemble,
  richer position sizing (Kelly / vol-target), alerting, and persistent state.

---

> ⚠️ **Reminder:** this system uses Alpaca **paper trading only**. No real money.
