"""
RouteGuard - Trust-First Commute Intelligence (Foundation of Data Science micro-project)
Run:  streamlit run app.py
NOTE: All stops, routes and trip logs below are SAMPLE / SYNTHETIC data for demo.
      Replace the seed functions with real MTC / Metro / survey data when available.
"""
import math
import sqlite3
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.ensemble import RandomForestRegressor

DB = "routeguard.db"
V, E, U = "VERIFIED", "ESTIMATED", "UNAVAILABLE"
BADGE = {V: "🟢 Verified", E: "🟡 Estimated", U: "🔴 Unavailable"}

# ---------------------------------------------------------------- 1. DATA LAYER
STOPS = [  # name, lat, lon  (approximate coordinates - verify on OpenStreetMap)
    ("Velammal College (Surapet)", 13.1260, 80.1790),
    ("Anna Nagar", 13.0850, 80.2101),
    ("Koyambedu", 13.0694, 80.1948),
    ("Ambattur", 13.1143, 80.1548),
    ("Padi", 13.1000, 80.1900),
    ("Villivakkam", 13.1080, 80.2060),
]
# id, name, origin, dest, mode, fare(None=unknown), base_min, sd, live_age_min, live_eta
ROUTES = [
    (1, "MTC 59 Bus", "Anna Nagar", "Velammal College (Surapet)", "Bus", 15, 45, 8, 3, 42),
    (2, "MTC 70 Bus", "Koyambedu", "Velammal College (Surapet)", "Bus", 20, 38, 5, 25, None),
    (3, "Metro + Share Auto", "Anna Nagar", "Velammal College (Surapet)", "Metro", 35, 32, 4, 40, None),
    (4, "Suburban Train + Walk", "Ambattur", "Velammal College (Surapet)", "Train", 25, 35, 3, 2, 34),
    (5, "Share Auto", "Padi", "Velammal College (Surapet)", "Auto", None, 28, 10, None, None),
]


def haversine(lat1, lon1, lat2, lon2):
    r = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def init_db():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS stops(name TEXT, lat REAL, lon REAL)")
    cur.execute("""CREATE TABLE IF NOT EXISTS routes(id INT, name TEXT, origin TEXT, dest TEXT,
                   mode TEXT, fare REAL, base_min REAL, sd REAL, live_age REAL, live_eta REAL)""")
    cur.execute("CREATE TABLE IF NOT EXISTS trips(route_id INT, hour INT, weekday INT, travel_min REAL)")
    if cur.execute("SELECT COUNT(*) FROM stops").fetchone()[0] == 0:
        cur.executemany("INSERT INTO stops VALUES(?,?,?)", STOPS)
        cur.executemany("INSERT INTO routes VALUES(?,?,?,?,?,?,?,?,?,?)", ROUTES)
        rng = np.random.default_rng(42)
        rows = []
        for r in ROUTES:
            rid, base, sd = r[0], r[6], r[7]
            for _ in range(250):
                h, wd = int(rng.integers(6, 21)), int(rng.integers(0, 6))
                peak = 0.25 * base if h in (8, 9, 17, 18, 19) else 0
                t = max(10, base + peak + rng.normal(0, sd))
                rows.append((rid, h, wd, round(float(t), 1)))
        cur.executemany("INSERT INTO trips VALUES(?,?,?,?)", rows)
    con.commit()
    con.close()


@st.cache_data
def load():
    init_db()
    con = sqlite3.connect(DB)
    out = [pd.read_sql(f"SELECT * FROM {t}", con) for t in ("stops", "routes", "trips")]
    con.close()
    return out


# ---------------------------------------------------------------- 2. DS LAYER
@st.cache_resource
def train(trips: pd.DataFrame):
    X, y = trips[["route_id", "hour", "weekday"]], trips["travel_min"]
    return RandomForestRegressor(n_estimators=120, random_state=1).fit(X, y)


def predict(model, rid, hour, wd):
    x = pd.DataFrame([[rid, hour, wd]], columns=["route_id", "hour", "weekday"])
    preds = np.array([t.predict(x.values)[0] for t in model.estimators_])
    return preds.mean(), preds.std()


