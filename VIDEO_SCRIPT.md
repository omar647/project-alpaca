# 🎬 Video Script — project-alpaca (Systematic Trading System on Alpaca)

**Target length:** 10–15 minutes. Read the **SAY** lines out loud; do the
**SHOW / DO** actions on screen.

> **What the grader needs to see (from the assignment):** the overall
> **architecture**, a **UI demo running in Alpaca paper trading**, and a clear
> description of **strategy logic, the data pipeline, and execution + risk**. Then
> a **reflection** on limitations, improvements, and what I learned. This script
> hits all of them in order.
>
> **This is a solo project — one person, first-person voice throughout.**

---

## 🗣️ How to say things out loud (quick reference)

So I don't trip over the names on camera:

- **project-alpaca** → say *"project alpaca"*
- **Alpaca** → *"alpaca"* (the word)
- **UI** → *"U-I"* (say the letters) or *"the dashboard"*
- **API** → *"A-P-I"* (letters)
- **MA crossover** → *"moving average crossover"* (the config calls it
  `ma_crossover`, but I say the full words)
- **SMA** → *"simple moving average"*, or *"S-M-A"* (letters) after I've said it once
- **ML** → *"machine learning"* (the strategy is named `ml`)
- **PCA** → *"P-C-A"* (letters) — it stands for principal component analysis
- **Gradient Boosting** → *"gradient boosting"* (words)
- **P(up)** → *"the probability of an up day"*
- **P&L** → *"P and L"*
- **CAGR** → *"compound annual growth rate"* (or say *"kagger"* if you like — but
  the full words are safest)
