"""RouteGuard: design system (CSS), cards, Verified / Estimated / Unavailable labels, place picker."""
import html
import math

import streamlit as st

from config import DELAY, E, HEADWAY_PENALTY, LEGEND, REL_BASE, ROAD, U, V
from data import geocode

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root{
  --bg:#0B0F19; --panel:#131A2A; --panel2:#18213A; --line:#243049;
  --text:#E6EAF2; --mute:#8B97AD; --acc:#22D3B6; --acc2:#3B82F6;
  --ok:#34D399; --warn:#FBBF24; --bad:#F87171;
}
html,body,[class*="css"],.stApp{font-family:'Inter',system-ui,sans-serif}
.stApp{background:radial-gradient(1200px 600px at 85% -10%,rgba(34,211,182,.10),transparent 60%),
       radial-gradient(900px 500px at -10% 10%,rgba(59,130,246,.10),transparent 60%),var(--bg)}
#MainMenu,footer,[data-testid="stDecoration"]{visibility:hidden}
.block-container{max-width:1100px;padding-top:2rem}

/* ---------- hero ---------- */
.hero{display:flex;align-items:center;gap:18px;padding:22px 26px;margin-bottom:18px;border-radius:20px;
  background:linear-gradient(120deg,rgba(34,211,182,.16),rgba(59,130,246,.14));border:1px solid var(--line)}
.hero .logo{font-size:2.4rem;width:64px;height:64px;display:grid;place-items:center;border-radius:18px;
  background:linear-gradient(135deg,var(--acc),var(--acc2));box-shadow:0 8px 30px rgba(34,211,182,.35)}
.hero h1{margin:0;font-size:2rem;font-weight:800;letter-spacing:-.02em;padding:0}
.hero p{margin:2px 0 0;color:var(--mute);font-size:1rem}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 18px}
.chip{padding:6px 12px;border-radius:999px;font-size:.8rem;font-weight:600;color:var(--text);
  background:var(--panel);border:1px solid var(--line)}

/* ---------- summary strip ---------- */
.strip{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:10px 0 18px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:14px 16px}
.stat .k{color:var(--mute);font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;font-weight:600}
.stat .v{font-size:1.5rem;font-weight:800;margin-top:4px}
.stat .s{color:var(--mute);font-size:.8rem}

/* ---------- route cards ---------- */
.card{border:1px solid var(--line);border-radius:18px;padding:18px;margin:12px 0 6px;
  background:linear-gradient(180deg,var(--panel2),var(--panel));color:var(--text);
  box-shadow:0 6px 24px rgba(0,0,0,.25);transition:transform .15s,border-color .15s}
