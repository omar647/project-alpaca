"""project-alpaca — control & monitoring dashboard (Streamlit).

Run from the project root:
    streamlit run ui/app.py

Two modes:
  * PAPER  — start/stop the live trading engine; watch the quote board, account,
             positions, signals, orders, P&L and the event log update live.
  * BACKTEST — run the same strategy over history and compare to Buy & Hold.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
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
# Design system — terminal-native dark. Mint = action / live; green & red are
# reserved for P&L and up/down; everything else stays neutral.
# --------------------------------------------------------------------------- #
C = {
    "bg": "#07090e", "panel": "#0d1119", "panel2": "#111725", "raised": "#161d2e",
    "line": "rgba(255,255,255,.065)", "line2": "rgba(255,255,255,.12)",
    "ink": "#edf1f8", "ink2": "#a3aec2", "ink3": "#77839a",
    "mint": "#00e6a2",
    "up": "#34d383", "down": "#ff5c6c", "amber": "#ffb454", "blue": "#6ea8fe",
}

# Event-log kind → (text color, chip background).
KIND = {
    "DATA":   ("#a3aec2", "rgba(163,174,194,.13)"),
    "SIGNAL": ("#6ea8fe", "rgba(110,168,254,.15)"),
    "ORDER":  ("#00e6a2", "rgba(0,230,162,.14)"),
    "FILL":   ("#34d383", "rgba(52,211,131,.16)"),
    "RISK":   ("#ffb454", "rgba(255,180,84,.16)"),
    "INFO":   ("#a3aec2", "rgba(163,174,194,.11)"),
    "ERROR":  ("#ff5c6c", "rgba(255,92,108,.16)"),
}

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {{
  --bg:{C['bg']}; --panel:{C['panel']}; --panel2:{C['panel2']}; --raised:{C['raised']};
  --line:{C['line']}; --line2:{C['line2']};
  --ink:{C['ink']}; --ink2:{C['ink2']}; --ink3:{C['ink3']};
  --mint:{C['mint']}; --up:{C['up']}; --down:{C['down']}; --amber:{C['amber']}; --blue:{C['blue']};
  --sans:'Inter',system-ui,-apple-system,'Segoe UI',sans-serif;
  --mono:'JetBrains Mono','SF Mono',ui-monospace,'Menlo',monospace;
  --ease:cubic-bezier(.22,.9,.28,1);
}}

.stApp {{ background:
  radial-gradient(1100px 500px at 85% -10%, rgba(0,230,162,.045), transparent 60%),
  radial-gradient(900px 420px at -10% 0%, rgba(110,168,254,.035), transparent 55%),
  var(--bg); }}
html, body, [class*="css"] {{ font-family:var(--sans); }}
.block-container {{ padding:1.05rem 2rem 3.2rem; max-width:1560px; }}
#MainMenu, header[data-testid="stHeader"] {{ background:transparent; }}
[data-testid="stAppDeployButton"] {{ display:none !important; }}

/* Numbers everywhere read as tabular monospace. */
.num, .kpi-val, .money, td.num {{ font-family:var(--mono); font-variant-numeric:tabular-nums; }}

h1,h2,h3,h4 {{ color:var(--ink); letter-spacing:-.015em; font-weight:650; text-wrap:balance; }}
p, .stMarkdown, label, .stCaption {{ color:var(--ink2); }}

/* ---- top bar ---- */
.topbar {{ display:flex; align-items:center; gap:12px; padding:2px 0 14px;
  border-bottom:1px solid var(--line); margin-bottom:16px; flex-wrap:wrap; }}
.brand {{ display:flex; align-items:center; gap:11px; }}
.brand .mark {{ width:30px; height:30px; border-radius:8px; display:grid; place-items:center;
  background:linear-gradient(150deg,#0d2f26,#0a1620); border:1px solid rgba(0,230,162,.38);
  color:var(--mint); font-size:15px; box-shadow:0 0 18px rgba(0,230,162,.12); }}
.brand .name {{ font-weight:650; font-size:1.04rem; color:var(--ink); letter-spacing:-.02em; line-height:1.15; }}
.brand .sub {{ color:var(--ink3); font-size:.71rem; }}
.spacer {{ flex:1; }}
.chip {{ font-family:var(--mono); font-size:.68rem; letter-spacing:.03em; padding:4px 9px;
  border-radius:6px; background:var(--panel2); color:var(--ink2); border:1px solid var(--line);
  white-space:nowrap; }}
.chip.mode-paper {{ color:var(--mint); border-color:rgba(0,230,162,.28); background:rgba(0,230,162,.07); }}
.chip.mode-bt {{ color:var(--blue); border-color:rgba(110,168,254,.28); background:rgba(110,168,254,.08); }}
.chip.mkt-open {{ color:var(--up); border-color:rgba(52,211,131,.28); background:rgba(52,211,131,.1); }}
.chip.mkt-shut {{ color:var(--amber); border-color:rgba(255,180,84,.25); background:rgba(255,180,84,.08); }}
.status {{ display:inline-flex; align-items:center; gap:7px; font-size:.75rem; font-weight:600;
  padding:5px 13px; border-radius:999px; white-space:nowrap; }}
.status.on {{ color:var(--up); background:rgba(52,211,131,.12); border:1px solid rgba(52,211,131,.3); }}
.status.off {{ color:var(--ink2); background:rgba(163,174,194,.09); border:1px solid var(--line2); }}
.dot {{ width:7px; height:7px; border-radius:50%; background:currentColor; }}
.status.on .dot {{ animation:pulse 1.8s infinite; }}
@keyframes pulse {{ 0%{{box-shadow:0 0 0 0 rgba(52,211,131,.5);}} 70%{{box-shadow:0 0 0 7px rgba(52,211,131,0);}} 100%{{box-shadow:0 0 0 0 rgba(52,211,131,0);}} }}
@media (prefers-reduced-motion:reduce) {{
  .status.on .dot {{ animation:none; }}
  * {{ transition-duration:.01ms !important; }}
}}

/* ---- section header ---- */
.sec {{ display:flex; align-items:baseline; gap:10px; margin:24px 0 10px; }}
.sec h4 {{ margin:0; font-size:.8rem; text-transform:uppercase; letter-spacing:.09em; color:var(--ink2); font-weight:600; }}
.sec .hint {{ color:var(--ink3); font-size:.74rem; }}
.sec .rule {{ flex:1; height:1px; background:var(--line); align-self:center; }}

/* ---- KPI strip: one instrument panel, cells divided by hairlines ---- */
.strip {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(168px,1fr)); gap:1px;
  background:var(--line); border:1px solid var(--line); border-radius:14px; overflow:hidden; }}
.cell {{ background:var(--panel); padding:13px 17px 12px; min-width:0; }}
.cell .lab {{ color:var(--ink3); font-size:.66rem; text-transform:uppercase; letter-spacing:.08em; font-weight:600; }}
.cell .val {{ color:var(--ink); font-family:var(--mono); font-variant-numeric:tabular-nums;
  font-size:1.38rem; font-weight:600; margin-top:4px; line-height:1.12; white-space:nowrap; }}
.cell .sub {{ font-family:var(--mono); font-size:.72rem; margin-top:3px; color:var(--ink3); white-space:nowrap; }}
.pos {{ color:var(--up); }} .neg {{ color:var(--down); }} .mut {{ color:var(--ink3); }}

/* ---- data tables ---- */
.tblwrap {{ background:var(--panel); border:1px solid var(--line); border-radius:12px;
  overflow:auto; max-height:420px; }}
.tbl {{ width:100%; border-collapse:collapse; font-size:.84rem; }}
.tbl th {{ position:sticky; top:0; z-index:2; text-align:left; color:var(--ink3); font-weight:600;
  font-size:.67rem; text-transform:uppercase; letter-spacing:.06em; padding:9px 14px;
  border-bottom:1px solid var(--line2); background:var(--panel2); white-space:nowrap; }}
.tbl th.r, .tbl td.r {{ text-align:right; }}
.tbl td {{ padding:8px 14px; border-bottom:1px solid var(--line); color:var(--ink); white-space:nowrap; }}
.tbl tbody tr:last-child td {{ border-bottom:none; }}
.tbl tbody tr {{ transition:background .15s var(--ease); }}
.tbl tbody tr:hover td {{ background:rgba(255,255,255,.025); }}
.tbl td.sym {{ font-weight:600; letter-spacing:.02em; }}
.tbl td.num {{ text-align:right; color:var(--ink); }}
.tbl td.dim {{ color:var(--ink3); }}
.tbl tfoot td {{ position:sticky; bottom:0; background:var(--panel2); border-top:1px solid var(--line2);
  font-weight:600; }}

.badge {{ font-family:var(--mono); font-size:.67rem; font-weight:600; padding:2px 9px;
  border-radius:5px; letter-spacing:.03em; }}
.b-long {{ color:var(--up); background:rgba(52,211,131,.15); }}
.b-flat {{ color:var(--ink3); background:rgba(163,174,194,.12); }}
.b-buy {{ color:var(--mint); }} .b-sell {{ color:var(--down); }}
.b-hold {{ color:var(--ink3); }} .b-block {{ color:var(--amber); }}
.st-filled {{ color:var(--up); background:rgba(52,211,131,.15); }}
.st-open {{ color:var(--amber); background:rgba(255,180,84,.15); }}
.st-dead {{ color:var(--down); background:rgba(255,92,108,.15); }}

/* ---- terminal event feed ---- */
.feed {{ background:var(--panel); border:1px solid var(--line); border-radius:12px;
  max-height:340px; overflow-y:auto; font-family:var(--mono); font-size:.77rem; }}
.feed-row {{ display:flex; align-items:center; gap:11px; padding:6px 14px;
  border-bottom:1px solid rgba(255,255,255,.03); }}
.feed-row:last-child {{ border-bottom:none; }}
.feed-time {{ color:var(--ink3); white-space:nowrap; }}
.feed-kind {{ font-size:.62rem; font-weight:600; padding:1px 7px; border-radius:4px;
  letter-spacing:.05em; white-space:nowrap; }}
.feed-msg {{ color:var(--ink2); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.feed::-webkit-scrollbar, .tblwrap::-webkit-scrollbar {{ width:9px; height:9px; }}
.feed::-webkit-scrollbar-thumb, .tblwrap::-webkit-scrollbar-thumb {{ background:var(--line2); border-radius:6px; }}

.empty {{ background:var(--panel); border:1px dashed var(--line2); border-radius:12px;
  padding:24px 26px; text-align:center; color:var(--ink3); font-size:.84rem; line-height:1.55; }}
.empty b {{ color:var(--ink2); font-weight:600; }}

/* ---- sidebar ---- */
section[data-testid="stSidebar"] {{ background:var(--panel); border-right:1px solid var(--line); }}
section[data-testid="stSidebar"] .block-container {{ padding-top:1.4rem; }}
.side-title {{ display:flex; align-items:center; gap:9px; font-weight:650; color:var(--ink); font-size:1rem; }}
.side-title .mark {{ width:24px; height:24px; border-radius:6px; display:grid; place-items:center;
  background:linear-gradient(150deg,#0d2f26,#0a1620); border:1px solid rgba(0,230,162,.38); color:var(--mint); }}
.side-lab {{ color:var(--ink3); font-size:.65rem; text-transform:uppercase; letter-spacing:.09em;
  margin:18px 0 2px; font-weight:600; }}
.risk {{ font-family:var(--mono); font-size:.74rem; color:var(--ink2); line-height:1.9; }}
.risk b {{ color:var(--ink); font-weight:500; }}
.uni {{ display:flex; flex-wrap:wrap; gap:5px; margin-top:6px; }}
.uni span {{ font-family:var(--mono); font-size:.68rem; color:var(--ink2); background:var(--panel2);
  border:1px solid var(--line); border-radius:5px; padding:2px 7px; }}
.side-foot {{ color:var(--ink3); font-size:.68rem; border-top:1px solid var(--line);
  margin-top:20px; padding-top:12px; line-height:1.6; }}

/* ---- buttons ---- */
.stButton > button {{ border-radius:9px; font-weight:600; font-size:.84rem; border:1px solid var(--line2);
  background:var(--panel2); color:var(--ink); transition:all .16s var(--ease); }}
.stButton > button:hover:not(:disabled) {{ border-color:var(--ink3); background:var(--raised); transform:translateY(-1px); }}
.stButton > button:focus-visible {{ outline:2px solid var(--mint); outline-offset:2px; }}
.stButton > button:disabled {{ opacity:.38; }}
.stButton > button[kind="primary"] {{ background:var(--mint); color:#04130d; border-color:var(--mint); }}
.stButton > button[kind="primary"]:hover:not(:disabled) {{ filter:brightness(1.08);
  box-shadow:0 4px 18px rgba(0,230,162,.25); }}

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


def smoney(x, dec=0):
    if x is None or x != x:
        return "—"
    return f"{'+' if x >= 0 else '−'}${abs(x):,.{dec}f}"


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
    st.markdown(f"<div class='sec'><h4>{escape(title)}</h4>{h}"
                "<span class='rule'></span></div>", unsafe_allow_html=True)


def kpi_strip(cells):
    """cells: list of (label, value, value_cls, sub_html)."""
    html = "".join(
        f"<div class='cell'><div class='lab'>{escape(lab)}</div>"
        f"<div class='val {cls}'>{val}</div>"
        f"<div class='sub'>{sub}</div></div>"
        for lab, val, cls, sub in cells)
    st.markdown(f"<div class='strip'>{html}</div>", unsafe_allow_html=True)


def empty(msg_html):
    st.markdown(f"<div class='empty'>{msg_html}</div>", unsafe_allow_html=True)


def table(head_html, body_html, foot_html=""):
    foot = f"<tfoot>{foot_html}</tfoot>" if foot_html else ""
    st.markdown(f"<div class='tblwrap'><table class='tbl'><thead>{head_html}</thead>"
                f"<tbody>{body_html}</tbody>{foot}</table></div>", unsafe_allow_html=True)


def _action_html(action: str) -> str:
    a = action.upper()
    cls = ("b-buy" if a.startswith("BUY") else "b-sell" if a.startswith("SELL")
           else "b-block" if a.startswith(("BLOCK", "PENDING")) else "b-hold")
    return f"<span class='badge {cls}'>{escape(action)}</span>"


def _age(ts) -> str:
    if ts is None:
        return "—"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    s = (datetime.now(timezone.utc) - ts).total_seconds()
    if s < 90:
        return f"{s:.0f}s"
    if s < 5400:
        return f"{s/60:.0f}m"
    if s < 172800:
        return f"{s/3600:.0f}h"
    return f"{s/86400:.0f}d"


def quote_board(quotes: dict[str, dict], universe: list[str]):
    rows = ""
    for sym in universe:
        q = quotes.get(sym)
        if not q:
            continue
        last, bid, ask = q.get("last_price"), q.get("bid_price"), q.get("ask_price")
        # Off-hours the free IEX feed often reports a one-sided book (0 / None);
        # show those as missing rather than "$0.00".
        bid = bid or None
        ask = ask or None
        spread = (ask - bid) if (bid and ask and ask >= bid) else None
        sp_txt = f"{spread:.2f}" if spread is not None else "—"
        ts = q.get("trade_time") or q.get("quote_time")
        rows += (f"<tr><td class='sym'>{escape(sym)}</td>"
                 f"<td class='num'>{money(last, 2)}</td>"
                 f"<td class='num dim'>{money(bid, 2)}</td>"
                 f"<td class='num dim'>{money(ask, 2)}</td>"
                 f"<td class='num dim'>{sp_txt}</td>"
                 f"<td class='num dim'>{_age(ts)}</td></tr>")
    table("<tr><th>Symbol</th><th class='r'>Last</th><th class='r'>Bid</th>"
          "<th class='r'>Ask</th><th class='r'>Spread</th><th class='r'>Age</th></tr>", rows)


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
                 f"<td class='dim' style='font-size:.78rem'>{escape(s.reason)}</td></tr>")
    table("<tr><th>Symbol</th><th>Signal</th><th class='r'>Price</th>"
          "<th class='r'>Pos</th><th>Action</th><th>Detail</th></tr>", rows)


def positions_table(positions):
    rows, tot_mv, tot_pl = "", 0.0, 0.0
    for sym, p in positions.items():
        plc = sign_cls(p["unrealized_pl"])
        tot_mv += p["market_value"]
        tot_pl += p["unrealized_pl"]
        rows += (f"<tr><td class='sym'>{escape(sym)}</td>"
                 f"<td class='num'>{p['qty']:g}</td>"
                 f"<td class='num dim'>${p['avg_entry_price']:,.2f}</td>"
                 f"<td class='num'>${p['current_price']:,.2f}</td>"
                 f"<td class='num'>{money(p['market_value'])}</td>"
                 f"<td class='num {plc}'>{smoney(p['unrealized_pl'])}</td>"
                 f"<td class='num {plc}'>{pct(p['unrealized_plpc'])}</td></tr>")
    foot = (f"<tr><td>Total</td><td></td><td></td><td></td>"
            f"<td class='num'>{money(tot_mv)}</td>"
            f"<td class='num {sign_cls(tot_pl)}'>{smoney(tot_pl)}</td><td></td></tr>")
    table("<tr><th>Symbol</th><th class='r'>Qty</th><th class='r'>Avg entry</th>"
          "<th class='r'>Price</th><th class='r'>Mkt value</th>"
          "<th class='r'>Unreal. P&L</th><th class='r'>Return</th></tr>", rows, foot)


def orders_table(orders):
    rows = ""
    for o in orders:
        s = o["status"].lower()
        scls = ("st-filled" if "filled" in s else
                "st-dead" if any(k in s for k in ("reject", "cancel", "expired")) else "st-open")
        sidecls = "b-buy" if o["side"] == "buy" else "b-sell"
        qty = f"{o['qty']:g}" if o["qty"] else "—"
        fill = f"{o['filled_qty']:g}" if o["filled_qty"] else "·"
        px = f"${o['filled_avg_price']:,.2f}" if o.get("filled_avg_price") else "·"
        ts = o.get("submitted_at")
        when = ts.astimezone().strftime("%m-%d %H:%M") if ts is not None else "—"
        rows += (f"<tr><td class='num dim' style='font-size:.74rem'>{when}</td>"
                 f"<td class='sym'>{escape(o['symbol'])}</td>"
                 f"<td><span class='badge {sidecls}'>{o['side'].upper()}</span></td>"
                 f"<td class='num'>{qty}</td><td class='num dim'>{fill}</td>"
                 f"<td class='num dim'>{px}</td>"
                 f"<td><span class='badge {scls}'>{escape(o['status'])}</span></td></tr>")
    table("<tr><th>Time</th><th>Symbol</th><th>Side</th><th class='r'>Qty</th>"
          "<th class='r'>Filled</th><th class='r'>Avg px</th><th>Status</th></tr>", rows)


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
        hoverlabel=dict(bgcolor=C["raised"], bordercolor="rgba(255,255,255,.15)",
                        font=dict(family="JetBrains Mono, monospace", size=11, color=C["ink"])),
        legend=dict(orientation="h", y=1.14, x=0, font=dict(size=11),
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


def strat_label(name: str, params: dict) -> str:
    if name == "ma_crossover":
        return f"SMA {params.get('fast', 20)}/{params.get('slow', 50)} · trend"
    return f"ML · GB · p>{params.get('threshold', 0.6):.2f}"


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

st.sidebar.markdown(
    "<div class='side-foot'>Every order routes to Alpaca's <b>paper</b> endpoint.<br>"
    "Keys load from <code>.env</code> — never committed.</div>", unsafe_allow_html=True)


def topbar(running: bool, mode_label: str, strat_txt: str, market: dict | None = None):
    status = ("<span class='status on'><span class='dot'></span>RUNNING</span>" if running
              else "<span class='status off'><span class='dot'></span>STOPPED</span>")
    mkt = ""
    if market and market.get("is_open") is not None:
        if market["is_open"]:
            mkt = "<span class='chip mkt-open'>● MARKET OPEN</span>"
        else:
            nxt = market.get("next_open")
            when = nxt.astimezone().strftime("%a %H:%M") if nxt is not None else ""
            mkt = f"<span class='chip mkt-shut'>● MARKET CLOSED · opens {when}</span>"
    mode_cls = "mode-paper" if mode_label == "PAPER" else "mode-bt"
    st.markdown(
        "<div class='topbar'><div class='brand'><span class='mark'>▲</span>"
        "<div><div class='name'>project-alpaca</div>"
        "<div class='sub'>Alpaca paper trading engine</div></div></div>"
        f"<div class='spacer'></div>{mkt}"
        f"<span class='chip {mode_cls}'>{escape(mode_label)}</span>"
        f"<span class='chip'>{escape(strat_txt)}</span>{status}</div>",
        unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# First-run state — no API keys yet.
# --------------------------------------------------------------------------- #
try:
    load_settings()
except RuntimeError as exc:
    topbar(False, "PAPER", strat_label(strat_name, params))
    st.error(f"**Alpaca keys not configured.** {exc}")
    st.markdown(
        "```bash\ncp .env.example .env   # then paste your *paper* keys (they start with PK)\n```\n"
        "Get paper keys at [app.alpaca.markets](https://app.alpaca.markets) → "
        "*Paper Trading* → *API Keys*. Restart the app afterwards.")
    st.stop()


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
    topbar(running, "PAPER", strat_label(strat_name, params), market)

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
        connected = True
    except Exception as exc:  # noqa: BLE001
        acct, live_positions = state.account or {}, state.positions
        connected = False
        st.warning(f"Broker unreachable — showing the last engine snapshot. ({exc})")

    try:
        orders = engine.broker.recent_orders(25)
    except Exception:  # noqa: BLE001
        orders = []

    equity = acct.get("equity")
    pnl = (equity - cfg.engine.starting_equity) if equity else None
    last_eq = acct.get("last_equity")
    day_pnl = (equity - last_eq) if (equity and last_eq) else None
    exposure = (acct.get("long_market_value", 0.0) / equity) if equity else None
    fills = sum(1 for o in orders if "filled" in o["status"].lower())

    # Session drawdown from the engine's own equity curve.
    session_dd = None
    if len(state.equity_curve) > 1:
        eqs = pd.Series([e for _, e in state.equity_curve], dtype=float)
        session_dd = float((eqs / eqs.cummax() - 1.0).min())

    kpi_strip([
        ("Equity", money(equity), "",
         f"<span class='{sign_cls(day_pnl)}'>{smoney(day_pnl)}</span> today"
         if day_pnl is not None else "account value"),
        ("P&L vs start", smoney(pnl), sign_cls(pnl),
         f"from {money(cfg.engine.starting_equity)}"),
        ("Buying power", money(acct.get('buying_power')), "",
         f"cash {money(acct.get('cash'))}"),
        ("Exposure", pct(exposure, signed=False), "",
         f"{len(live_positions)} open position{'s' if len(live_positions) != 1 else ''}"),
        ("Session drawdown", pct(session_dd, signed=False) if session_dd is not None else "—",
         "neg" if session_dd else "mut", "peak-to-trough this session"),
        ("Fills", str(fills), "" if fills else "mut",
         f"cycle {state.cycles}" if state.cycles else "no cycles yet"),
    ])

    if not running and state.cycles == 0:
        st.info("Engine is stopped. Press **▶ Start** to spin up the live data feed and "
                "the trading loop against your Alpaca paper account.")
    elif running and state.cycles == 0:
        st.info("Engine started — the first evaluation cycle runs in a few seconds "
                "(fetching bars for the whole universe)…")
    if market and market.get("is_open") is False:
        nxt = market.get("next_open")
        when = nxt.astimezone().strftime("%A %H:%M %Z") if nxt is not None else "the next session"
        st.info(f"📕 Market is closed. Orders still submit and show as **ACCEPTED**, but "
                f"they fill (and become positions with live P&L) at the next open — "
                f"**{when}**. Prices are last-close until then.")
    if acct.get("buying_power") is not None and acct["buying_power"] < 1000:
        st.warning("Low buying power on this paper account — new buy orders may be "
                   "rejected. Reset the paper account in the Alpaca dashboard "
                   "(Account → Reset) to restore $100k of buying power.")

    colQ, colS = st.columns([2, 3])
    with colQ:
        quotes = engine.quote_store.all()
        section("Quote board", f"IEX feed · poll {cfg.engine.poll_seconds}s")
        if quotes:
            quote_board(quotes, cfg.universe)
        else:
            empty("The data pipeline fills this board once the engine starts —<br>"
                  f"it polls all <b>{len(cfg.universe)} symbols</b> every "
                  f"<b>{cfg.engine.poll_seconds}s</b> and appends each row to "
                  "<b>data/store/quotes.csv</b>.")
    with colS:
        n_long = sum(1 for s in state.symbols.values() if s.signal)
        section("Live signals", f"{n_long} long · {len(state.symbols) - n_long} flat"
                if state.symbols else "target position per symbol")
        if state.symbols:
            signals_table(list(state.symbols.values()))
        else:
            empty("No signals yet. Each cycle the strategy re-reads daily bars and "
                  "emits <b>LONG</b> or <b>FLAT</b> per symbol — the engine then "
                  "reconciles that against your holdings.")

    colL, colR = st.columns(2)
    with colL:
        section("Positions & P&L", f"{len(live_positions)} open")
        if live_positions:
            positions_table(live_positions)
        else:
            empty("No open positions. When a signal flips <b>LONG</b>, the "
                  "risk-sized buy lands here with live unrealized P&L.")
    with colR:
        section("Recent orders", "routed to Alpaca paper")
        if orders:
            orders_table(orders[:12])
        else:
            empty("Orders appear here the moment the engine routes one —<br>"
                  "with quantity, fill price, and status straight from Alpaca.")

    if len(state.equity_curve) > 1:
        section("Session equity", "sampled once per engine cycle")
        eq = pd.DataFrame(state.equity_curve, columns=["ts", "equity"]).set_index("ts")
        base = float(eq["equity"].iloc[0])
        fig = go.Figure()
        fig.add_scatter(x=eq.index, y=[base] * len(eq), mode="lines",
                        line=dict(width=0), hoverinfo="skip", showlegend=False)
        fig.add_scatter(x=eq.index, y=eq["equity"], mode="lines", name="Equity",
                        line=dict(color=C["mint"], width=2),
                        fill="tonexty", fillcolor="rgba(0,230,162,.07)",
                        hovertemplate="%{y:$,.0f}<extra></extra>")
        fig.add_hline(y=base, line_dash="dot", line_color="rgba(255,255,255,.18)",
                      line_width=1)
        pad = max(abs(float(eq["equity"].max()) - base),
                  abs(base - float(eq["equity"].min())), base * 0.001)
        fig.update_yaxes(tickprefix="$", range=[base - pad * 1.3, base + pad * 1.3])
        st.plotly_chart(style_fig(fig, 230), use_container_width=True,
                        config={"displayModeBar": False})

    section("Event log", f"{len(GLOBAL_LOG.recent(500))} events · mirrored to logs/system.log")
    events = GLOBAL_LOG.recent(50)
    if events:
        event_feed(events)
    else:
        empty("Engine events stream here — <b>DATA</b> updates, <b>SIGNAL</b> "
              "evaluations, <b>ORDER</b> routing, <b>RISK</b> blocks, and errors.")

    if auto and running:
        time.sleep(5)
        st.rerun()


# --------------------------------------------------------------------------- #
# BACKTEST MODE
# --------------------------------------------------------------------------- #
else:
    topbar(False, "BACKTEST", strat_label(strat_name, params))

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
        kpi_strip([
            ("Total return", pct(m.get("Total Return")), sign_cls(m.get("Total Return")),
             f"B&H {pct(b.get('Total Return'))}"),
            ("CAGR", pct(m.get("CAGR")), sign_cls(m.get("CAGR")),
             f"B&H {pct(b.get('CAGR'))}"),
            ("Sharpe", f"{m.get('Sharpe', float('nan')):.2f}", "",
             f"B&H {b.get('Sharpe', float('nan')):.2f}"),
            ("Max drawdown", pct(m.get("Max Drawdown"), signed=False), "neg",
             f"B&H {pct(b.get('Max Drawdown'), signed=False)}"),
            ("Trades", str(m.get("Trades", 0)), "", "round trips, all symbols"),
            ("Hit rate", f"{m.get('Hit Rate', float('nan'))*100:.0f}%", "",
             "share of winning trades"),
        ])

        section("Portfolio equity", "equal-weight · strategy vs buy & hold")
        fig = go.Figure()
        fig.add_scatter(x=rep.strategy_equity.index, y=rep.strategy_equity,
                        name="Strategy", line=dict(color=C["mint"], width=2),
                        hovertemplate="%{y:$,.0f}<extra>Strategy</extra>")
        fig.add_scatter(x=rep.buyhold_equity.index, y=rep.buyhold_equity,
                        name="Buy & Hold",
                        line=dict(color=C["amber"], width=1.6, dash="dot"),
                        hovertemplate="%{y:$,.0f}<extra>Buy & Hold</extra>")
        fig.update_yaxes(tickprefix="$")
        st.plotly_chart(style_fig(fig, 320), use_container_width=True,
                        config={"displayModeBar": False})

        section("Drawdown", "peak-to-trough, strategy vs buy & hold")
        dd_s = rep.strategy_equity / rep.strategy_equity.cummax() - 1.0
        dd_b = rep.buyhold_equity / rep.buyhold_equity.cummax() - 1.0
        fig = go.Figure()
        fig.add_scatter(x=dd_b.index, y=dd_b, name="Buy & Hold", mode="lines",
                        line=dict(color=C["amber"], width=1.2, dash="dot"),
                        hovertemplate="%{y:.1%}<extra>Buy & Hold</extra>")
        fig.add_scatter(x=dd_s.index, y=dd_s, name="Strategy", mode="lines",
                        line=dict(color=C["down"], width=1.6),
                        fill="tozeroy", fillcolor="rgba(255,92,108,.08)",
                        hovertemplate="%{y:.1%}<extra>Strategy</extra>")
        fig.update_yaxes(tickformat=".0%")
        st.plotly_chart(style_fig(fig, 200), use_container_width=True,
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
                         f"<td class='num dim'>{fmt(bv)}</td></tr>")
            table("<tr><th>Metric</th><th class='r'>Strategy</th>"
                  "<th class='r'>Buy &amp; Hold</th></tr>", rows)
        with colR:
            section("Per-symbol return")
            rows = ""
            for s, r in rep.per_symbol.items():
                sv = r["strategy"]["Total Return"]; bv = r["buyhold"]["Total Return"]
                rows += (f"<tr><td class='sym'>{escape(s)}</td>"
                         f"<td class='num {sign_cls(sv)}'>{pct(sv)}</td>"
                         f"<td class='num dim'>{pct(bv)}</td>"
                         f"<td class='num'>{r['strategy']['Sharpe']:.2f}</td>"
                         f"<td class='num'>{r['strategy']['Trades']}</td></tr>")
            table("<tr><th>Symbol</th><th class='r'>Strategy</th>"
                  "<th class='r'>Buy &amp; Hold</th><th class='r'>Sharpe</th>"
                  "<th class='r'>Trades</th></tr>", rows)
    else:
        empty("Pick a strategy and horizon in the sidebar, then press "
              "<b>▶ Run backtest</b> — the exact strategy code that trades live runs "
              "over history and is benchmarked against Buy &amp; Hold.")