- **Sharpe** → *"sharpe"* (rhymes with "sharp")
- **IEX** → *"I-E-X"* (letters — it's the free data feed)
- **CSV** → *"C-S-V"* (letters)
- **.env** → *"dot E-N-V"* or *"the dot-env file"*

**Tickers — how I say each one:**
- **AAPL** → *"Apple"*
- **MSFT** → *"Microsoft"*
- **SPY** → *"spy"* (it's a word — the S&P 500 fund)
- **QQQ** → *"triple-Q"* (the Nasdaq 100 fund)
- **NVDA** → *"Nvidia"*
- **AMD** → *"A-M-D"* (letters)
- **GOOGL** → *"Google"*
- **META** → *"Meta"*

---

## 🎥 Before you hit record

- **Reset the paper account** for a clean slate: Alpaca dashboard → *Account →
  Reset* → back to $100,000 buying power and no leftover orders. (This also clears
  any old pending orders so the demo is clean.)
- Open the project in your editor:  `code .`  in the `project-alpaca/` folder.
- Open **two terminals** in `project-alpaca/`:
  - Terminal 1 for the dashboard: `streamlit run ui/app.py`
  - Terminal 2 for the tests + a quick command-line trade.
- Log in to your Alpaca **paper** dashboard in a browser tab
  (app.alpaca.markets → *Paper*).
- All commands use `python3` (on macOS `python` won't work).

---

## 0 · Intro & disclaimer (0:00–0:40)

**SAY:**
> "Hi — this is my project, **project alpaca**: a full, end-to-end systematic
> trading system I built on **Alpaca**. It streams live market data, generates
> rule-based and machine-learning signals, sizes and routes orders through a risk
> layer, and it's all controlled from a live dashboard — running in either a
> historical **backtest** or against a live **Alpaca paper account**.
> **Everything is paper trading only — no real money, no credit card, no live
> keys.** Every order is pinned to Alpaca's paper endpoint in code.
> In this video I'll walk through the architecture, the data pipeline, the two
> strategies, execution and risk, then demo the whole thing running live, and
> finish with what I learned."

**SHOW:** the project folder open in your editor, and the README title.

---

## 1 · Architecture overview (0:40–2:40)

**DO:** Open the README and scroll to the architecture diagram. Then show the
folder tree in the editor sidebar.

**SAY:**
> "My goal was to build a *real* system, not a notebook — so it's split into clean
> modules that each do one job, and the same strategy code runs identically in
> backtest and in live paper trading."

**DO:** Point at each top-level folder as you name it.

**SAY:**
> - "**config** holds everything tunable — the ticker universe, which strategy to
>   run, the risk limits, and the engine timing — in one `config.yaml` file. The
>   secret A-P-I keys live separately in a **dot-env** file that's never committed
>   to GitHub."
> - "**data** is the market-data pipeline — it talks to Alpaca and collects
>   quotes."
> - "**strategy** turns price data into a signal — that's the moving average
>   crossover and the machine-learning model."
> - "**risk** does position sizing and the pre-trade safety checks."
> - "**execution** is the trading engine — it takes the signals, checks risk, and
>   submits the actual paper orders through Alpaca."
> - "**backtest** runs that same strategy over history and scores it against Buy
>   and Hold."
> - "and **ui** is the dashboard that monitors and controls all of it."

**SAY (trace the data flow on the diagram):**
> "So the flow is: **data** pulls bars and quotes from Alpaca → **strategy** turns
> those into a target signal, either **long** or **flat**, for each symbol →
> **risk** sizes that into an order that respects the limits → **execution** sends
> it to the Alpaca paper account → and the **UI** reads shared state to show it
> all live. The engine runs on a background thread, and it talks to the dashboard
> through a thread-safe state object and an event log, so the interface never
> freezes while the engine is working."

**SAY:**
> "One more thing — there are **18 unit tests** covering the indicators, the
> signals, the risk sizing, and the backtest engine. Let me run those quickly to
> show the core logic is verified."

**DO:** In Terminal 2, run:

```bash
python3 -m pytest tests/ -q
```

**SHOW / SAY:** point at the green result.
> "All 18 pass, no network needed."

---

## 2 · The data pipeline (2:40–4:10)

**DO:** Open `data/pipeline.py` in the editor.

**SAY:**
> "The data pipeline has two parts. There's a **façade** that hands the rest of
> the system what it needs — daily bars for the signals, and the latest quote for
> each symbol. And there's a **background collector** that runs on its own thread."

**DO:** Scroll to the `QuoteCollector` class and the `poll_once` method.

**SAY:**
> "The collector polls the whole universe — my eight symbols: **Apple**,
> **Microsoft**, **spy**, **triple-Q**, **Nvidia**, **A-M-D**, **Google**, and
> **Meta** — every 60 seconds. For each symbol it grabs the latest quote, stores
> it in a thread-safe table, logs it with a timestamp, price, and size, and
> appends a row to a **C-S-V** file on disk. So there's a structured, growing
> record of everything the system saw."

**SAY:**
> "It's using Alpaca's free **I-E-X** feed. And notice the error handling — if a
> single quote fetch fails, it logs it and keeps going. One bad symbol never kills
> the whole loop. That robustness matters when you're running live."

**DO (optional):** Show `data/store/quotes.csv` if it has rows, or the connector
file `data/connector.py` briefly.

**SAY:**
> "Under the hood the connector wraps Alpaca's Market Data A-P-I — it can pull
> historical bars over REST and even stream live quotes over a websocket."

---

## 3 · Strategy logic (4:10–6:20)

**DO:** Open `strategy/signals.py`.

**SAY:**
> "I built two interchangeable strategies. Both are **long-only** and both output
> the same thing — a target of **1 for long** or **0 for flat** for each symbol —
> so the backtest and the live engine share one signal path. That's the key design
> choice: the code that decides a trade is *identical* whether I'm testing on
> history or trading live."

**SAY (Strategy 1 — MA crossover):**
> "The first strategy is the **moving average crossover** — it's trend following.
> It takes a fast **simple moving average**, 20 days by default, and a slow one, 50
> days. When the fast average is **above** the slow average, that's an uptrend, so
> it goes **long**. When it crosses back below, it goes to **cash**.
> The intuition is momentum: an established uptrend tends to keep going, so the
> strategy rides it, and steps aside in downtrends to dodge the worst drawdowns."

**DO:** Scroll to the `MLStrategy` class.

**SAY (Strategy 2 — ML):**
> "The second strategy is **machine learning**. It engineers a set of technical
> features, standardizes them, then runs **P-C-A** — principal component analysis
> — to compress them down to the components that explain at least 80% of the
> variance. Those components feed a **gradient boosting** classifier that predicts
> whether tomorrow's return will be positive. It goes **long** only when the
> probability of an up day is above **0.6**, otherwise it stays flat.
> The intuition there is that lots of individually-weak technical signals, combined
> by a model, can tilt the odds of the next day slightly in its favor."

**SAY:**
> "Both strategies expose the same two methods — one gives the full signal history
> for backtesting, and one gives the single latest signal for live trading. And
> importantly, the machine-learning signal in the backtest only counts decisions
> on a **held-out test window** the model never trained on, so it isn't fooling
> itself with look-ahead."

---

## 4 · Execution & risk management (6:20–8:00)

**DO:** Open `risk/manager.py`.

**SAY:**
> "Before any order goes out, it passes through the risk manager. There are three
> pre-trade checks. **One** — no more than 15% of equity in any single name.
> **Two** — a hard dollar cap of $20,000 per name. And **three** — total gross
> exposure can't exceed 100% of equity, which means **no leverage** — the system
> can never spend money it doesn't have. It also caps every order against the real
> buying power Alpaca reports, with a small buffer, so it doesn't submit an order
> the broker will reject."

**DO:** Scroll to the `exit_reason` method.

**SAY:**
> "And there are two exit rules that *override* the strategy: a **stop-loss** at
> minus 8% and a **take-profit** at plus 20% from the entry price. So even if the
> model still says hold, a position that's down 8% gets cut automatically."

**DO:** Open `execution/engine.py` and show the `run_once` / `_evaluate_symbol`
methods.

**SAY:**
> "The trading engine ties it together. Each cycle, for every symbol, it: pulls the
> latest bars, computes the strategy's target, reads the current position and
> account equity from Alpaca, applies the stop-loss and take-profit, and then
> reconciles the target against the current holding — that becomes a **buy**,
> **sell**, or **hold**. A buy gets risk-sized first, then submitted to the paper
> account."

**DO:** Open `execution/broker.py` and point at the `paper=True` line.

**SAY:**
> "Every order routes through this broker wrapper, and right here — the trading
> client is pinned to **paper equals true**. This module physically cannot touch a
> live account. Orders are wrapped in error handling, so a rejected or invalid
> order returns a clean result instead of crashing the loop. And if there's already
> an open, unfilled order for a symbol, it skips it — so it never stacks duplicate
> orders while one is waiting to fill."

---

## 5 · Demo — Backtest mode (8:00–10:00)

**DO:** In Terminal 1, launch the dashboard:

```bash
streamlit run ui/app.py
```

**DO:** In the browser, in the left sidebar pick **Backtest** mode. Leave the
strategy on `ma_crossover`.

**SAY:**
> "Here's the dashboard. Let me start in **Backtest** mode. I'll run the moving
> average crossover over the last 3 years across all eight symbols, equal-weighted,
> and compare it to just buying and holding."

**DO:** Press **▶ Run backtest**. Wait for it to load.

**SAY (point at the top metric strip):**
> "Here are the results. Up top: total return, **compound annual growth rate**,
> **sharpe** ratio, max drawdown, number of trades, and hit rate — each one shown
> next to the Buy-and-Hold number underneath for comparison."

*(Read your actual numbers off the screen. For reference, a recent 3-year run
showed the strategy around +50% total return with a 26% max drawdown, versus
Buy-and-Hold around +108% with a 33% drawdown.)*

**SAY (point at the equity curve, then the drawdown chart):**
> "This is the equity curve — the strategy in green, Buy and Hold as the dotted
> line. And below it, the drawdown chart. This is the honest story of a
> trend-following system: in a strong bull market like this one, stepping out
> during pullbacks means it **gives up some of the raw upside** — Buy and Hold wins
> on total return. But look at the drawdown — the strategy's worst peak-to-trough
> loss is meaningfully **smaller**, because it moves to cash in downtrends. That
> trade-off — less return for a smoother ride — *is* the point of systematic risk
> management. On shorter or choppier windows the risk-adjusted return, the sharpe,
> actually comes out ahead."

**DO:** Scroll down to the metrics table and the per-symbol table.

**SAY:**
> "Down here I can compare every metric side by side, and see how the strategy did
> on each individual symbol — return, sharpe, and trade count per name."

---

## 6 · Demo — Live paper trading (10:00–12:30)

**DO:** In the sidebar, switch to **Paper trading** mode.

**SAY:**
> "Now the main event — live paper trading. I'm switching to **Paper trading**
> mode. Up top you can see the status is **stopped**, the mode chip says **paper**,
> and it shows whether the market is open or closed."

**DO:** Point at the top KPI strip.

**SAY:**
> "This strip reads straight from my Alpaca paper account — equity, today's **P and
> L**, buying power, exposure, session drawdown, and fills."

**DO:** Press **▶ Start**.

**SAY:**
> "When I press **Start**, two things spin up together: the background data feed
> that polls all eight symbols, and the trading loop. Give it a few seconds for the
> first cycle."

**DO:** Wait ~10–20 seconds for a cycle. Point at each section as it fills.

**SAY (Quote board):**
> "Here's the live quote board filling in — last price, bid, ask, spread, and how
> fresh each quote is."

**SAY (Live signals):**
> "And the live signals — for each symbol the strategy says **long** or **flat**,
> and the engine's action: buy, sell, hold, or blocked by risk. You can see the
> exact reason on the right — the fast average versus the slow average for each
> name."

**SAY (Orders / Positions):**
> "As the engine acts, the orders show up here in **Recent orders**, routed to
> Alpaca paper — with quantity, fill price, and status. And any positions with live
> **P and L** land in this table."


**DO:** Back in the dashboard, scroll to the event log.

**SAY:**
> "Everything is logged in this event feed — data updates, signals, orders, risk
> blocks, and errors — and it's all mirrored to a log file on disk. So there's a
> complete audit trail of what the system did and why."

**DO:** Press **■ Stop**.

**SAY:**
> "And I can stop the whole thing with one button."

---

## 7 · Reflection — limitations, improvements, lessons (12:30–14:20)

**SAY (Limitations):**
> "A few honest limitations. First, it's on the free **I-E-X** feed, which has
> limited depth and isn't split-adjusted, so some older backtests on stocks that
> split — like **Nvidia** — can look distorted. A paid feed fixes that. Second, the
> signals are computed on **daily bars**, so even though the live loop re-checks
> often, the decisions are really daily — intraday trading would need bar
> streaming. And third, position sizing is deliberately simple — equal-ish and
> capped — with no volatility targeting or portfolio optimization."

**SAY (Improvements):**
> "For improvements, the obvious next steps are: model transaction costs and
> slippage in the backtest so it's more realistic; add more strategies and maybe
> ensemble them together; use smarter position sizing like volatility targeting;
> add alerting; and persist state so the system survives a restart."

**SAY (What I learned):**
> "The biggest thing I learned is that **a trading system is mostly not the
> strategy.** The signal logic is a small fraction of the code. The real work is
> everything around it — a data pipeline that doesn't die when one quote fails,
> risk checks that run *before* every order, error handling so a rejected order
> doesn't crash the loop, keeping the engine and the interface on separate threads,
> and logging everything so you can actually trust what happened.
> One concrete example: while testing, I noticed that with the market closed,
> orders sit unfilled — and the engine was re-submitting the same buy every single
> cycle, stacking up duplicate orders. So I added a check that skips a symbol if it
> already has an open order. That's exactly the kind of real-world bug you only find
> by actually running the thing against a broker — and it's why building on paper
> first matters."

---

## 8 · Close (14:20–14:40)

**SAY:**
> "So that's **project alpaca** — a modular system with a live Alpaca data
> pipeline, two systematic strategies, a real risk layer, an execution engine
> routing paper orders, a full backtester, and a dashboard to control it all.
> **Once more: this is paper trading only — no real money is ever used.** Thanks
> for watching."

---

## ✅ Checklist (the video must cover all of these)

- [ ] **Architecture** explained (the modules and how data flows through them)
- [ ] **Data pipeline** described (polling, storage, logging, error handling)
- [ ] **Strategy logic** described (moving average crossover **and** the machine-
      learning / P-C-A / gradient boosting model)
- [ ] **Execution & risk** described (sizing, per-name + gross caps, no leverage,
      stop-loss / take-profit, `paper=True`)
- [ ] **UI demonstrated** in both backtest and paper modes
- [ ] **System shown running in Alpaca paper** (orders + positions in the Alpaca
      dashboard)
- [ ] **Reflection**: limitations, improvements, and what you learned
- [ ] You saying: **"This is paper trading only — no real money is used."**

## Tips

- **Reset the paper account before recording** so you start clean at $100k with no
  leftover orders.
- If the **market is closed**, orders will show as **ACCEPTED / pending** and fill
  at the next open — that still counts as "submitted / running." The dashboard even
  shows a banner explaining this, which is a nice thing to point at on camera.
- Keep it moving — **summarize** the code, don't read every line. Aim for ~13
  minutes so you're safely inside the 10–15 window.
- Rehearse the ticker names once (see the pronunciation box up top) so you don't
  stumble on **triple-Q** and **A-M-D** live.
- Upload as **YouTube (unlisted)** and paste the link in the README, or drop the
  video file in the GitHub repo.