def reliability_stats(trips, rid):
    t = trips[trips.route_id == rid].travel_min
    base = t.median()
    return t.std(), float((t <= base * 1.15).mean()), len(t)


WEIGHTS = {  # cost, time, reliability, buffer, walk
    "Balanced": dict(cost=.25, time=.25, rel=.2, buf=.2, walk=.1),
    "Cheapest": dict(cost=.55, time=.15, rel=.1, buf=.1, walk=.1),
    "Fastest": dict(cost=.1, time=.55, rel=.1, buf=.15, walk=.1),
    "Most reliable": dict(cost=.1, time=.1, rel=.4, buf=.3, walk=.1),
}


def rank(stops, routes, trips, model, home, budget, deadline_min, hour, wd, priority, max_walk):
    hlat, hlon = stops.loc[stops.name == home, ["lat", "lon"]].iloc[0]
    rows = []
    for _, r in routes.iterrows():
        o = stops.loc[stops.name == r.origin].iloc[0]
        walk_km = haversine(hlat, hlon, o.lat, o.lon)
        if walk_km > max_walk:
            continue
        sd, ontime, n = reliability_stats(trips, r.id)
        pred, pred_sd = predict(model, r.id, hour, wd)
        # trust states
        live_ok = pd.notna(r.live_age) and r.live_age <= 10 and pd.notna(r.live_eta)
        time_min, t_state = (r.live_eta, V) if live_ok else ((pred, E) if n >= 30 else (None, U))
        fare_state = U if pd.isna(r.fare) else V
        walk_min = walk_km / 5 * 60
        total = None if time_min is None else time_min + walk_min
        buffer = None if total is None else deadline_min - total
        fresh = 1.0 if live_ok else (0.3 if pd.isna(r.live_age) else max(0.0, 1 - r.live_age / 60))
        conf = 0.4 * fresh + 0.3 * min(n / 200, 1) + 0.3 * (1 - min(pred_sd / 10, 1))
        rows.append(dict(route=r["name"], origin=r.origin, mode=r["mode"], fare=r.fare, fare_state=fare_state,
                         time=total, time_state=t_state, walk_km=walk_km, walk_min=walk_min,
                         rel=0.6 * ontime + 0.4 * (1 - min(sd / 15, 1)), ontime=ontime,
                         buffer=buffer, confidence=conf))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # component scores in [0,1]; None -> excluded (never guessed)
    def norm_inv(col):
        s = df[col].astype(float)
        return 1 - (s - s.min()) / (s.max() - s.min() + 1e-9)
    comp = pd.DataFrame(index=df.index)
    comp["cost"] = np.where(df.fare.isna(), np.nan, np.clip(1 - df.fare / budget, 0, 1))
    comp["time"] = norm_inv("time")
    comp["rel"] = df.rel
    comp["buf"] = np.where(df.buffer.isna(), np.nan, np.clip(df.buffer / 30, 0, 1))
    comp["walk"] = np.clip(1 - df.walk_km / max_walk, 0, 1)
    w = pd.Series(WEIGHTS[priority])
    scores = []
    for i in df.index:
        c = comp.loc[i]
        ok = c.notna()
        scores.append(float((c[ok] * w[ok]).sum() / w[ok].sum()) * 100)
    df["score"] = scores
    df["over_budget"] = df.fare > budget
    return df.sort_values("score", ascending=False).reset_index(drop=True)


