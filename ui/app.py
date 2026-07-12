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
from html import escape

# Make the project root importable when launched as `streamlit run ui/app.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from config.config import load_config
from config.settings import load_settings
from logutil import GLOBAL_LOG
from backtest.runner import run_backtest_mode
from execution.engine import TradingEngine
from strategy.signals import make_strategy

st.set_page_config(page_title="project-alpaca", page_icon="▲", layout="wide")

# --------------------------------------------------------------------------- #
# Design system
# --------------------------------------------------------------------------- #
# Palette — a calm trading-desk dark surface. Mint = action / "live"; green &
# red are reserved for P&L / up-down only; everything else is neutral.
C = {
    "bg": "#090c12", "panel": "#0e131c", "panel2": "#111826", "raised": "#151d2b",
    "line": "rgba(255,255,255,.07)", "line2": "rgba(255,255,255,.12)",
    "ink": "#eef2f8", "ink2": "#9aa6b8", "ink3": "#687488",
    "mint": "#00e6a2", "mint2": "#0b3b30",
    "up": "#2bd07c", "down": "#ff5f6d", "amber": "#ffb454", "blue": "#6ea8fe",
}

# Event-log kind → (text color, chip background).
KIND = {
    "DATA":   ("#9aa6b8", "rgba(154,166,184,.13)"),
    "SIGNAL": ("#6ea8fe", "rgba(110,168,254,.15)"),
    "ORDER":  ("#00e6a2", "rgba(0,230,162,.14)"),
    "FILL":   ("#2bd07c", "rgba(43,208,124,.16)"),
    "RISK":   ("#ffb454", "rgba(255,180,84,.16)"),
    "INFO":   ("#9aa6b8", "rgba(154,166,184,.11)"),
    "ERROR":  ("#ff5f6d", "rgba(255,95,109,.16)"),
}

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {{
  --bg:{C['bg']}; --panel:{C['panel']}; --panel2:{C['panel2']}; --raised:{C['raised']};
  --line:{C['line']}; --line2:{C['line2']};
  --ink:{C['ink']}; --ink2:{C['ink2']}; --ink3:{C['ink3']};
  --mint:{C['mint']}; --up:{C['up']}; --down:{C['down']}; --amber:{C['amber']};
  --sans:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif;
  --mono:'JetBrains Mono','SF Mono',ui-monospace,'Menlo',monospace;
}}

.stApp {{ background:var(--bg); }}
html, body, [class*="css"] {{ font-family:var(--sans); }}
.block-container {{ padding:1.1rem 2rem 3rem; max-width:1560px; }}
#MainMenu, header[data-testid="stHeader"] {{ background:transparent; }}
[data-testid="stAppDeployButton"] {{ display:none !important; }}

/* Numbers everywhere read as tabular monospace. */
.num, .kpi-val, .money, td.num {{ font-family:var(--mono); font-variant-numeric:tabular-nums; }}

h1,h2,h3,h4 {{ color:var(--ink); letter-spacing:-.015em; font-weight:650; }}
p, .stMarkdown, label, .stCaption {{ color:var(--ink2); }}

/* ---- top bar ---- */
.topbar {{ display:flex; align-items:center; gap:14px; padding:2px 0 14px;
  border-bottom:1px solid var(--line); margin-bottom:18px; }}
