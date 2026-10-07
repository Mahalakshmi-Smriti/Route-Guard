"""
RouteGuard - REAL DATA ONLY. Run: streamlit run app.py
Sources (free, no API key):
  Places ........ Nominatim (OpenStreetMap)
  Stops/routes .. Overpass API (OpenStreetMap)
  Walk/cycle/road OSRM + routing.openstreetmap.de
  Timetable ..... Chennai GTFS (scheduled, not live)
Not free anywhere: live bus/metro ETA, official fares, bike-taxi availability.
Those are shown as "Unavailable" unless the feed has them or YOU type a fare in the sidebar.

Needs: pip install streamlit pandas numpy requests
"""
import datetime as dt
import hashlib
import hmac
import html
import math
import os
import re
import sqlite3
import zipfile

import numpy as np
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="RouteGuard", page_icon="🛡️", layout="centered")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "routeguard.db")
UA = {"User-Agent": "RouteGuard-student-app/3.0"}
NOMINATIM = "https://nominatim.openstreetmap.org/search"
OVERPASS = ["https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter"]
CAR = "https://router.project-osrm.org/route/v1/driving/"
FOOT = "https://routing.openstreetmap.de/routed-foot/route/v1/driving/"
BIKE = "https://routing.openstreetmap.de/routed-bike/route/v1/driving/"
ROAD = "Auto / Cab / Bike taxi"
NAN = float("nan")
MAX_WALK_MIN = 15  # longest walk to a stop that we accept

GTFS_URL = "https://raw.githubusercontent.com/ungalsoththu/ChennaiGTFS/main/data/chennai-unified-gtfs.zip"
GTFS_FILE = os.path.join(BASE_DIR, "chennai-gtfs.zip")  # downloaded once, then reused
RTYPE = {"0": "Tram", "1": "Metro", "2": "Train", "3": "Bus"}

WEIGHTS = {"Balanced": dict(cost=.30, time=.40, buf=.30),
           "Cheapest": dict(cost=.60, time=.20, buf=.20),
           "Fastest": dict(cost=.10, time=.60, buf=.30),
           "Most spare time": dict(cost=.20, time=.20, buf=.60)}


# ------------------------------------------------------------ database (users + saved trips)
def db(sql, args=()):
    con = sqlite3.connect(DB)
    try:
        cur = con.cursor()
        cur.execute(sql, args)
        rows = cur.fetchall()
        con.commit()
        return rows
    finally:
        con.close()


def init_db():
    db("CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, name TEXT, salt TEXT, pw TEXT)")
    db("""CREATE TABLE IF NOT EXISTS saved(id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT, trip TEXT,
          route TEXT, score REAL, fare REAL, minutes REAL, at TEXT DEFAULT CURRENT_TIMESTAMP)""")


# ------------------------------------------------------------ authentication
def hp(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000).hex()


def sign_up(name, email, pw):
    """Returns an error message, or None when the account was created."""
    email = email.strip().lower()
    if not name.strip():
        return "Enter your name."
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return "Enter a valid email."
    if len(pw) < 8 or pw.isalpha() or pw.isdigit():
        return "Password needs 8+ characters with letters and numbers."
    if db("SELECT 1 FROM users WHERE email=?", (email,)):
        return "An account with this email already exists."
    salt = os.urandom(16)
    db("INSERT INTO users VALUES(?,?,?,?)", (email, name.strip(), salt.hex(), hp(pw, salt)))
    return None


def sign_in(email, pw):
    """Returns the user's name on success, else None."""
    row = db("SELECT name,salt,pw FROM users WHERE email=?", (email.strip().lower(),))
    if row and hmac.compare_digest(row[0][2], hp(pw, bytes.fromhex(row[0][1]))):
        return row[0][0]
    return None


def log_in_session(email, name):
    st.session_state.clear()
    st.session_state.update(user=email.strip().lower(), name=name, fails=0)


def log_out():
    st.session_state.clear()
    st.rerun()


