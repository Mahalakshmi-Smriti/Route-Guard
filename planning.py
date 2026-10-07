"""RouteGuard: builds every option, estimates reliability, checks the deadline and ranks."""
import pandas as pd

from config import (BIKE, CAR, DELAY, E, FOOT, HEADWAY_PENALTY, MAX_WALK_MIN, NAN, REL_BASE, ROAD,
                    U, V, WEIGHTS)
from data import best_stop, road, routes_near

COMPONENTS = {"cost": "cost", "time": "travel time", "buf": "spare time", "rel": "reliability"}


def make_option(name, mode, time, km, fare, fare_tag, detail, ride=None, headway=None, sched=None):
    """One row. time = expected minutes. worst = time if delays happen (an ESTIMATE)."""
    ride = time if ride is None else ride
    rel = max(0.0, REL_BASE.get(mode, 65) - (HEADWAY_PENALTY * headway if headway else 0))
    worst = time + DELAY.get(mode, .4) * ride + (headway or 0)
    return dict(name=name, mode=mode, time=time, worst=worst, km=km, fare=fare, fare_tag=fare_tag,
                rel=rel, detail=detail, sched=sched or [])


def transit_fare(t, ov):
    if t["fare"]:
        return float(t["fare"][1]), V, "fare from timetable feed"
    if ov.get(t["mode"], 0) > 0:
        return float(ov[t["mode"]]), V, "fare typed by you"
    return NAN, U, "no fare data"


def build_options(a, b, ov, gtfs):
    out = []
    foot, bike, car = road(a, b, FOOT), road(a, b, BIKE), road(a, b, CAR)
    if foot and foot[0] <= 5:
        out.append(make_option("Walk", "Walk", foot[1], foot[0], 0.0, V, "Walking route on OpenStreetMap paths"))
    if bike:
        out.append(make_option("Cycle", "Cycle", bike[1], bike[0], 0.0, V, "Cycling route (your own cycle)"))
    if car:
        f = ov.get(ROAD, 0)
        out.append(make_option(ROAD, ROAD, car[1], car[0], f if f > 0 else NAN, V if f > 0 else U,
                               "Road route with no live traffic. Whether an auto or bike taxi is "
                               "available cannot be checked"))
    skipped = 0
    for t in gtfs:
        if t["total"] is None:
            skipped += 1
            continue
        fare, tag, why = transit_fare(t, ov)
        head = f" → {t['head']}" if t["head"] else ""
        detail = (f"Board at {t['a']} ({t['ma']} m walk), get off at {t['b']} ({t['mb']} m walk){head}. "
                  f"Walk {t['wa']:.0f} + wait {t['wait']:.0f} + ride {t['ride']:.0f} + walk {t['wb']:.0f} min. "
                  f"({why})")
        out.append(make_option(f"{t['mode']} {t['route']}", t["mode"], t["total"], NAN, fare, tag, detail,
                               ride=t["ride"], headway=t["head_min"], sched=t["nxt"]))
    return out, skipped


def rank(options, deadline, budget, pri):
    """Scores 0-100 from cost, time, spare time and reliability. Missing data is left out, never guessed."""
    if not options:
        return []
    df = pd.DataFrame(options)
    df["spare"] = deadline - df["worst"]
    # 0 = safe even with delays, 1 = on time only if nothing goes wrong, 2 = misses the deadline
    df["tier"] = df.apply(lambda r: 0 if r.worst <= deadline else (1 if r.time <= deadline else 2), axis=1)
    tm = df["time"]
    c = pd.DataFrame({"cost": (1 - df["fare"] / budget).clip(0, 1),
                      "time": 1 - (tm - tm.min()) / (tm.max() - tm.min() + 1e-9),
                      "buf": (df["spare"] / 30).clip(0, 1),
                      "rel": df["rel"] / 100})
    w = pd.Series(WEIGHTS[pri])
    scores, left_out = [], []
    for _, row in c.iterrows():
        ok = row.notna()
        scores.append(float((row[ok] * w[ok]).sum() / w[ok].sum() * 100))
        left_out.append([COMPONENTS[k] for k in row.index[~ok]])
    df["score"], df["left_out"] = scores, left_out
    df["over_budget"] = df["fare"] > budget
    return df.sort_values(["tier", "score"], ascending=[True, False]).reset_index(drop=True).to_dict("records")


def transit(a, b, na, nb, ov):
    """Route numbers from OpenStreetMap that serve BOTH ends. No timing exists in this source."""
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