.brand {{ display:flex; align-items:center; gap:10px; }}
.brand .mark {{ width:26px; height:26px; border-radius:7px; display:grid; place-items:center;
  background:linear-gradient(150deg,#0e2b24,#0a1620); border:1px solid rgba(0,230,162,.35);
  color:var(--mint); font-size:14px; }}
.brand .name {{ font-weight:650; font-size:1.02rem; color:var(--ink); letter-spacing:-.02em; }}
.brand .sub {{ color:var(--ink3); font-size:.72rem; margin-top:1px; }}
.spacer {{ flex:1; }}
.chip {{ font-family:var(--mono); font-size:.68rem; letter-spacing:.03em; padding:3px 8px;
  border-radius:6px; background:var(--panel2); color:var(--ink2); border:1px solid var(--line); }}
.chip.mode {{ color:var(--mint); border-color:rgba(0,230,162,.25); background:rgba(0,230,162,.07); }}
.chip.mkt-open {{ color:var(--up); border-color:rgba(43,208,124,.28); background:rgba(43,208,124,.1); }}
.chip.mkt-shut {{ color:var(--amber); border-color:rgba(255,180,84,.25); background:rgba(255,180,84,.08); }}
.status {{ display:inline-flex; align-items:center; gap:7px; font-size:.76rem; font-weight:600;
  padding:5px 12px; border-radius:999px; }}
.status.on {{ color:var(--up); background:rgba(43,208,124,.13); border:1px solid rgba(43,208,124,.28); }}
.status.off {{ color:var(--ink2); background:rgba(154,166,184,.1); border:1px solid var(--line); }}
.dot {{ width:7px; height:7px; border-radius:50%; background:currentColor; }}
.status.on .dot {{ box-shadow:0 0 0 0 rgba(43,208,124,.6); animation:pulse 1.8s infinite; }}
@keyframes pulse {{ 0%{{box-shadow:0 0 0 0 rgba(43,208,124,.5);}} 70%{{box-shadow:0 0 0 7px rgba(43,208,124,0);}} 100%{{box-shadow:0 0 0 0 rgba(43,208,124,0);}} }}
@media (prefers-reduced-motion:reduce) {{ .status.on .dot {{ animation:none; }} }}

/* ---- section header ---- */
.sec {{ display:flex; align-items:baseline; gap:10px; margin:22px 0 10px; }}
.sec h4 {{ margin:0; font-size:.82rem; text-transform:uppercase; letter-spacing:.09em; color:var(--ink2); font-weight:600; }}
.sec .hint {{ color:var(--ink3); font-size:.74rem; }}

/* ---- KPI strip ---- */
.kpi-row {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; }}
.kpi {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:13px 15px; }}
.kpi-lab {{ color:var(--ink3); font-size:.68rem; text-transform:uppercase; letter-spacing:.07em; }}
.kpi-val {{ color:var(--ink); font-size:1.42rem; font-weight:600; margin-top:3px; line-height:1.1; }}
.pos {{ color:var(--up); }} .neg {{ color:var(--down); }} .mut {{ color:var(--ink3); }}

/* ---- data tables ---- */
.tbl {{ width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--line);
  border-radius:12px; overflow:hidden; font-size:.84rem; }}
.tbl th {{ text-align:left; color:var(--ink3); font-weight:600; font-size:.68rem; text-transform:uppercase;
  letter-spacing:.06em; padding:9px 14px; border-bottom:1px solid var(--line); background:var(--panel2); }}
.tbl th.r, .tbl td.r {{ text-align:right; }}
.tbl td {{ padding:9px 14px; border-bottom:1px solid var(--line); color:var(--ink); }}
.tbl tr:last-child td {{ border-bottom:none; }}
.tbl tbody tr:hover td {{ background:rgba(255,255,255,.02); }}
.tbl td.sym {{ font-weight:600; letter-spacing:.02em; }}
.tbl td.num {{ text-align:right; color:var(--ink); }}

.badge {{ font-family:var(--mono); font-size:.68rem; font-weight:600; padding:2px 9px; border-radius:5px; letter-spacing:.03em; }}
.b-long {{ color:var(--up); background:rgba(43,208,124,.15); }}
.b-flat {{ color:var(--ink3); background:rgba(154,166,184,.12); }}
.b-buy {{ color:var(--mint); }} .b-sell {{ color:var(--down); }}
.b-hold {{ color:var(--ink3); }} .b-block {{ color:var(--amber); }}
.st-filled {{ color:var(--up); background:rgba(43,208,124,.15); }}
.st-open {{ color:var(--amber); background:rgba(255,180,84,.15); }}
.st-dead {{ color:var(--down); background:rgba(255,95,109,.15); }}

/* ---- terminal event feed ---- */
.feed {{ background:var(--panel); border:1px solid var(--line); border-radius:12px;
  max-height:340px; overflow-y:auto; font-family:var(--mono); font-size:.77rem; }}
