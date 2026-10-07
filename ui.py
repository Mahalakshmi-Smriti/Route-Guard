"""RouteGuard: cards, colours, the Verified / Estimated / Unavailable labels and the place picker."""
import html
import math

import streamlit as st

from config import DELAY, E, HEADWAY_PENALTY, LEGEND, REL_BASE, U, V
from data import geocode

CSS = """
<style>
.hero{text-align:center;padding:1rem 0}
.card{border:1px solid #ddd;border-radius:12px;padding:12px;margin:8px 0;background:#fff;color:#222}
.card.top{border:2px solid #2e7d32}
.row{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:4px}
.mu{color:#666;font-size:.85rem;margin-top:4px}
.score{font-weight:700;font-size:1.2rem}
.pill{padding:2px 8px;border-radius:10px;font-size:.75rem;font-weight:600;white-space:nowrap}
.pill.Verified{background:#e8f5e9;color:#2e7d32}
.pill.Estimated{background:#fff8e1;color:#8d6e00}
.pill.Unavailable{background:#eeeeee;color:#666}
.st0{color:#2e7d32;font-weight:600}
.st1{color:#b26a00;font-weight:600}
.st2{color:#c62828;font-weight:600}
</style>
"""

STATUS = {0: ("st0", "✅ Makes your deadline even with delays"),
          1: ("st1", "⚠️ Risky: on time only if nothing goes wrong"),
          2: ("st2", "❌ Misses your deadline")}


def pill(tag):
    return f'<span class="pill {tag}">{tag}</span>'


def row(text, tag):
    return f'<div class="row"><span>{text}</span>{pill(tag)}</div>'


def legend():
    with st.expander("What do Verified, Estimated and Unavailable mean?"):
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
    over = " (over your budget)" if x["over_budget"] else ""
    h = [f'<div class="card{" top" if top else ""}">',
         f'<div class="row"><b>{"🏆 " if top else ""}{html.escape(x["name"])}</b>'
         f'<span class="score">{x["score"]:.0f}/100</span></div>',
         f'<div class="{css}">{msg}</div>',
         row(f'Time: {x["time"]:.0f} min{km}', E),
         row(f'If delayed: about {x["worst"]:.0f} min (spare {x["spare"]:.0f} min)', E),
         row(f'Fare: {fare}{over}', x["fare_tag"]),
         row(f'Reliability: {x["rel"]:.0f}%', E)]
    if x["sched"]:
        h.append(row("Next departures: " + ", ".join(x["sched"]) + " (scheduled, not live)", V))
    h.append(f'<div class="mu">{html.escape(x["detail"])}</div>')
    if x["left_out"]:
        h.append(f'<div class="mu">Score ignores {", ".join(x["left_out"])} because the data is unavailable.</div>')
    return "".join(h) + "</div>"


def transit_card(t):
    fare = t["fare"]
    fare_row = row(f"Fare: ₹{fare:.0f} (typed by you)", V) if fare > 0 else row("Fare", U)
    refs = ", ".join(html.escape(str(r)) for r in t["refs"])
    return (f'<div class="card"><div class="row"><b>{t["mode"]}</b></div>'
            f'<div>Route(s) serving both ends: <b>{refs}</b></div>'
            + row("Route numbers (OpenStreetMap map data)", V)
            + f'<div class="mu">Walk {t["s"]["min"]:.0f} min ({t["s"]["m"]} m) to '
              f'<b>{html.escape(t["s"]["name"])}</b>, ride, get off near '
              f'<b>{html.escape(t["e"]["name"])}</b>, walk {t["e"]["min"]:.0f} min ({t["e"]["m"]} m)</div>'
            + row("Ride time and live arrival", U) + fare_row + '</div>')


def place_picker(label, key):
    """Returns ((lat, lon), place name) or None."""
    q = st.text_input(label, key=key + "_q")
    opts = geocode(q)
    if not opts:
        if len(q.strip()) >= 3:
            st.caption("No places found. Try a different spelling.")
        return None
    i = st.selectbox("Pick the exact place", range(len(opts)),
                     format_func=lambda k: opts[k][0], key=key + "_s")
    return (opts[i][1], opts[i][2]), opts[i][0]