def auth_screen():
    st.markdown('<div class="hero"><h1>🛡️ RouteGuard</h1><p>Know the route. Know the uncertainty.</p></div>',
                unsafe_allow_html=True)
    if st.session_state.get("fails", 0) >= 5:
        st.error("Too many failed attempts. Refresh the page and try again later.")
        st.stop()

    t1, t2 = st.tabs(["Sign in", "Create account"])

    with t1:
        with st.form("in"):
            em = st.text_input("Email")
            pw = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", use_container_width=True)
        if submitted:
            name = sign_in(em, pw)
            if name:
                log_in_session(em, name)
                st.rerun()
            st.session_state.fails = st.session_state.get("fails", 0) + 1
            st.error("Incorrect email or password.")

    with t2:
        with st.form("up"):
            nm = st.text_input("Full name")
            em2 = st.text_input("Email ")
            p1 = st.text_input("Password ", type="password")
            p2 = st.text_input("Confirm password", type="password")
            created = st.form_submit_button("Create account", use_container_width=True)
        if created:
            err = "Passwords do not match." if p1 != p2 else sign_up(nm, em2, p1)
            if err:
                st.error(err)
            else:
                log_in_session(em2, nm.strip())  # sign the new user straight in
                st.rerun()
    st.stop()


# ------------------------------------------------------------ real data fetchers
# Cached functions RAISE on failure, so a failed call is never cached for an hour.
def hav(a, b, c, d):
    p1, p2, dl = math.radians(a), math.radians(c), math.radians(d - b)
    x = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))


@st.cache_data(ttl=3600, show_spinner=False)
def _geocode(q):
    r = requests.get(NOMINATIM, headers=UA, timeout=10,
                     params={"q": q + ", Chennai", "format": "json", "limit": 6, "countrycodes": "in"})
    r.raise_for_status()
    return [(x["display_name"][:80], float(x["lat"]), float(x["lon"])) for x in r.json()]


def geocode(q):
    try:
        return _geocode(q.strip()) if len(q.strip()) >= 3 else []
    except Exception:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def _route(base, a, b):
    r = requests.get(f"{base}{a[1]},{a[0]};{b[1]},{b[0]}", params={"overview": "false"},
                     headers=UA, timeout=12)
    r.raise_for_status()
    j = r.json()
    if j.get("code") != "Ok":
        raise ValueError("no route")
    x = j["routes"][0]
    return x["distance"] / 1000, x["duration"] / 60  # km, minutes


def road(a, b, base=CAR):
    try:
        return _route(base, tuple(a), tuple(b))
    except Exception:
        return None


def overpass(q):
    last = None
    for url in OVERPASS:
        try:
            r = requests.post(url, data={"data": q}, headers=UA, timeout=35)
            r.raise_for_status()
            return r.json()["elements"]
        except Exception as e:
            last = e
    raise last


def kind_of(t):
    txt = (t.get("network", "") + " " + t.get("name", "") + " " + t.get("operator", "")).lower()
    if t.get("amenity") == "taxi":
        return "Auto stand"
    if t.get("highway") == "bus_stop" or t.get("bus") == "yes":
        return "Bus"
    if t.get("railway"):
        if t.get("railway") == "subway_entrance" or t.get("station") == "subway" or "metro" in txt:
            return "Metro"
        return "Train"
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def _nearby(lat, lon, r):
    q = f"""[out:json][timeout:25];(
    node(around:{r},{lat},{lon})["highway"="bus_stop"];
    node(around:{r},{lat},{lon})["railway"~"^(station|halt|subway_entrance|tram_stop)$"];
    node(around:{r},{lat},{lon})["amenity"="taxi"];);out body 400;"""
    out = {"Bus": [], "Metro": [], "Train": [], "Auto stand": []}
    for e in overpass(q):
        t = e.get("tags", {})
        k = kind_of(t)
        if k:
            out[k].append(dict(name=t.get("name") or "(unnamed stop)",
                               m=round(hav(lat, lon, e["lat"], e["lon"]) * 1000),
                               lat=e["lat"], lon=e["lon"]))
    for k in out:
        out[k].sort(key=lambda x: x["m"])
    return out


def nearby(lat, lon, r=1000):
    try:
        return _nearby(lat, lon, r)
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def _routes_near(lat, lon, r):
    """Real bus / metro / train ROUTE numbers (OSM route relations) that serve stops near a point."""
    q = f"""[out:json][timeout:25];(
    node(around:{r},{lat},{lon})["highway"="bus_stop"];
    node(around:{r},{lat},{lon})["railway"~"^(station|halt|subway_entrance|tram_stop)$"];
    node(around:{r},{lat},{lon})["public_transport"~"^(platform|stop_position|station)$"];)->.s;
    rel(bn.s)["route"~"^(bus|subway|light_rail|train|tram)$"];out tags;"""
    mode = {"bus": "Bus", "subway": "Metro", "light_rail": "Train", "train": "Train", "tram": "Train"}
    res = {}
    for e in overpass(q):
        t = e.get("tags", {})
        res[(mode[t["route"]], t.get("ref") or t.get("name", "?"))] = t.get("name", "")
    return res