.card:hover{transform:translateY(-2px);border-color:#34415f}
.card.top{border:1.5px solid var(--acc);box-shadow:0 0 0 4px rgba(34,211,182,.10),0 10px 34px rgba(34,211,182,.15)}
.card .head{display:flex;align-items:center;gap:14px}
.card .ico{font-size:1.5rem;width:48px;height:48px;border-radius:14px;display:grid;place-items:center;background:#0e1424;border:1px solid var(--line)}
.card .ttl{flex:1;min-width:0}
.card .ttl b{font-size:1.1rem}
.badge{display:inline-block;margin-left:8px;padding:2px 9px;border-radius:999px;font-size:.7rem;font-weight:700;
  background:rgba(34,211,182,.16);color:var(--acc);vertical-align:middle}
.ring{--c:var(--ok);width:62px;height:62px;border-radius:50%;display:grid;place-items:center;flex:none;
  background:conic-gradient(var(--c) calc(var(--p)*1%),#222c45 0)}
.ring span{width:48px;height:48px;border-radius:50%;background:var(--panel);display:grid;place-items:center;font-weight:800;font-size:1.05rem}
.ring.mid{--c:var(--warn)} .ring.low{--c:var(--bad)}
.status{margin:12px 0;padding:9px 12px;border-radius:12px;font-weight:600;font-size:.9rem}
.status.st0{background:rgba(52,211,153,.12);color:var(--ok)}
.status.st1{background:rgba(251,191,36,.12);color:var(--warn)}
.status.st2{background:rgba(248,113,113,.12);color:var(--bad)}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.m{background:#0e1424;border:1px solid var(--line);border-radius:12px;padding:10px 12px}
.m .k{color:var(--mute);font-size:.7rem;text-transform:uppercase;letter-spacing:.06em;font-weight:600}
.m .v{font-weight:700;font-size:1.05rem;margin:3px 0 6px}
.row{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:8px;font-size:.9rem}
.mu{color:var(--mute);font-size:.85rem;margin-top:10px;line-height:1.45}
.pill{padding:2px 8px;border-radius:999px;font-size:.68rem;font-weight:700;white-space:nowrap}
.pill.Verified{background:rgba(52,211,153,.15);color:var(--ok)}
.pill.Estimated{background:rgba(251,191,36,.15);color:var(--warn)}
.pill.Unavailable{background:rgba(148,163,184,.15);color:#a8b3c7}
.sec{display:flex;align-items:center;gap:10px;margin:26px 0 4px;font-size:1.25rem;font-weight:800}
.sec:after{content:"";flex:1;height:1px;background:var(--line)}

/* ---------- streamlit widgets ---------- */
section[data-testid="stSidebar"]{background:#0D1322;border-right:1px solid var(--line)}
.stButton>button,.stFormSubmitButton>button{border-radius:12px;font-weight:700;border:1px solid var(--line);transition:all .15s}
.stButton>button:hover{border-color:var(--acc);color:var(--acc)}
.stButton>button[kind="primary"],.stFormSubmitButton>button[kind="primary"],.stFormSubmitButton>button{
  background:linear-gradient(135deg,var(--acc),var(--acc2));color:#04121a;border:none;
  box-shadow:0 6px 20px rgba(34,211,182,.30)}
.stButton>button[kind="primary"]:hover{filter:brightness(1.08);color:#04121a}
.stTabs [data-baseweb="tab-list"]{gap:6px;border-bottom:1px solid var(--line)}
.stTabs [data-baseweb="tab"]{border-radius:10px 10px 0 0;padding:10px 18px;font-weight:600}
.stTabs [aria-selected="true"]{color:var(--acc)}
div[data-baseweb="input"],div[data-baseweb="select"]>div{border-radius:12px}
@media(max-width:700px){.strip,.grid{grid-template-columns:repeat(2,1fr)}.hero h1{font-size:1.5rem}}
</style>
"""

STATUS = {0: ("st0", "✅ Makes your deadline even with delays"),
          1: ("st1", "⚠️ Risky: on time only if nothing goes wrong"),
          2: ("st2", "❌ Misses your deadline")}

ICON = {"Walk": "🚶", "Cycle": "🚴", ROAD: "🛺", "Metro": "🚇", "Train": "🚆", "Tram": "🚊", "Bus": "🚌"}


def pill(tag):
    return f'<span class="pill {tag}">{tag}</span>'


def row(text, tag):
    return f'<div class="row"><span>{text}</span>{pill(tag)}</div>'


def hero(subtitle):
    st.markdown(f'<div class="hero"><div class="logo">🛡️</div><div><h1>RouteGuard</h1>'
                f'<p>{subtitle}</p></div></div>', unsafe_allow_html=True)


def chips(items):
    st.markdown('<div class="chips">' + "".join(f'<span class="chip">{i}</span>' for i in items) + '</div>',
                unsafe_allow_html=True)


def section(title):
    st.markdown(f'<div class="sec">{title}</div>', unsafe_allow_html=True)


def summary_strip(ranked, deadline):
    """Four headline numbers above the results."""
    if not ranked:
        return
    safe = sum(1 for x in ranked if int(x["tier"]) == 0)
    best = ranked[0]
    fast = min(ranked, key=lambda x: x["time"])
    fares = [x for x in ranked if not math.isnan(x["fare"])]
    cheap = min(fares, key=lambda x: x["fare"]) if fares else None
    cheap_v = "Unknown" if not cheap else ("Free" if cheap["fare"] == 0 else f"₹{cheap['fare']:.0f}")
    cells = [("Best match", html.escape(best["name"]), f'score {best["score"]:.0f}/100'),
             ("Fastest", f'{fast["time"]:.0f} min', html.escape(fast["name"])),
             ("Cheapest", cheap_v, html.escape(cheap["name"]) if cheap else "no fare data"),
             ("Safe options", f"{safe} of {len(ranked)}", f"arrive within {deadline} min")]
    st.markdown('<div class="strip">' + "".join(
        f'<div class="stat"><div class="k">{k}</div><div class="v">{v}</div><div class="s">{s}</div></div>'
        for k, v, s in cells) + '</div>', unsafe_allow_html=True)


def legend():
    with st.expander("ⓘ What do Verified, Estimated and Unavailable mean?"):
        for tag, text in LEGEND.items():
            st.markdown(f'{pill(tag)} {text}', unsafe_allow_html=True)
        st.caption("Reliability and 'if delayed' times use rough assumptions (not measured). "
                   "Base reliability: " + ", ".join(f"{k} {v}" for k, v in REL_BASE.items())
                   + f". Each minute between vehicles lowers it by {HEADWAY_PENALTY}. "
                   "Delay allowance on moving time: "
                   + ", ".join(f"{k} {int(v * 100)}%" for k, v in DELAY.items())
                   + ". You can change these in config.py.")


def card(x, top):
    fare_nan = isinstance(x["fare"], float) and math.isnan(x["fare"])
    fare = "Unavailable" if fare_nan else ("Free" if x["fare"] == 0 else f"₹{x['fare']:.0f}")
    css, msg = STATUS[int(x["tier"])]
    km = "" if math.isnan(x["km"]) else f" · {x['km']:.1f} km"
    over = " (over budget)" if x["over_budget"] else ""
    ring = "" if x["score"] >= 65 else (" mid" if x["score"] >= 40 else " low")
    badge = '<span class="badge">BEST PICK</span>' if top else ""
    h = [f'<div class="card{" top" if top else ""}">',
         f'<div class="head"><div class="ico">{ICON.get(x["mode"], "🚏")}</div>'
         f'<div class="ttl"><b>{html.escape(x["name"])}</b>{badge}</div>'
         f'<div class="ring{ring}" style="--p:{x["score"]:.0f}"><span>{x["score"]:.0f}</span></div></div>',
         f'<div class="status {css}">{msg}</div>',
         '<div class="grid">',
         f'<div class="m"><div class="k">Time</div><div class="v">{x["time"]:.0f} min{km}</div>{pill(E)}</div>',
         f'<div class="m"><div class="k">If delayed</div><div class="v">{x["worst"]:.0f} min</div>'
         f'<div class="mu" style="margin:0 0 6px">spare {x["spare"]:.0f} min</div>{pill(E)}</div>',
         f'<div class="m"><div class="k">Fare</div><div class="v">{fare}{over}</div>{pill(x["fare_tag"])}</div>',
         f'<div class="m"><div class="k">Reliability</div><div class="v">{x["rel"]:.0f}%</div>{pill(E)}</div>',
         '</div>']
    if x["sched"]:
        h.append(row("🕒 Next departures: " + ", ".join(x["sched"]) + " (scheduled, not live)", V))
    h.append(f'<div class="mu">{html.escape(x["detail"])}</div>')
    if x["left_out"]:
        h.append(f'<div class="mu">Score ignores {", ".join(x["left_out"])} because the data is unavailable.</div>')
    return "".join(h) + "</div>"


def transit_card(t):
    fare = t["fare"]
    fare_row = row(f"Fare: ₹{fare:.0f} (typed by you)", V) if fare > 0 else row("Fare", U)
    refs = " ".join(f'<span class="badge" style="margin:0 4px 0 0">{html.escape(str(r))}</span>' for r in t["refs"])
    return (f'<div class="card"><div class="head"><div class="ico">{ICON.get(t["mode"], "🚏")}</div>'
            f'<div class="ttl"><b>{t["mode"]}</b></div></div>'
            f'<div class="row"><span>Routes serving both ends: {refs}</span>{pill(V)}</div>'
            f'<div class="mu">Walk {t["s"]["min"]:.0f} min ({t["s"]["m"]} m) to '
            f'<b>{html.escape(t["s"]["name"])}</b>, ride, get off near '
            f'<b>{html.escape(t["e"]["name"])}</b>, walk {t["e"]["min"]:.0f} min ({t["e"]["m"]} m)</div>'
            + row("Ride time and live arrival", U) + fare_row + '</div>')


def saved_card(trip, route, score, minutes, fare_txt, at):
    ring = "" if score >= 65 else (" mid" if score >= 40 else " low")
    return (f'<div class="card"><div class="head"><div class="ico">⭐</div>'
            f'<div class="ttl"><b>{html.escape(trip)}</b>'
            f'<div class="mu" style="margin:2px 0 0">{html.escape(route)} · {minutes:.0f} min · Fare: {fare_txt}</div></div>'
            f'<div class="ring{ring}" style="--p:{score:.0f}"><span>{score:.0f}</span></div></div>'
            f'<div class="mu">Saved {html.escape(str(at))} UTC</div></div>')


def place_picker(label, key):
    """Returns ((lat, lon), place name) or None."""
    q = st.text_input(label, key=key + "_q", placeholder="Type a place in Chennai, e.g. T. Nagar")
    opts = geocode(q)
    if not opts:
        if len(q.strip()) >= 3:
            st.caption("No places found. Try a different spelling.")
        return None
    i = st.selectbox("Pick the exact place", range(len(opts)),
                     format_func=lambda k: opts[k][0], key=key + "_s")
    return (opts[i][1], opts[i][2]), opts[i][0]
