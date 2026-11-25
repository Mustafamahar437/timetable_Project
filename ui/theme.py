"""
ui/theme.py
===========
Shared visual design system: a dark "glass + depth" 3D look.

Everything visual lives here so pages stay free of styling code:
  * inject_css()      - global stylesheet (3D cards, buttons, tabs, sidebar)
  * page_header()     - hero banner used at the top of every page
  * stat_card()       - tilting 3D KPI card
  * pipeline_3d()     - the 6-phase compiler pipeline as 3D blocks
  * timetable_grid()  - colour-coded weekly timetable rendered as HTML
"""

from __future__ import annotations

import html
import streamlit as st

# ---------------------------------------------------------------- stylesheet
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');

:root{
  --bg:#0b0f1f; --panel:#141a33; --panel2:#1b2347; --line:rgba(255,255,255,.08);
  --txt:#e8ebff; --mut:#9aa3d1; --p1:#7c5cff; --p2:#22d3ee; --ok:#34d399; --bad:#fb7185; --warn:#fbbf24;
}
html, body, [class*="css"], .stApp { font-family:'Inter',sans-serif; }
.stApp{
  background:
    radial-gradient(900px 500px at 8% -5%, rgba(124,92,255,.25), transparent 60%),
    radial-gradient(800px 500px at 100% 0%, rgba(34,211,238,.16), transparent 60%),
    linear-gradient(180deg,#0b0f1f,#0a0d1a);
}
.block-container{ padding-top:1.6rem; max-width:1280px; }
header[data-testid="stHeader"]{ background:transparent; }

/* ---------- sidebar ---------- */
section[data-testid="stSidebar"]{
  background:linear-gradient(180deg,#121838,#0c1128);
  border-right:1px solid var(--line);
  box-shadow:6px 0 30px rgba(0,0,0,.45);
}
.brand{ display:flex; gap:12px; align-items:center; padding:6px 4px 14px; }
.brand-logo{
  width:44px; height:44px; border-radius:12px; display:grid; place-items:center; font-size:22px;
  background:linear-gradient(135deg,var(--p1),var(--p2));
  box-shadow:0 10px 24px rgba(124,92,255,.55), inset 0 2px 0 rgba(255,255,255,.35), inset 0 -4px 0 rgba(0,0,0,.25);
  transform:perspective(300px) rotateX(12deg) rotateY(-12deg);
}
.brand-t{ font-weight:800; font-size:1.02rem; line-height:1.1; color:#fff;}
.brand-s{ font-size:.72rem; color:var(--mut); letter-spacing:.08em; text-transform:uppercase;}

/* ---------- hero ---------- */
.hero{
  position:relative; overflow:hidden; padding:28px 32px; border-radius:22px; margin-bottom:22px;
  background:linear-gradient(135deg,rgba(124,92,255,.35),rgba(34,211,238,.18)), var(--panel);
  border:1px solid rgba(255,255,255,.14);
  box-shadow:0 30px 60px -20px rgba(0,0,0,.7), 0 0 0 1px rgba(124,92,255,.18),
             inset 0 1px 0 rgba(255,255,255,.25);
  transform:perspective(1400px) rotateX(1.2deg);
}
.hero:after{ content:""; position:absolute; right:-60px; top:-60px; width:260px; height:260px; border-radius:50%;
  background:radial-gradient(circle at 30% 30%, rgba(255,255,255,.35), rgba(124,92,255,.15) 45%, transparent 70%);
  filter:blur(2px); animation:float 7s ease-in-out infinite; }
.hero h1{ margin:0; font-size:2rem; font-weight:800; letter-spacing:-.02em; color:#fff; padding:0;}
.hero p{ margin:.4rem 0 0; color:#c9d0ff; max-width:760px; font-size:.98rem;}
.hero .tag{ display:inline-block; font-size:.7rem; font-weight:700; letter-spacing:.12em; text-transform:uppercase;
  padding:4px 10px; border-radius:99px; background:rgba(255,255,255,.12); margin-bottom:10px; color:#dfe3ff;}
@keyframes float{ 0%,100%{transform:translateY(0)} 50%{transform:translateY(16px)} }

/* ---------- 3D stat cards ---------- */
.stat-grid{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:18px; perspective:1200px; margin:6px 0 22px;}
.stat{
  position:relative; padding:20px 22px; border-radius:18px; color:#fff;
  background:linear-gradient(145deg,var(--c1),var(--c2));
  box-shadow:0 20px 35px -12px var(--sh), 0 2px 0 rgba(255,255,255,.35) inset, 0 -6px 0 rgba(0,0,0,.18) inset;
  transform:rotateX(0) rotateY(0) translateZ(0); transition:transform .35s cubic-bezier(.2,.8,.2,1), box-shadow .35s;
  transform-style:preserve-3d;
}
.stat:hover{ transform:rotateX(8deg) rotateY(-8deg) translateY(-6px);
  box-shadow:0 34px 50px -14px var(--sh), 0 2px 0 rgba(255,255,255,.4) inset, 0 -6px 0 rgba(0,0,0,.2) inset;}
.stat .ico{ font-size:1.9rem; transform:translateZ(40px); display:inline-block; filter:drop-shadow(0 6px 6px rgba(0,0,0,.35));}
.stat .val{ font-size:2.3rem; font-weight:800; line-height:1.05; transform:translateZ(30px); letter-spacing:-.02em;}
.stat .lab{ font-size:.78rem; opacity:.9; text-transform:uppercase; letter-spacing:.1em; font-weight:600;}

/* ---------- 3D pipeline ---------- */
.pipe{ display:flex; flex-wrap:wrap; gap:14px; align-items:stretch; perspective:1400px; margin:8px 0 24px;}
.node{
  flex:1 1 150px; min-width:150px; padding:16px; border-radius:16px; position:relative;
  background:linear-gradient(160deg,var(--panel2),var(--panel));
  border:1px solid var(--line);
  box-shadow:0 18px 28px -14px rgba(0,0,0,.8), inset 0 1px 0 rgba(255,255,255,.12), 0 6px 0 -2px #0a0e20;
  transform:rotateX(14deg); transition:transform .3s, box-shadow .3s; transform-origin:bottom;
}
.node:hover{ transform:rotateX(0) translateY(-8px);
  box-shadow:0 30px 40px -14px rgba(124,92,255,.55), inset 0 1px 0 rgba(255,255,255,.2), 0 6px 0 -2px #0a0e20;}
.node .n{ width:30px; height:30px; border-radius:9px; display:grid; place-items:center; font-weight:800; font-size:.85rem;
  background:linear-gradient(135deg,var(--p1),var(--p2)); color:#fff; margin-bottom:10px;
  box-shadow:0 6px 12px rgba(124,92,255,.5), inset 0 1px 0 rgba(255,255,255,.4);}
.node .t{ font-weight:700; font-size:.95rem; color:#fff;}
.node .d{ font-size:.76rem; color:var(--mut); margin-top:3px;}
.node .s{ margin-top:10px; font-size:.72rem; font-weight:700; letter-spacing:.06em; text-transform:uppercase;}
.s-ok{color:var(--ok)} .s-bad{color:var(--bad)} .s-idle{color:var(--mut)}
.node.ok{ border-color:rgba(52,211,153,.5);} .node.bad{ border-color:rgba(251,113,133,.6);}

/* ---------- native widgets ---------- */
div[data-testid="stMetric"]{
  background:linear-gradient(160deg,var(--panel2),var(--panel)); border:1px solid var(--line);
  padding:14px 16px; border-radius:14px;
  box-shadow:0 14px 24px -12px rgba(0,0,0,.8), inset 0 1px 0 rgba(255,255,255,.1);
}
div[data-testid="stVerticalBlockBorderWrapper"]{ border-radius:16px; }

/* 3D push buttons */
.stButton>button, .stDownloadButton>button{
  border-radius:12px; font-weight:700; border:1px solid rgba(255,255,255,.14);
  background:linear-gradient(180deg,#2a3470,#1b2347); color:#fff;
  box-shadow:0 6px 0 #0d1330, 0 14px 22px -6px rgba(0,0,0,.7), inset 0 1px 0 rgba(255,255,255,.22);
  transition:transform .12s, box-shadow .12s, filter .2s; transform:translateY(0);
}
.stButton>button:hover, .stDownloadButton>button:hover{ filter:brightness(1.2); transform:translateY(-2px);
  box-shadow:0 8px 0 #0d1330, 0 18px 26px -6px rgba(124,92,255,.5), inset 0 1px 0 rgba(255,255,255,.3);}
.stButton>button:active, .stDownloadButton>button:active{ transform:translateY(5px);
  box-shadow:0 1px 0 #0d1330, 0 4px 8px -4px rgba(0,0,0,.7), inset 0 1px 0 rgba(255,255,255,.2);}
.stButton>button[kind="primary"]{
  background:linear-gradient(180deg,#9078ff,#6240f0); border-color:rgba(255,255,255,.3);
  box-shadow:0 6px 0 #3b23a8, 0 16px 26px -6px rgba(124,92,255,.65), inset 0 1px 0 rgba(255,255,255,.4);}
.stButton>button[kind="primary"]:active{ box-shadow:0 1px 0 #3b23a8, 0 4px 8px -4px rgba(124,92,255,.6);}

/* tabs */
button[data-baseweb="tab"]{ border-radius:10px 10px 0 0; font-weight:600; }
div[data-baseweb="tab-highlight"]{ background:linear-gradient(90deg,var(--p1),var(--p2)); height:3px; }

/* inputs / editor */
textarea, input{ font-family:'JetBrains Mono',monospace !important; }
div[data-baseweb="textarea"], div[data-baseweb="select"]>div, div[data-baseweb="input"]{
  border-radius:12px !important; box-shadow:inset 0 3px 8px rgba(0,0,0,.5);
}
div[data-testid="stDataFrame"], div[data-testid="stCodeBlock"], div[data-testid="stExpander"]{
  border-radius:14px; box-shadow:0 18px 30px -16px rgba(0,0,0,.8); border:1px solid var(--line); overflow:hidden;}
div[data-testid="stAlert"]{ border-radius:14px; box-shadow:0 12px 22px -12px rgba(0,0,0,.7);}
h2,h3{ letter-spacing:-.01em; }

/* ---------- timetable grid ---------- */
.tt{ width:100%; border-collapse:separate; border-spacing:8px; perspective:1400px;}
.tt th{ padding:12px; border-radius:12px; font-size:.82rem; letter-spacing:.08em; text-transform:uppercase; color:#fff;
  background:linear-gradient(180deg,#3a2fa8,#2a2178); box-shadow:0 6px 0 #171049, 0 12px 18px -8px rgba(0,0,0,.7);}
.tt td.t{ font-weight:700; color:var(--mut); text-align:center; width:70px; font-size:.82rem;}
.tt td.c{ vertical-align:top; min-width:130px; height:64px; padding:6px; border-radius:12px;
  background:rgba(255,255,255,.03); border:1px dashed rgba(255,255,255,.07);}
.slot{ padding:8px 10px; border-radius:10px; margin-bottom:5px; color:#fff; font-size:.78rem; line-height:1.3;
  background:linear-gradient(145deg,var(--a),var(--b));
  box-shadow:0 5px 0 rgba(0,0,0,.35), 0 12px 16px -8px rgba(0,0,0,.7), inset 0 1px 0 rgba(255,255,255,.35);
  transition:transform .2s; }
.slot:hover{ transform:translateY(-4px) scale(1.04); z-index:2; position:relative;}
.slot b{ font-size:.86rem;} .slot span{ opacity:.88; display:block; font-size:.72rem;}
</style>
"""

_PALETTE = [
    ("#7c5cff", "#5b3df0"), ("#22d3ee", "#0891b2"), ("#f472b6", "#db2777"),
    ("#34d399", "#059669"), ("#fbbf24", "#d97706"), ("#fb7185", "#e11d48"),
    ("#60a5fa", "#2563eb"), ("#a78bfa", "#7c3aed"),
]


def inject_css() -> None:
    """Inject the global stylesheet. Call once per run from app.py."""
    st.html(_CSS)


def page_header(title: str, subtitle: str = "", tag: str = "") -> None:
    """Hero banner for the top of a page."""
    tag_html = f'<div class="tag">{html.escape(tag)}</div>' if tag else ""
    st.html(
        f'<div class="hero">{tag_html}<h1>{html.escape(title)}</h1>'
        f'<p>{html.escape(subtitle)}</p></div>'
    )


def stat_cards(items: list[tuple[str, str, int | str, str, str]]) -> None:
    """items: (icon, label, value, color1, color2)."""
    cards = ""
    for icon, label, value, c1, c2 in items:
        cards += (
            f'<div class="stat" style="--c1:{c1};--c2:{c2};--sh:{c1}99">'
            f'<div class="ico">{icon}</div><div class="val">{value}</div>'
            f'<div class="lab">{html.escape(label)}</div></div>'
        )
    st.html(f'<div class="stat-grid">{cards}</div>')


def pipeline_3d(states: list[tuple[str, str, str, str]]) -> None:
    """states: (title, description, status['ok'|'bad'|'idle'], status_label)."""
    nodes = ""
    for i, (title, desc, status, label) in enumerate(states, 1):
        nodes += (
            f'<div class="node {status if status != "idle" else ""}">'
            f'<div class="n">{i}</div><div class="t">{html.escape(title)}</div>'
            f'<div class="d">{html.escape(desc)}</div>'
            f'<div class="s s-{status}">{html.escape(label)}</div></div>'
        )
    st.html(f'<div class="pipe">{nodes}</div>')


def timetable_grid(entries: list[dict], days: list[str], times: list[str]) -> None:
    """Render the weekly timetable as colour-coded 3D blocks (one colour per course)."""
    courses = sorted({e["course_id"] for e in entries})
    color = {c: _PALETTE[i % len(_PALETTE)] for i, c in enumerate(courses)}
    cell: dict[tuple[str, str], list[dict]] = {}
    for e in entries:
        cell.setdefault((e["time_slot"], e["day"]), []).append(e)

    head = "<tr><th></th>" + "".join(f"<th>{html.escape(d[:3])}</th>" for d in days) + "</tr>"
    rows = ""
    for t in times:
        tds = ""
        for d in days:
            blocks = ""
            for e in cell.get((t, d), []):
                a, b = color[e["course_id"]]
                blocks += (
                    f'<div class="slot" style="--a:{a};--b:{b}"><b>{html.escape(e["course_id"])}</b>'
                    f'<span>{html.escape(e["room_id"])} · {html.escape(e["teacher_name"])}</span></div>'
                )
            tds += f'<td class="c">{blocks}</td>'
        rows += f'<tr><td class="t">{html.escape(t)}</td>{tds}</tr>'
    st.html(f'<table class="tt">{head}{rows}</table>')