.feed-row {{ display:flex; align-items:center; gap:11px; padding:6px 14px; border-bottom:1px solid rgba(255,255,255,.035); }}
.feed-row:last-child {{ border-bottom:none; }}
.feed-time {{ color:var(--ink3); white-space:nowrap; }}
.feed-kind {{ font-size:.62rem; font-weight:600; padding:1px 7px; border-radius:4px; letter-spacing:.05em; white-space:nowrap; }}
.feed-msg {{ color:var(--ink2); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.feed::-webkit-scrollbar {{ width:9px; }}
.feed::-webkit-scrollbar-thumb {{ background:var(--line2); border-radius:6px; }}

.empty {{ background:var(--panel); border:1px dashed var(--line2); border-radius:12px;
  padding:26px; text-align:center; color:var(--ink3); font-size:.84rem; }}

/* ---- sidebar ---- */
section[data-testid="stSidebar"] {{ background:var(--panel); border-right:1px solid var(--line); }}
section[data-testid="stSidebar"] .block-container {{ padding-top:1.4rem; }}
.side-title {{ display:flex; align-items:center; gap:9px; font-weight:650; color:var(--ink); font-size:1rem; }}
.side-title .mark {{ width:24px; height:24px; border-radius:6px; display:grid; place-items:center;
  background:linear-gradient(150deg,#0e2b24,#0a1620); border:1px solid rgba(0,230,162,.35); color:var(--mint); }}
.side-lab {{ color:var(--ink3); font-size:.66rem; text-transform:uppercase; letter-spacing:.09em; margin:18px 0 2px; font-weight:600; }}
.risk {{ font-family:var(--mono); font-size:.75rem; color:var(--ink2); line-height:1.85; }}
.risk b {{ color:var(--ink); font-weight:500; }}
.uni {{ display:flex; flex-wrap:wrap; gap:5px; margin-top:6px; }}
.uni span {{ font-family:var(--mono); font-size:.68rem; color:var(--ink2); background:var(--panel2);
  border:1px solid var(--line); border-radius:5px; padding:2px 7px; }}

/* ---- buttons ---- */
.stButton > button {{ border-radius:9px; font-weight:600; font-size:.84rem; border:1px solid var(--line2);
  background:var(--panel2); color:var(--ink); transition:all .16s cubic-bezier(.2,.8,.2,1); }}
.stButton > button:hover:not(:disabled) {{ border-color:var(--ink3); background:var(--raised); transform:translateY(-1px); }}
.stButton > button:disabled {{ opacity:.4; }}
.stButton > button[kind="primary"] {{ background:var(--mint); color:#04130d; border-color:var(--mint); }}
.stButton > button[kind="primary"]:hover:not(:disabled) {{ filter:brightness(1.08); box-shadow:0 4px 18px rgba(0,230,162,.25); }}

/* alerts a touch calmer */
[data-testid="stAlert"] {{ border-radius:10px; }}
</style>
""", unsafe_allow_html=True)

# Best-effort: hide the "Record a screencast" item from the ⋮ menu (kept otherwise).
components.html("""
<script>
const doc = window.parent.document;
function hideScreencast(){
  doc.querySelectorAll('ul[role="menu"] li,[role="menuitem"],span').forEach(el=>{
    if(/record a screencast/i.test(el.textContent) && el.children.length===0){
      (el.closest('li')||el.closest('[role="menuitem"]')||el).style.display='none';
    }
  });
}
new MutationObserver(hideScreencast).observe(doc.body,{childList:true,subtree:true});
hideScreencast();
</script>
""", height=0)


# --------------------------------------------------------------------------- #
# Formatting + render helpers
# --------------------------------------------------------------------------- #
def money(x, dec=0):
    return f"${x:,.{dec}f}" if x is not None else "—"


def smoney(x):
    if x is None:
        return "—"
    return f"{'+' if x >= 0 else '−'}${abs(x):,.0f}"


def pct(x, signed=True):
    if x is None or x != x:
        return "—"
    return f"{x*100:+.2f}%" if signed else f"{x*100:.2f}%"


def sign_cls(x):
    if x is None or x != x:
        return "mut"
    return "pos" if x >= 0 else "neg"


def section(title, hint=""):
    h = f"<span class='hint'>{escape(hint)}</span>" if hint else ""
    st.markdown(f"<div class='sec'><h4>{escape(title)}</h4>{h}</div>", unsafe_allow_html=True)


def kpi_row(items):
    cards = "".join(
        f"<div class='kpi'><div class='kpi-lab'>{escape(lab)}</div>"
        f"<div class='kpi-val {cls}'>{val}</div></div>"
        for lab, val, cls in items)
    st.markdown(f"<div class='kpi-row'>{cards}</div>", unsafe_allow_html=True)


def empty(msg):
    st.markdown(f"<div class='empty'>{escape(msg)}</div>", unsafe_allow_html=True)


def _action_html(action: str) -> str:
    a = action.upper()
    cls = ("b-buy" if a.startswith("BUY") else "b-sell" if a.startswith("SELL")
           else "b-block" if a.startswith("BLOCK") else "b-hold")
    return f"<span class='badge {cls}'>{escape(action)}</span>"


def signals_table(symbols):
    rows = ""
    for s in symbols:
        badge = (f"<span class='badge {'b-long' if s.signal else 'b-flat'}'>"
                 f"{'LONG' if s.signal else 'FLAT'}</span>")
        price = f"${s.price:,.2f}" if s.price else "—"
        posq = f"{s.position_qty:g}" if s.position_qty else "·"
        rows += (f"<tr><td class='sym'>{escape(s.symbol)}</td><td>{badge}</td>"
                 f"<td class='num'>{price}</td><td class='num'>{posq}</td>"
                 f"<td>{_action_html(s.last_action)}</td>"
                 f"<td style='color:var(--ink3);font-size:.78rem'>{escape(s.reason)}</td></tr>")
    st.markdown(
        "<table class='tbl'><thead><tr><th>Symbol</th><th>Signal</th>"
        "<th class='r'>Price</th><th class='r'>Pos</th><th>Action</th><th>Detail</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>", unsafe_allow_html=True)


def positions_table(positions):
    rows = ""
    for sym, p in positions.items():
        plc = "pos" if p["unrealized_pl"] >= 0 else "neg"
        rows += (f"<tr><td class='sym'>{escape(sym)}</td>"
                 f"<td class='num'>{p['qty']:g}</td>"
                 f"<td class='num'>${p['avg_entry_price']:,.2f}</td>"
                 f"<td class='num'>${p['current_price']:,.2f}</td>"
                 f"<td class='num'>{money(p['market_value'])}</td>"
                 f"<td class='num {plc}'>{smoney(p['unrealized_pl'])}</td>"
                 f"<td class='num {plc}'>{pct(p['unrealized_plpc'])}</td></tr>")
    st.markdown(
        "<table class='tbl'><thead><tr><th>Symbol</th><th class='r'>Qty</th>"
        "<th class='r'>Avg entry</th><th class='r'>Price</th><th class='r'>Mkt value</th>"
        "<th class='r'>Unreal. P&L</th><th class='r'>Return</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>", unsafe_allow_html=True)


def orders_table(orders):
    rows = ""
    for o in orders:
        s = o["status"].lower()
        scls = ("st-filled" if "filled" in s else
                "st-dead" if any(k in s for k in ("reject", "cancel", "expired")) else "st-open")
        sidecls = "b-buy" if o["side"] == "buy" else "b-sell"
        qty = f"{o['qty']:g}" if o["qty"] else "—"
        fill = f"{o['filled_qty']:g}" if o["filled_qty"] else "·"
        rows += (f"<tr><td class='sym'>{escape(o['symbol'])}</td>"
                 f"<td><span class='badge {sidecls}'>{o['side'].upper()}</span></td>"
                 f"<td class='num'>{qty}</td><td class='num'>{fill}</td>"
                 f"<td><span class='badge {scls}'>{escape(o['status'])}</span></td></tr>")
    st.markdown(
        "<table class='tbl'><thead><tr><th>Symbol</th><th>Side</th>"
        "<th class='r'>Qty</th><th class='r'>Filled</th><th>Status</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>", unsafe_allow_html=True)


def event_feed(events):
    rows = ""
    for e in events:
        fg, bg = KIND.get(e.kind, KIND["INFO"])
        t = e.time.astimezone().strftime("%H:%M:%S")
        rows += (f"<div class='feed-row'><span class='feed-time'>{t}</span>"
                 f"<span class='feed-kind' style='color:{fg};background:{bg}'>{e.kind}</span>"
                 f"<span class='feed-msg'>{escape(e.message)}</span></div>")
    st.markdown(f"<div class='feed'>{rows}</div>", unsafe_allow_html=True)


def style_fig(fig, height=300):
    fig.update_layout(
        height=height, margin=dict(l=6, r=6, t=8, b=6),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=C["ink2"], family="JetBrains Mono, monospace", size=11),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.12, x=0, font=dict(size=11),
                    bgcolor="rgba(0,0,0,0)"),
    )
    grid = dict(gridcolor="rgba(255,255,255,.05)", zeroline=False, showline=False)
    fig.update_xaxes(**grid)
    fig.update_yaxes(**grid)
    return fig


# --------------------------------------------------------------------------- #
# Engine lifecycle
# --------------------------------------------------------------------------- #
@st.cache_resource
def _cfg():
    return load_config()


def get_engine(strategy_name: str, params: dict) -> TradingEngine:
    if "engine" not in st.session_state:
        cfg = load_config()
        cfg.strategy.name = strategy_name
        cfg.strategy.params = params
        st.session_state.engine = TradingEngine(load_settings(), cfg, GLOBAL_LOG)
    return st.session_state.engine


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
cfg = _cfg()
st.sidebar.markdown(
    "<div class='side-title'><span class='mark'>▲</span> project-alpaca</div>"
    "<div style='color:var(--ink3);font-size:.72rem;margin:4px 0 6px'>"
    "Systematic trading on Alpaca · paper only</div>", unsafe_allow_html=True)

mode = st.sidebar.radio("Mode", ["Paper trading", "Backtest"], index=0)

st.sidebar.markdown("<div class='side-lab'>Strategy</div>", unsafe_allow_html=True)
strat_name = st.sidebar.selectbox(
    "Systematic strategy", ["ma_crossover", "ml"],
    index=0 if cfg.strategy.name == "ma_crossover" else 1,
    help="ma_crossover = trend following · ml = PCA + gradient boosting",
    label_visibility="collapsed",
)
if strat_name == "ma_crossover":
    fast = st.sidebar.number_input("Fast SMA", 5, 100, int(cfg.strategy.params.get("fast", 20)))
    slow = st.sidebar.number_input("Slow SMA", 10, 250, int(cfg.strategy.params.get("slow", 50)))
    params = {"fast": fast, "slow": slow}
else:
    thr = st.sidebar.slider("Long threshold P(up)", 0.50, 0.80,
                            float(cfg.strategy.params.get("threshold", 0.60)), 0.01)
    params = {"model": "gradient_boosting", "threshold": thr}

st.sidebar.markdown(
    "<div class='side-lab'>Risk limits</div>"
    f"<div class='risk'>≤ <b>{cfg.risk.max_position_pct*100:.0f}%</b> equity / name<br>"
    f"≤ <b>${cfg.risk.max_position_usd:,.0f}</b> / name<br>"
    f"≤ <b>{cfg.risk.max_gross_exposure*100:.0f}%</b> gross · no leverage<br>"
    f"stop <b>−{cfg.risk.stop_loss_pct*100:.0f}%</b> · take <b>+{cfg.risk.take_profit_pct*100:.0f}%</b>"
    "</div>", unsafe_allow_html=True)

st.sidebar.markdown(
    f"<div class='side-lab'>Universe · {len(cfg.universe)}</div>"
    "<div class='uni'>" + "".join(f"<span>{s}</span>" for s in cfg.universe) + "</div>",
    unsafe_allow_html=True)


def topbar(running: bool, mode_label: str, strat: str, market: dict | None = None):
    status = (f"<span class='status on'><span class='dot'></span>RUNNING</span>" if running
              else "<span class='status off'><span class='dot'></span>STOPPED</span>")
    mkt = ""
    if market and market.get("is_open") is not None:
        if market["is_open"]:
            mkt = "<span class='chip mkt-open'>● MARKET OPEN</span>"
        else:
            nxt = market.get("next_open")
            when = nxt.astimezone().strftime("%a %H:%M") if nxt is not None else ""
            mkt = f"<span class='chip mkt-shut'>● MARKET CLOSED · opens {when}</span>"
    st.markdown(
        "<div class='topbar'><div class='brand'><span class='mark'>▲</span>"
        "<div><div class='name'>project-alpaca</div>"
        f"<div class='sub'>Alpaca paper trading engine</div></div></div>"
        f"<div class='spacer'></div>{mkt}<span class='chip mode'>{escape(mode_label)}</span>"
        f"<span class='chip'>{escape(strat)}</span>{status}</div>",
        unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# PAPER TRADING MODE
# --------------------------------------------------------------------------- #
if mode == "Paper trading":
    engine = get_engine(strat_name, params)
    running = engine.running

    try:
        market = engine.broker.clock()
    except Exception:  # noqa: BLE001
        market = None
    topbar(running, "PAPER", strat_name, market)

    c1, c2, c3, _ = st.columns([1, 1, 1, 4])
    if c1.button("▶  Start", disabled=running, use_container_width=True, type="primary"):
        engine.start(); st.rerun()
    if c2.button("■  Stop", disabled=not running, use_container_width=True):
        engine.stop(); st.rerun()
    if c3.button("↻  Refresh", use_container_width=True):
        st.rerun()

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
    pnl = (equity - cfg.engine.starting_equity) if equity else None

    kpi_row([
        ("Equity", money(equity), ""),
        ("Buying power", money(acct.get("buying_power")), ""),
        ("P&L vs start", smoney(pnl), sign_cls(pnl)),
        ("Open positions", str(len(live_positions)), "" if live_positions else "mut"),
        ("Cycles", str(state.cycles), "" if state.cycles else "mut"),
    ])

    if not running and state.cycles == 0:
        st.info("Engine is stopped. Press **▶ Start** to begin the live paper data "
                "feed + trading loop (connects to your Alpaca paper account).")
    elif running and state.cycles == 0:
        st.info("Engine started — first evaluation cycle runs in a few seconds "
                "(fetching bars for the whole universe)…")
    if market and market.get("is_open") is False:
        nxt = market.get("next_open")
        when = nxt.astimezone().strftime("%A %H:%M %Z") if nxt is not None else "the next session"
        st.info(f"📕 Market is closed. Orders still submit and show as **ACCEPTED**, "
                f"but they fill (and become positions with live P&L) at the next open "
                f"— **{when}**. Prices are last-close until then.")
    if acct.get("buying_power") is not None and acct["buying_power"] < 1000:
        st.warning("Low buying power on this paper account — new buy orders may be "
                   "rejected. Reset the paper account in the Alpaca dashboard "
                   "(Account → Reset) to restore $100k of buying power.")

    section("Live signals", f"{sum(1 for s in state.symbols.values() if s.signal)} long"
            if state.symbols else "target position per symbol")
    if state.symbols:
        signals_table(list(state.symbols.values()))
    else:
        empty("No signals yet — press Start and the engine will evaluate the universe.")

    colL, colR = st.columns(2)
    with colL:
        section("Positions & P&L", f"{len(live_positions)} open")
        if live_positions:
            positions_table(live_positions)
        else:
            empty("No open positions.")
    with colR:
        section("Recent orders")
        try:
            orders = engine.broker.recent_orders(12)
        except Exception:
            orders = []
        if orders:
            orders_table(orders)
        else:
            empty("No orders yet.")

    if len(state.equity_curve) > 1:
        section("Session equity")
        eq = pd.DataFrame(state.equity_curve, columns=["ts", "equity"]).set_index("ts")
        fig = go.Figure(go.Scatter(
            x=eq.index, y=eq["equity"], mode="lines",
            line=dict(color=C["mint"], width=2), fill="tozeroy",
            fillcolor="rgba(0,230,162,.06)"))
        fig.update_yaxes(tickprefix="$")
        st.plotly_chart(style_fig(fig, 220), use_container_width=True,
                        config={"displayModeBar": False})

    section("Event log", f"{len(GLOBAL_LOG.recent(500))} events")
    events = GLOBAL_LOG.recent(50)
    if events:
        event_feed(events)
    else:
        empty("No events yet.")

    if auto and running:
        time.sleep(5)
        st.rerun()


# --------------------------------------------------------------------------- #
# BACKTEST MODE
# --------------------------------------------------------------------------- #
else:
    topbar(False, "BACKTEST", strat_name)

    cc1, cc2 = st.columns([3, 1])
    years = cc1.slider("Years of history", 1, 5, int(cfg.backtest.years))
    cc2.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
    run_bt = cc2.button("▶  Run backtest", type="primary", use_container_width=True)
    if run_bt:
        with st.spinner("Downloading data and running the strategy over the universe…"):
            strat = make_strategy(strat_name, params)
            st.session_state.backtest = run_backtest_mode(
                load_settings(), cfg, strategy=strat, days=int(years * 365.25))

    rep = st.session_state.get("backtest")
    if rep:
        m, b = rep.strategy_metrics, rep.buyhold_metrics
        kpi_row([
            ("Total return", pct(m.get("Total Return")), sign_cls(m.get("Total Return"))),
            ("CAGR", pct(m.get("CAGR")), sign_cls(m.get("CAGR"))),
            ("Sharpe", f"{m.get('Sharpe', float('nan')):.2f}", ""),
            ("Max drawdown", pct(m.get("Max Drawdown")), "neg"),
            ("Hit rate", f"{m.get('Hit Rate', float('nan'))*100:.0f}%", ""),
        ])

        section("Portfolio equity", "equal-weight · strategy vs buy & hold")
        fig = go.Figure()
        fig.add_scatter(x=rep.strategy_equity.index, y=rep.strategy_equity,
                        name="Strategy", line=dict(color=C["mint"], width=2))
        fig.add_scatter(x=rep.buyhold_equity.index, y=rep.buyhold_equity,
                        name="Buy & Hold", line=dict(color=C["amber"], width=1.6, dash="dot"))
        fig.update_yaxes(tickprefix="$")
        st.plotly_chart(style_fig(fig, 340), use_container_width=True,
                        config={"displayModeBar": False})

        colL, colR = st.columns([1, 1])
        with colL:
            section("Strategy vs Buy & Hold")
            METS = [("Total Return", "Total return", True), ("CAGR", "CAGR", True),
                    ("Volatility", "Volatility", True), ("Sharpe", "Sharpe", False),
                    ("Max Drawdown", "Max drawdown", True), ("Hit Rate", "Hit rate", True)]
            rows = ""
            for key, lab, is_pct in METS:
                sv = m.get(key); bv = b.get(key)
                fmt = (lambda v: pct(v, signed=False) if (v == v and v is not None) else "—") if is_pct \
                    else (lambda v: f"{v:.2f}" if (v is not None and v == v) else "—")
                rows += (f"<tr><td>{lab}</td><td class='num'>{fmt(sv)}</td>"
                         f"<td class='num' style='color:var(--ink3)'>{fmt(bv)}</td></tr>")
            st.markdown(
                "<table class='tbl'><thead><tr><th>Metric</th><th class='r'>Strategy</th>"
                f"<th class='r'>Buy &amp; Hold</th></tr></thead><tbody>{rows}</tbody></table>",
                unsafe_allow_html=True)
        with colR:
            section("Per-symbol return")
            rows = ""
            for s, r in rep.per_symbol.items():
                sv = r["strategy"]["Total Return"]; bv = r["buyhold"]["Total Return"]
                rows += (f"<tr><td class='sym'>{escape(s)}</td>"
                         f"<td class='num {sign_cls(sv)}'>{pct(sv)}</td>"
                         f"<td class='num' style='color:var(--ink3)'>{pct(bv)}</td>"
                         f"<td class='num'>{r['strategy']['Sharpe']:.2f}</td>"
                         f"<td class='num'>{r['strategy']['Trades']}</td></tr>")
            st.markdown(
                "<table class='tbl'><thead><tr><th>Symbol</th><th class='r'>Strategy</th>"
                "<th class='r'>Buy &amp; Hold</th><th class='r'>Sharpe</th><th class='r'>Trades</th>"
                f"</tr></thead><tbody>{rows}</tbody></table>", unsafe_allow_html=True)
    else:
        empty("Choose a strategy in the sidebar, set the horizon, and press Run backtest.")
