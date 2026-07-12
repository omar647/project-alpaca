# PRODUCT.md — project-alpaca

## Register
**Product.** This is an operator's dashboard for a systematic trading system — a tool
the user runs to monitor and control live paper trading and backtests. Design serves
the task; the interface should disappear into the work.

## Users & purpose
A finance student / quant-curious operator running an Alpaca **paper** trading engine.
On any given screen they are: starting/stopping the strategy, watching signals and
orders flow, and reading account P&L, positions, and a live event log — or running a
historical backtest and comparing it to Buy & Hold. They need to trust the numbers at
a glance and never wonder whether the system is doing something.

## Brand personality
Terminal-native, precise, calm. Bloomberg/Linear/Stripe-grade restraint: a dark
trading-desk surface, tabular monospace numbers, semantic green/red for money, one mint
accent for action and "live" state. Confidence through legibility, not decoration.

## Anti-references
- SaaS-cream / warm-neutral marketing look — wrong register entirely.
- Gradient-accented "hero metric" cards, glassmorphism, playful rounded mascots.
- Rainbow dashboards where color is decoration rather than meaning.

## Design principles
1. **Numbers are the product.** Tabular monospace, aligned, semantic color for sign.
2. **State is always legible.** Running vs stopped, mode, and per-symbol signal are
   never ambiguous.
3. **Restrained color.** Neutral dark surfaces; mint accent for action/live only;
   green/red reserved for P&L and up/down.
4. **The tool disappears.** Familiar affordances, consistent vocabulary, no surprise.

## Accessibility
Dark theme; body/data text ≥4.5:1 on surfaces; semantic colors paired with text labels
(never color alone); respects `prefers-reduced-motion`.

## Stack
Streamlit + Plotly (Python). Styling via a single injected CSS design system; key data
views rendered as bespoke HTML for control the default widgets can't give.