def routes_near(lat, lon, r=1000):
    try:
        return _routes_near(lat, lon, r)
    except Exception:
        return None


def best_stop(p, lst, top=3):
    """Among the nearest few stops, pick the one with the shortest REAL walking time."""
    best = None
    for s in lst[:top]:
        w = road(p, (s["lat"], s["lon"]), FOOT)
        if w and (best is None or w[1] < best["min"]):
            best = dict(name=s["name"], m=round(w[0] * 1000), min=w[1], lat=s["lat"], lon=s["lon"])
    return best


# ------------------------------------------------------------ GTFS (real scheduled timetable)
def hav_np(lat, lon, la, lo):
    p1, p2, dl = np.radians(lat), np.radians(la), np.radians(lo - lon)
    x = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 12742 * np.arcsin(np.sqrt(x))


def _entry(z, name):
    for n in z.namelist():
        if n == name or n.endswith("/" + name):
            return n
    return None


def _read(name):
    with zipfile.ZipFile(GTFS_FILE) as z:
        n = _entry(z, name)
        if not n:
            return None
        with z.open(n) as f:
            return pd.read_csv(f, dtype=str)


@st.cache_resource(show_spinner="Loading Chennai GTFS timetable (first time only)...")
def gtfs_tables():
    """cache_resource shares one copy of the tables (no per-rerun copying). Never modify them in place."""
    if not os.path.exists(GTFS_FILE):
        with requests.get(GTFS_URL, headers=UA, stream=True, timeout=90) as r:
            r.raise_for_status()
            with open(GTFS_FILE + ".part", "wb") as f:
                for ch in r.iter_content(1 << 20):
                    f.write(ch)
        os.replace(GTFS_FILE + ".part", GTFS_FILE)
    stops = _read("stops.txt")
    stops["lat"] = pd.to_numeric(stops.stop_lat, errors="coerce")
    stops["lon"] = pd.to_numeric(stops.stop_lon, errors="coerce")
    return dict(stops=stops.dropna(subset=["lat", "lon"]), routes=_read("routes.txt"), trips=_read("trips.txt"),
                cal=_read("calendar.txt"), cald=_read("calendar_dates.txt"),
                fa=_read("fare_attributes.txt"), fr=_read("fare_rules.txt"))


@st.cache_data(show_spinner=False)
def gtfs_stop_times(stop_ids):
    """Reads the big stop_times file in chunks and keeps only rows for the stops near you."""
    keep, want = [], set(stop_ids)
    cols = ("trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time")
    with zipfile.ZipFile(GTFS_FILE) as z, z.open(_entry(z, "stop_times.txt")) as f:
        for ch in pd.read_csv(f, dtype=str, chunksize=400_000, usecols=lambda c: c in cols):
            keep.append(ch[ch.stop_id.isin(want)])
    return pd.concat(keep, ignore_index=True)


def active_services(T, day):
    """Service IDs running on this date. Returns (set or None, note)."""
    ymd, wd = day.strftime("%Y%m%d"), day.strftime("%A").lower()
    cal, cd = T["cal"], T["cald"]
    if cal is None and cd is None:
        return None, ""
    act = set()
    if cal is not None and wd in cal.columns:
        act = set(cal[(cal.start_date <= ymd) & (cal.end_date >= ymd) & (cal[wd] == "1")].service_id)
    if cd is not None:
        d = cd[cd.date == ymd]
        act |= set(d[d.exception_type == "1"].service_id)
        act -= set(d[d.exception_type == "2"].service_id)
    if not act:
        return None, "The feed's calendar does not cover this date, so every timetable pattern is shown."
    return act, ""


def gtfs_fare(T, rid):
    fa, fr = T["fa"], T["fr"]
    if fa is None or fr is None or "route_id" not in fr:
        return None
    p = pd.to_numeric(fa[fa.fare_id.isin(fr[fr.route_id == rid].fare_id)].price, errors="coerce").dropna()
    return (p.min(), p.max()) if len(p) else None