def explain(best, df, budget, deadline_min):
    why = [f"**{best.route}** scores highest ({best.score:.0f}/100) for your chosen priority."]
    if pd.isna(best.fare):
        why.append("Fare is **unavailable** - RouteGuard did not guess it, so cost was left out of this score.")
    else:
        why.append(f"Fare ₹{best.fare:.0f} fits your ₹{budget} budget." if not best.over_budget
                   else f"Fare ₹{best.fare:.0f} is above your ₹{budget} budget.")
    if best.buffer is not None and not pd.isna(best.buffer):
        why.append(f"You arrive with ~{best.buffer:.0f} min spare before your deadline."
                   if best.buffer >= 0 else f"Warning: you may be ~{-best.buffer:.0f} min late.")
    why.append(f"Historically on time {best.ontime*100:.0f}% of trips; time is {BADGE[best.time_state]}.")
    if len(df) > 1:
        alt = df.iloc[1]
        why.append(f"Runner-up: {alt.route} ({alt.score:.0f}/100).")
    return " ".join(why)


# ---------------------------------------------------------------- 3. UI
st.set_page_config(page_title="RouteGuard", page_icon="🛡️", layout="wide")
st.title("🛡️ RouteGuard")
st.caption("Know the route. Know the uncertainty.  (Demo uses sample data)")

stops, routes, trips = load()
model = train(trips)

with st.sidebar:
    st.header("Your trip")
    home = st.selectbox("Starting locality", [s for s in stops.name if "Velammal" not in s], index=4)
    budget = st.slider("Daily budget (₹)", 20, 50, 30, 5)
    deadline = st.slider("Minutes until deadline", 20, 120, 60, 5)
    hour = st.slider("Departure hour", 6, 20, 8)
    wd = st.selectbox("Day", list(range(6)), format_func=lambda i: "Mon Tue Wed Thu Fri Sat".split()[i])
    priority = st.radio("Priority", list(WEIGHTS))
    max_walk = st.slider("Max walk to a stop (km)", 0.5, 5.0, 3.0, 0.5)

df = rank(stops, routes, trips, model, home, budget, deadline, hour, wd, priority, max_walk)
if df.empty:
    st.warning("No routes within walking range. Increase the walking limit.")
    st.stop()

best = df.iloc[0]
st.success(explain(best, df, budget, deadline))

show = df.assign(
    Fare=[("₹%d" % f if pd.notna(f) else "—") + " " + BADGE[s].split()[0] for f, s in zip(df.fare, df.fare_state)],
    Time=[("%.0f min" % t if pd.notna(t) else "—") + " " + BADGE[s].split()[0] for t, s in zip(df.time, df.time_state)],
    Score=df.score.round(0), Confidence=(df.confidence * 100).round(0).astype(int).astype(str) + "%",
    Walk=df.walk_km.round(1).astype(str) + " km",
)[["route", "origin", "Fare", "Time", "Walk", "Score", "Confidence"]]
st.dataframe(show, use_container_width=True, hide_index=True)
st.caption("🟢 Verified (fresh live source)   🟡 Estimated (model / history)   🔴 Unavailable (not guessed)")

c1, c2 = st.columns(2)
with c1:
    st.subheader("Route scores")
    st.plotly_chart(px.bar(df, x="route", y="score", color="confidence", range_y=[0, 100]), use_container_width=True)
with c2:
    st.subheader("What-if: change the budget")
    wi = []
    for b in (20, 30, 40, 50):
        d = rank(stops, routes, trips, model, home, b, deadline, hour, wd, priority, max_walk)
        wi.append(dict(budget=f"₹{b}", best_route=d.iloc[0].route, score=round(d.iloc[0].score)))
    st.dataframe(pd.DataFrame(wi), hide_index=True, use_container_width=True)

st.subheader("Nearby better-connected stops (computed from coordinates)")
hlat, hlon = stops.loc[stops.name == home, ["lat", "lon"]].iloc[0]
near = stops.assign(km=[haversine(hlat, hlon, a, b) for a, b in zip(stops.lat, stops.lon)])
near["routes_serving"] = near.name.map(routes.groupby("origin").size()).fillna(0).astype(int)
near = near[(near.name != home) & (near.km <= max_walk) & (near.routes_serving > 0)]
st.dataframe(near.sort_values("routes_serving", ascending=False)[["name", "km", "routes_serving"]].round(1),
             hide_index=True, use_container_width=True)
st.map(stops.rename(columns={"lon": "longitude", "lat": "latitude"}))
