"""RouteGuard: route scoring, result cards and place picker."""
import html

import pandas as pd
import streamlit as st

from config import BIKE, CAR, FOOT, MAX_WALK_MIN, NAN, ROAD, WEIGHTS
from data import geocode, road, routes_near, best_stop


# ------------------------------------------------------------ planning
def plan(a, b, deadline, budget, pri, ov):
    """Ranks only options that have REAL time data (walk, cycle, road). Returns a list of dicts."""
    foot, bike, car = road(a, b, FOOT), road(a, b, BIKE), road(a, b, CAR)
    rows = []
    if foot and foot[0] <= 5:
        rows.append(("Walk", foot[1], 0.0, "FREE", foot[0], "Real walking route"))
    if bike:
        rows.append(("Cycle", bike[1], 0.0, "FREE", bike[0], "Real cycling route (your own cycle)"))
    if car:
        f = ov.get(ROAD, 0)
        rows.append((ROAD, car[1], f if f > 0 else NAN, "VERIFIED" if f > 0 else "NA", car[0],
                     "Real road route, no live traffic. Auto / bike-taxi availability can't be checked"))
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["route", "time", "fare", "fs", "km", "detail"])
    df["buf"] = deadline - df["time"]
    tm = df["time"]
    c = pd.DataFrame({"cost": (1 - df["fare"] / budget).clip(0, 1),
                      "time": 1 - (tm - tm.min()) / (tm.max() - tm.min() + 1e-9),
                      "buf": (df["buf"] / 30).clip(0, 1)})
    w = pd.Series(WEIGHTS[pri])

    def score(row):
        ok = row.notna()
        return float((row[ok] * w[ok]).sum() / w[ok].sum() * 100)  # missing fare is left out, not guessed

    df["score"] = c.apply(score, axis=1)
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    return df.to_dict("records")


def transit(a, b, na, nb, ov):
    """Public transport only when OpenStreetMap shows a route serving BOTH ends and walkable stops exist."""
    ra, rb = routes_near(*a), routes_near(*b)
    out = []
    if ra is None or rb is None or not na or not nb:
        return None
    for mode in ("Bus", "Metro", "Train"):
        common = sorted({ref for (m, ref) in ra if m == mode} & {ref for (m, ref) in rb if m == mode})
        if not common or not na[mode] or not nb[mode]:
            continue
        s, e = best_stop(a, na[mode]), best_stop(b, nb[mode])
        if s and e and s["min"] <= MAX_WALK_MIN and e["min"] <= MAX_WALK_MIN:
            out.append(dict(mode=mode, refs=common[:8], s=s, e=e, fare=ov.get(mode, 0)))
    return out


# ------------------------------------------------------------ UI helpers
def pill(kind, text):
    return f'<span class="pill {kind}">{text}</span>'


def card(x, top):
    fare = "Free" if x["fs"] == "FREE" else f"₹{x['fare']:.0f}" if x["fs"] == "VERIFIED" else "Unavailable"
    fp = (pill("REAL", "Free") if x["fs"] == "FREE" else pill("VERIFIED", "Entered by you")
          if x["fs"] == "VERIFIED" else pill("UNAVAILABLE", "Unavailable"))
    return (f'<div class="card{" top" if top else ""}"><div class="row"><b>{html.escape(x["route"])}</b>'
            f'<span class="score">{x["score"]:.0f}</span></div>'
            f'<div class="row"><span>{x["time"]:.0f} min · {x["km"]:.1f} km</span>{pill("REAL", "Real route")}</div>'
            f'<div class="row"><span>Fare: {fare}</span>{fp}</div>'
            f'<div class="mu">{html.escape(x["detail"])}</div></div>')


def transit_card(t):
    fare = t["fare"]
    fp = pill("VERIFIED", f"₹{fare:.0f} entered by you") if fare > 0 else pill("UNAVAILABLE", "Fare unavailable")
    refs = ", ".join(html.escape(str(r)) for r in t["refs"])
    return (f'<div class="card"><div class="row"><b>{t["mode"]}</b>{fp}</div>'
            f'<div>Route(s) serving both ends: <b>{refs}</b></div>'
            f'<div class="mu">Walk {t["s"]["min"]:.0f} min ({t["s"]["m"]} m) to <b>{html.escape(t["s"]["name"])}</b> '
            f'→ ride → get off near <b>{html.escape(t["e"]["name"])}</b>, walk {t["e"]["min"]:.0f} min '
            f'({t["e"]["m"]} m)</div>'
            f'<div class="row"><span class="mu">Walking total: {t["s"]["min"] + t["e"]["min"]:.0f} min</span>'
            f'{pill("UNAVAILABLE", "Ride time / live ETA unavailable")}</div></div>')


def gtfs_card(t, ov):
    if t["fare"]:
        lo, hi = t["fare"]
        fp = pill("SCHED", f"₹{lo:.0f}" + (f"–₹{hi:.0f}" if hi > lo else "") + " from feed")
    elif ov.get(t["mode"], 0) > 0:
        fp = pill("VERIFIED", f"₹{ov[t['mode']]:.0f} entered by you")
    else:
        fp = pill("UNAVAILABLE", "Fare unavailable")

    if t["total"] is not None:
        every = f' (every ~{t["head_min"]:.0f} min)' if t["head_min"] else ""
        timing = (f'<div class="row"><span>{t["total"]:.0f} min total</span>'
                  f'{pill("SCHED", "Scheduled, not live")}</div>'
                  f'<div class="mu">Walk {t["wa"]:.0f} min + wait {t["wait"]:.0f} min + '
                  f'ride {t["ride"]:.0f} min + walk {t["wb"]:.0f} min</div>'
                  f'<div class="mu">Next departures: {", ".join(t["nxt"])}{every}</div>')
    else:
        timing = f'<div class="row">{pill("UNAVAILABLE", "No time data in feed")}</div>'

    head = f' → {html.escape(t["head"])}' if t["head"] else ""
    return (f'<div class="card"><div class="row"><b>{html.escape(t["mode"])} {html.escape(t["route"])}</b>{fp}</div>'
            f'<div class="mu">{head}</div>'
            f'<div class="mu">Board at <b>{html.escape(str(t["a"]))}</b> ({t["ma"]} m walk), '
            f'get off at <b>{html.escape(str(t["b"]))}</b> ({t["mb"]} m walk)</div>'
            f'{timing}</div>')


CSS = """
<style>
.hero{text-align:center;padding:1rem 0}
.card{border:1px solid #ddd;border-radius:12px;padding:12px;margin:8px 0;background:#fff;color:#222}
.card.top{border:2px solid #2e7d32}
.row{display:flex;justify-content:space-between;align-items:center;gap:8px}
.mu{color:#666;font-size:.85rem;margin-top:4px}
.score{font-weight:700;font-size:1.2rem}
.pill{padding:2px 8px;border-radius:10px;font-size:.75rem;font-weight:600}
.pill.REAL{background:#e8f5e9;color:#2e7d32}
.pill.VERIFIED{background:#e3f2fd;color:#1565c0}
.pill.SCHED{background:#fff8e1;color:#8d6e00}
.pill.UNAVAILABLE{background:#f5f5f5;color:#777}
</style>
"""




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