def hhmm(s):
    return f"{int(s // 3600) % 24:02d}:{int(s % 3600 // 60):02d}"


def gtfs_options(A, B, depart, day, walk_m=900):
    T = gtfs_tables()
    S = T["stops"]

    def near(p):
        d = hav_np(p[0], p[1], S.lat.values, S.lon.values) * 1000
        return S[d <= walk_m].assign(m=d[d <= walk_m])

    sa, sb = near(A), near(B)
    if sa.empty or sb.empty:
        return [], ""
    st_ = gtfs_stop_times(tuple(sorted(set(sa.stop_id) | set(sb.stop_id)))).copy()
    for c in ("arrival_time", "departure_time"):
        st_[c] = pd.to_timedelta(st_[c], errors="coerce").dt.total_seconds() if c in st_ else np.nan
    st_["seq"] = pd.to_numeric(st_.stop_sequence, errors="coerce")
    j = st_[st_.stop_id.isin(sa.stop_id)].merge(st_[st_.stop_id.isin(sb.stop_id)], on="trip_id",
                                                suffixes=("_a", "_b"))
    j = j[j.seq_a < j.seq_b]  # same trip, boarding stop comes BEFORE the alighting stop
    if j.empty:
        return [], ""
    j = j.merge(T["trips"].reindex(columns=["trip_id", "route_id", "service_id", "trip_headsign"]), on="trip_id")
    j = j.merge(T["routes"].reindex(columns=["route_id", "route_short_name", "route_long_name", "route_type"]),
                on="route_id", how="left")
    act, note = active_services(T, day)
    if act is not None:
        j = j[j.service_id.isin(act)]
    cols = ["stop_id", "stop_name", "m", "lat", "lon"]
    j = j.merge(sa[cols].add_suffix("_a"), on="stop_id_a").merge(sb[cols].add_suffix("_b"), on="stop_id_b")

    # Shortlist the 15 routes with the closest stops first, so we make at most ~30 walking-route calls.
    groups = [((g.m_a + g.m_b).min(), rid, g) for rid, g in j.groupby("route_id")]
    groups.sort(key=lambda x: x[0])

    out = []
    for _, rid, g in groups[:15]:
        g = g.assign(pair=g.m_a + g.m_b)
        best = g.sort_values("pair").iloc[0]
        wa = road(A, (float(best.lat_a), float(best.lon_a)), FOOT)
        wb = road(B, (float(best.lat_b), float(best.lon_b)), FOOT)
        if not wa or not wb or wa[1] > MAX_WALK_MIN or wb[1] > MAX_WALK_MIN:
            continue
        g = g[(g.stop_id_a == best.stop_id_a) & (g.stop_id_b == best.stop_id_b)].copy()
        g["dep"] = g.departure_time_a.fillna(g.arrival_time_a)
        g["arr"] = g.arrival_time_b.fillna(g.departure_time_b)
        g = g.dropna(subset=["dep", "arr"])
        name = best.route_short_name if pd.notna(best.route_short_name) else best.route_long_name
        e = dict(rid=rid, route=str(name), mode=RTYPE.get(best.route_type, "Transit"),
                 head=best.trip_headsign if pd.notna(best.trip_headsign) else "",
                 a=best.stop_name_a, b=best.stop_name_b, wa=wa[1], wb=wb[1], ma=round(wa[0] * 1000),
                 mb=round(wb[0] * 1000), total=None, ride=None, wait=None, nxt=[], head_min=None,
                 fare=gtfs_fare(T, rid))
        if not g.empty:
            ready = depart + wa[1] * 60  # time you reach the boarding stop
            nxt = np.sort(g.dep[g.dep >= ready].unique())
            if len(nxt) == 0:
                continue  # no more departures after you arrive
            e["ride"] = float((g.arr - g.dep).median() / 60)
            e["wait"] = float((nxt[0] - ready) / 60)
            e["total"] = wa[1] + e["wait"] + e["ride"] + wb[1]
            e["nxt"] = [hhmm(x) for x in nxt[:4]]
            if len(nxt) > 1:
                e["head_min"] = float(np.median(np.diff(nxt[:8])) / 60)
        out.append(e)
    out.sort(key=lambda x: (x["total"] is None, x["total"] or 0))
    return out[:8], note


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
            f'<div>Route(s) servi
