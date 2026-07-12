"""project-alpaca — control & monitoring dashboard (Streamlit).

Run from the project root:
    streamlit run ui/app.py

Two modes:
  * PAPER  — start/stop the live trading engine; watch account, positions,
             signals, orders, P&L and the event log update in real time.
  * BACKTEST — run the same strategy over history and compare to Buy & Hold.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime

# Make the project root importable when launched as `streamlit run ui/app.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.config import load_config
from config.settings import load_settings
from logutil import GLOBAL_LOG
from backtest.runner import run_backtest_mode
from execution.engine import TradingEngine
from strategy.signals import make_strategy

st.set_page_config(page_title="project-alpaca", page_icon="▲", layout="wide")

# --------------------------------------------------------------------------- #
# Styling
# --------------------------------------------------------------------------- #
st.markdown("""
<style>
  .stApp { background:#0a0d13; }
  .block-container { padding-top:1.4rem; max-width:1500px; }
  h1,h2,h3 { color:#eef1f6; letter-spacing:-.01em; }
  .kpi { background:#10141d; border:1px solid rgba(255,255,255,.07);
         border-radius:14px; padding:14px 16px; }
  .kpi .lab { color:#8b95a7; font-size:.72rem; text-transform:uppercase;
              letter-spacing:.08em; }
  .kpi .val { color:#eef1f6; font-size:1.5rem; font-weight:650; margin-top:2px; }
  .pos { color:#2bd07c; } .neg { color:#ff5d6c; } .mint { color:#00e5a0; }
  .pill { display:inline-block; padding:3px 11px; border-radius:999px;
          font-size:.74rem; font-weight:600; }
  .on  { background:rgba(43,208,124,.16); color:#2bd07c; }
  .off { background:rgba(255,93,108,.15); color:#ff5d6c; }
  .tag { font-size:.68rem; padding:2px 7px; border-radius:6px;
         background:rgba(0,229,160,.12); color:#00e5a0; }
  /* Hide Streamlit's default "Deploy" button (keep the ⋮ menu). */
  [data-testid="stAppDeployButton"] { display:none !important; }
</style>
""", unsafe_allow_html=True)

# Best-effort: also hide the "Record a screencast" item from the ⋮ menu.
# (CSS can't target it by text, so a tiny observer in a 0-height iframe does it.)
import streamlit.components.v1 as _components
_components.html("""
<script>
const doc = window.parent.document;
function hideScreencast() {
  doc.querySelectorAll('ul[role="menu"] li, [role="menuitem"], span').forEach(el => {
    if (/record a screencast/i.test(el.textContent) && el.children.length === 0) {
      const item = el.closest('li') || el.closest('[role="menuitem"]') || el;
      item.style.display = 'none';
    }
  });
}
new MutationObserver(hideScreencast).observe(doc.body, {childList:true, subtree:true});
hideScreencast();
</script>
""", height=0)


# --------------------------------------------------------------------------- #
# Engine lifecycle (persisted across reruns in session_state)
# --------------------------------------------------------------------------- #
@st.cache_resource
def _cfg():
    return load_config()


def get_engine(strategy_name: str, params: dict) -> TradingEngine:
    """Build (once) and cache the engine so its background thread survives reruns."""
    if "engine" not in st.session_state:
        cfg = load_config()
        cfg.strategy.name = strategy_name
        cfg.strategy.params = params
        st.session_state.engine = TradingEngine(load_settings(), cfg, GLOBAL_LOG)
    return st.session_state.engine


def kpi(col, label, value, cls=""):
    col.markdown(
        f"<div class='kpi'><div class='lab'>{label}</div>"
        f"<div class='val {cls}'>{value}</div></div>", unsafe_allow_html=True)


def money(x): return f"${x:,.0f}" if x is not None else "—"
def pct(x): return f"{x*100:+.2f}%" if x is not None else "—"


def _fmt_metrics(m: dict) -> dict:
    if not m:
        return {}
    out = {}
    for k, v in m.items():
        if k in ("Total Return", "CAGR", "Volatility", "Max Drawdown", "Hit Rate"):
            out[k] = f"{v*100:.2f}%" if v == v else "—"
        elif k == "Sharpe":
            out[k] = f"{v:.2f}" if v == v else "—"
        else:
            out[k] = v
    return out


# --------------------------------------------------------------------------- #
# Sidebar — controls
# --------------------------------------------------------------------------- #
cfg = _cfg()
st.sidebar.title("▲ project-alpaca")
st.sidebar.caption("Systematic trading on Alpaca — **paper only**")

mode = st.sidebar.radio("Mode", ["Paper trading", "Backtest"], index=0)

st.sidebar.markdown("### Strategy")
strat_name = st.sidebar.selectbox(
    "Systematic strategy", ["ma_crossover", "ml"],
    index=0 if cfg.strategy.name == "ma_crossover" else 1,
    help="ma_crossover = trend following · ml = PCA + gradient boosting",
)
if strat_name == "ma_crossover":
    fast = st.sidebar.number_input("Fast SMA", 5, 100, int(cfg.strategy.params.get("fast", 20)))
    slow = st.sidebar.number_input("Slow SMA", 10, 250, int(cfg.strategy.params.get("slow", 50)))
    params = {"fast": fast, "slow": slow}
else:
    thr = st.sidebar.slider("Long threshold P(up)", 0.50, 0.80,
                            float(cfg.strategy.params.get("threshold", 0.60)), 0.01)
    params = {"model": "gradient_boosting", "threshold": thr}

st.sidebar.markdown("### Risk limits")
st.sidebar.caption(
    f"• ≤ {cfg.risk.max_position_pct*100:.0f}% equity / name  \n"
    f"• ≤ ${cfg.risk.max_position_usd:,.0f} / name  \n"
    f"• ≤ {cfg.risk.max_gross_exposure*100:.0f}% gross (no leverage)  \n"
    f"• stop −{cfg.risk.stop_loss_pct*100:.0f}% · take +{cfg.risk.take_profit_pct*100:.0f}%")
st.sidebar.caption(f"Universe ({len(cfg.universe)}): {', '.join(cfg.universe)}")


# --------------------------------------------------------------------------- #
# PAPER TRADING MODE
# --------------------------------------------------------------------------- #
if mode == "Paper trading":
    engine = get_engine(strat_name, params)
    running = engine.running

    c1, c2, c3, c4 = st.columns([1, 1, 1, 3])
    if c1.button("▶ Start", disabled=running, use_container_width=True):
        engine.start(); st.rerun()
    if c2.button("■ Stop", disabled=not running, use_container_width=True):
        engine.stop(); st.rerun()
    if c3.button("🔄 Refresh", use_container_width=True):
        st.rerun()
    status = ("<span class='pill on'>● RUNNING</span>" if running
              else "<span class='pill off'>● STOPPED</span>")
    c4.markdown(f"### project-alpaca &nbsp; {status} "
                f"&nbsp;<span class='tag'>PAPER</span> "
                f"<span class='tag'>{strat_name}</span>", unsafe_allow_html=True)

    auto = st.sidebar.checkbox("Auto-refresh (5s)", value=True)

    state = engine.state()
    # Read account + positions LIVE from the broker so the dashboard is current
    # even between cycles and even when the market is closed.
    try:
        acct = engine.broker.account()
        live_positions = engine.broker.positions()
    except Exception as exc:  # noqa: BLE001
        acct, live_positions = state.account or {}, state.positions
        st.warning(f"Could not read account: {exc}")

    equity = acct.get("equity")
    start_eq = cfg.engine.starting_equity
    pnl = (equity - start_eq) if equity else None

    k1, k2, k3, k4, k5 = st.columns(5)
    kpi(k1, "Equity", money(equity))
    kpi(k2, "Buying power", money(acct.get("buying_power")))
    kpi(k3, "P&L vs start", money(pnl), "pos" if (pnl or 0) >= 0 else "neg")
    kpi(k4, "Open positions", str(len(live_positions)))
    kpi(k5, "Cycles", str(state.cycles))

    if not running and state.cycles == 0:
        st.info("Engine is stopped. Press **▶ Start** to begin the live paper "
                "data feed + trading loop. (Connects to your Alpaca paper account.)")
    elif running and state.cycles == 0:
        st.info("Engine started — first evaluation cycle runs in a few seconds "
                "(fetching bars for the whole universe)…")
    if acct.get("buying_power") is not None and acct["buying_power"] < 1000:
        st.warning("⚠️ Low buying power on this paper account — new buy orders may "
                   "be rejected. Reset the paper account in the Alpaca dashboard "
                   "(Account → Reset) to restore $100k of buying power.")

    # Signals table
    st.markdown("#### Live signals")
    if state.symbols:
        rows = [{
            "Symbol": s.symbol, "Signal": "LONG" if s.signal else "FLAT",
            "Price": f"${s.price:.2f}" if s.price else "—",
            "Position": f"{s.position_qty:g}" if s.position_qty else "—",
            "Last action": s.last_action, "Detail": s.reason,
        } for s in state.symbols.values()]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.caption("No signals yet — start the engine.")

    colL, colR = st.columns(2)

    # Positions
    with colL:
        st.markdown("#### Positions & P&L")
        if live_positions:
            prows = [{
                "Symbol": sym, "Qty": p["qty"], "Avg entry": f"${p['avg_entry_price']:.2f}",
                "Price": f"${p['current_price']:.2f}", "Mkt value": money(p["market_value"]),
                "Unreal. P&L": f"${p['unrealized_pl']:+,.0f}",
                "Ret": pct(p["unrealized_plpc"]),
            } for sym, p in live_positions.items()]
            st.dataframe(pd.DataFrame(prows), use_container_width=True, hide_index=True)
        else:
            st.caption("No open positions.")

        # Equity curve
        if len(state.equity_curve) > 1:
            eq = pd.DataFrame(state.equity_curve, columns=["ts", "equity"]).set_index("ts")
            fig = go.Figure(go.Scatter(x=eq.index, y=eq["equity"], line=dict(color="#00e5a0")))
            fig.update_layout(height=240, margin=dict(l=0, r=0, t=10, b=0),
                              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font_color="#a2adbf", title="Equity (this session)")
            st.plotly_chart(fig, use_container_width=True)

    # Orders + event log
    with colR:
        st.markdown("#### Recent orders")
        try:
            orders = engine.broker.recent_orders(12)
        except Exception:
            orders = []
        if orders:
            odf = pd.DataFrame(orders)[["symbol", "side", "qty", "filled_qty", "status", "type"]]
            st.dataframe(odf, use_container_width=True, hide_index=True)
        else:
            st.caption("No orders yet.")

    st.markdown("#### Event log")
    events = GLOBAL_LOG.recent(40)
    if events:
        edf = pd.DataFrame([e.as_row() for e in events])
        st.dataframe(edf, use_container_width=True, hide_index=True, height=280)
    else:
        st.caption("No events yet.")

    if auto and running:
        time.sleep(5)
        st.rerun()


# --------------------------------------------------------------------------- #
# BACKTEST MODE
# --------------------------------------------------------------------------- #
else:
    st.markdown(f"### Backtest &nbsp;<span class='tag'>{strat_name}</span> "
                f"<span class='tag'>historical</span>", unsafe_allow_html=True)
    years = st.slider("Years of history", 1, 5, int(cfg.backtest.years))
    if st.button("▶ Run backtest", type="primary"):
        with st.spinner("Downloading data and running the strategy…"):
            strat = make_strategy(strat_name, params)
            rep = run_backtest_mode(load_settings(), cfg, strategy=strat,
                                    days=int(years * 365.25))
        st.session_state.backtest = rep

    rep = st.session_state.get("backtest")
    if rep:
        m, b = rep.strategy_metrics, rep.buyhold_metrics
        k1, k2, k3, k4 = st.columns(4)
        kpi(k1, "Total Return", pct(m.get("Total Return")),
            "pos" if m.get("Total Return", 0) >= 0 else "neg")
        kpi(k2, "Sharpe", f"{m.get('Sharpe', float('nan')):.2f}")
        kpi(k3, "Max Drawdown", pct(m.get("Max Drawdown")), "neg")
        kpi(k4, "Hit Rate", f"{m.get('Hit Rate', float('nan'))*100:.0f}%")

        # Equity comparison
        fig = go.Figure()
        fig.add_scatter(x=rep.strategy_equity.index, y=rep.strategy_equity,
                        name="Strategy", line=dict(color="#00e5a0"))
        fig.add_scatter(x=rep.buyhold_equity.index, y=rep.buyhold_equity,
                        name="Buy & Hold", line=dict(color="#ffb454"))
        fig.update_layout(height=340, margin=dict(l=0, r=0, t=30, b=0),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font_color="#a2adbf", title="Portfolio equity — Strategy vs Buy & Hold",
                          legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("#### Portfolio metrics")
        comp = pd.DataFrame({
            "Strategy": _fmt_metrics(m), "Buy & Hold": _fmt_metrics(b),
        })
        st.dataframe(comp, use_container_width=True)

        st.markdown("#### Per-symbol (Total Return: strategy vs buy & hold)")
        prows = [{
            "Symbol": s,
            "Strategy": pct(r["strategy"]["Total Return"]),
            "Buy & Hold": pct(r["buyhold"]["Total Return"]),
            "Sharpe": f"{r['strategy']['Sharpe']:.2f}",
            "Trades": r["strategy"]["Trades"],
        } for s, r in rep.per_symbol.items()]
        st.dataframe(pd.DataFrame(prows), use_container_width=True, hide_index=True)
    else:
        st.info("Choose a strategy in the sidebar and press **Run backtest**.")
