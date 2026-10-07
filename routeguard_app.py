"""
RouteGuard v2 - new UI, secure sign up / sign in, saved trips, EDA.   Run: streamlit run app.py
All stops/routes/trip logs are SAMPLE data. Passwords are salted PBKDF2-SHA256 hashes (never stored in plain text).
"""
import hmac, math, os, re, sqlite3
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from sklearn.ensemble import RandomForestRegressor

DB = "routeguard.db"
V, E, U = "VERIFIED", "ESTIMATED", "UNAVAILABLE"
LBL = {V: "Verified", E: "Estimated", U: "Unavailable"}
STOPS = [("Velammal College (Surapet)", 13.1260, 80.1790), ("Anna Nagar", 13.0850, 80.2101),
         ("Koyambedu", 13.0694, 80.1948), ("Ambattur", 13.1143, 80.1548),
         ("Padi", 13.1000, 80.1900), ("Villivakkam", 13.1080, 80.2060)]
ROUTES = [(1, "MTC 59 Bus", "Anna Nagar", "Bus", 15, 45, 8, 3, 42),
          (2, "MTC 70 Bus", "Koyambedu", "Bus", 20, 38, 5, 25, None),
          (3, "Metro + Share Auto", "Anna Nagar", "Metro", 35, 32, 4, 40, None),
          (4, "Suburban Train + Walk", "Ambattur", "Train", 25, 35, 3, 2, 34),
          (5, "Share Auto", "Padi", "Auto", None, 28, 10, None, None)]
WEIGHTS = {"Balanced": dict(cost=.25, time=.25, rel=.2, buf=.2, walk=.1),
           "Cheapest": dict(cost=.55, time=.15, rel=.1, buf=.1, walk=.1),
           "Fastest": dict(cost=.1, time=.55, rel=.1, buf=.15, walk=.1),
           "Most reliable": dict(cost=.1, time=.1, rel=.4, buf=.3, walk=.1)}


# ------------------------------------------------------------ database
def db(sql, args=(), many=None):
    con = sqlite3.connect(DB)
    cur = con.cursor()
    if many:
        cur.executemany(sql, many)
    else:
        cur.execute(sql, args)
    rows = cur.fetchall()
    con.commit()
    con.close()
    return rows


def init_db():
    db("CREATE TABLE IF NOT EXISTS stops(name TEXT, lat REAL, lon REAL)")
    db("""CREATE TABLE IF NOT EXISTS routes(id INT, name TEXT, origin TEXT, mode TEXT, fare REAL,
          base_min REAL, sd REAL, live_age REAL, live_eta REAL)""")
    db("CREATE TABLE IF NOT EXISTS trips(route_id INT, hour INT, weekday INT, travel_min REAL)")
    db("CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, name TEXT, salt TEXT, pw TEXT)")
    db("""CREATE TABLE IF NOT EXISTS saved(id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT, start TEXT,
          route TEXT, score REAL, fare REAL, minutes REAL, at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    if not db("SELECT 1 FROM stops"):
        db("INSERT INTO stops VALUES(?,?,?)", many=STOPS)
        db("INSERT INTO routes VALUES(?,?,?,?,?,?,?,?,?)", many=ROUTES)
        rng, rows = np.random.default_rng(42), []
        for r in ROUTES:
            for _ in range(250):
                h, wd = int(rng.integers(6, 21)), int(rng.integers(0, 6))
                t = max(10, r[5] + (0.25 * r[5] if h in (8, 9, 17, 18, 19) else 0) + rng.normal(0, r[6]))
                rows.append((r[0], h, wd, round(float(t), 1)))
        db("INSERT INTO trips VALUES(?,?,?,?)", many=rows)


# ------------------------------------------------------------ authentication
def hp(pw, salt):
    import hashlib
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000).hex()


def sign_up(name, email, pw):
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
    row = db("SELECT name,salt,pw FROM users WHERE email=?", (email.strip().lower(),))
    if row and hmac.compare_digest(row[0][2], hp(pw, bytes.fromhex(row[0][1]))):
        return row[0][0]
    return None


def auth_screen():
    st.markdown('<div class="hero"><h1>🛡️ RouteGuard</h1><p>Know the route. Know the uncertainty.</p></div>',
                unsafe_allow_html=True)
    if st.session_state.get("fails", 0) >= 5:
        st.error("Too many failed attempts. Refresh the page and try again later.")
        st.stop()
    t1, t2 = st.tabs(["Sign in", "Create account"])
    with t1, st.form("in"):
        em, pw = st.text_input("Email"), st.text_input("Password", type="password")
        if st.form_submit_button("Sign in", use_container_width=True):
            name = sign_in(em, pw)
            if name:
                st.session_state.update(user=em.strip().lower(), name=name, fails=0)
                st.rerun()
            st.session_state.fails = st.session_state.get("fails", 0) + 1
            st.error("Incorrect email or password.")
    with t2, st.form("up"):
        nm, em2 = st.text_input("Full name"), st.text_input("Email ")
        p1, p2 = st.text_input("Password ", type="password"), st.text_input("Confirm password", type="password")
        if st.form_submit_button("Create account", use_container_width=True):
            err = "Passwords do not match." if p1 != p2 else sign_up(nm, em2, p1)
            st.error(err) if err else st.success("Account created. Open the Sign in tab.")
    st.stop()


# ------------------------------------------------------------ data science
@st.cache_data
def load():
    init_db()
    return [pd.DataFrame(db(f"SELECT * FROM {t}"), columns=c) for t, c in [
        ("stops", ["name", "lat", "lon"]),
        ("routes", ["id", "name", "origin", "mode", "fare", "base_min", "sd", "live_age", "live_eta"]),
        ("trips", ["route_id", "hour", "weekday", "travel_min"])]]


@st.cache_resource
def train(trips):
    return RandomForestRegressor(n_estimators=120, random_state=1).fit(
        trips[["route_id", "hour", "weekday"]].values, trips.travel_min)


def hav(a, b, c, d):
    p1, p2, dl = math.radians(a), math.radians(c), math.radians(d - b)
    x = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 12742 * math.asin(math.sqrt(x))


def rank(stops, routes, trips, model, home, budget, deadline, hour, wd, pri, max_walk):
    hl = stops.loc[stops.name == home].iloc[0]
    rows = []
    for _, r in routes.iterrows():
        o = stops.loc[stops.name == r.origin].iloc[0]
        walk = hav(hl.lat, hl.lon, o.lat, o.lon)
        if walk > max_walk:
            continue
        t = trips[trips.route_id == r.id].travel_min
        ont, n = float((t <= t.median() * 1.15).mean()), len(t)
        pr = np.array([e.predict([[r.id, hour, wd]])[0] for e in model.estimators_])
        live = pd.notna(r.live_age) and r.live_age <= 10 and pd.notna(r.live_eta)
        tm = r.live_eta if live else pr.mean()
        total = tm + walk / 5 * 60
        fresh = 1.0 if live else (0.3 if pd.isna(r.live_age) else max(0, 1 - r.live_age / 60))
        rows.append(dict(route=r["name"], origin=r.origin, fare=r.fare, time=total, ts=V if live else E,
                         walk=walk, ont=ont, buf=deadline - total,
                         rel=0.6 * ont + 0.4 * (1 - min(t.std() / 15, 1)),
                         conf=0.4 * fresh + 0.3 * min(n / 200, 1) + 0.3 * (1 - min(pr.std() / 10, 1))))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    tm = df.time
    c = pd.DataFrame({"cost": np.where(df.fare.isna(), np.nan, np.clip(1 - df.fare / budget, 0, 1)),
                      "time": 1 - (tm - tm.min()) / (tm.max() - tm.min() + 1e-9), "rel": df.rel,
                      "buf": np.clip(df.buf / 30, 0, 1), "walk": np.clip(1 - df.walk / max_walk, 0, 1)})
    w = pd.Series(WEIGHTS[pri])
    df["score"] = [float((c.loc[i][c.loc[i].notna()] * w[c.loc[i].notna()]).sum() / w[c.loc[i].notna()].sum() * 100)
                   for i in df.index]
    return df.sort_values("score", ascending=False).reset_index(drop=True)


def explain(b, budget):
    s = f"**{b.route}** is your best match ({b.score:.0f}/100). "
    s += ("Fare is **unavailable**, so it was not guessed and cost was left out of the score. " if pd.isna(b.fare)
          else f"Fare ₹{b.fare:.0f} {'fits' if b.fare <= budget else 'is above'} your ₹{budget} budget. ")
    s += (f"You should arrive ~{b.buf:.0f} min early. " if b.buf >= 0 else f"⚠️ You may be ~{-b.buf:.0f} min late. ")
    return s + f"On time {b.ont * 100:.0f}% of past trips; travel time is {LBL[b.ts].lower()}."


# ------------------------------------------------------------ UI
st.set_page_config(page_title="RouteGuard", page_icon="🛡️", layout="centered")
st.markdown("""<style>
.block-container{max-width:760px;padding-top:1.2rem}
.hero{background:linear-gradient(135deg,#1d4ed8,#7c3aed);color:#fff;padding:18px 20px;border-radius:18px;margin-bottom:14px}
.hero h1{margin:0;font-size:1.7rem;color:#fff}.hero p{margin:2px 0 0;opacity:.9}
.card{border:1px solid rgba(128,128,128,.28);border-radius:16px;padding:12px 14px;margin:9px 0}
.card.top{border:2px solid #7c3aed}.row{display:flex;justify-content:space-between;align-items:center;gap:8px}
.score{font-size:1.5rem;font-weight:700;color:#7c3aed}.mu{opacity:.7;font-size:.85rem}
.pill{padding:2px 10px;border-radius:99px;font-size:.75rem;font-weight:600}
.VERIFIED{background:#dcfce7;color:#166534}.ESTIMATED{background:#fef3c7;color:#92400e}.UNAVAILABLE{background:#fee2e2;color:#991b1b}
.stButton>button,.stFormSubmitButton>button{border-radius:12px;font-weight:600}
</style>""", unsafe_allow_html=True)

stops, routes, trips = load()
if "user" not in st.session_state:
    auth_screen()
model = train(trips)

st.markdown(f'<div class="hero"><h1>🛡️ RouteGuard</h1><p>Hi {st.session_state.name}, plan a trusted commute. '
            f'<i>(sample data demo)</i></p></div>', unsafe_allow_html=True)
with st.sidebar:
    st.header("Trip settings")
    home = st.selectbox("Starting locality", [s for s in stops.name if "Velammal" not in s], index=4)
    pri = st.radio("Priority", list(WEIGHTS), horizontal=True)
    budget = st.slider("Daily budget (₹)", 20, 50, 30, 5)
    deadline = st.slider("Minutes until deadline", 20, 120, 60, 5)
    hour = st.slider("Departure hour", 6, 20, 8)
    wd = st.selectbox("Day", range(6), format_func=lambda i: "Mon Tue Wed Thu Fri Sat".split()[i])
    mw = st.slider("Max walk to a stop (km)", 0.5, 5.0, 3.0, 0.5)
    if st.button("Sign out", use_container_width=True):
        st.session_state.clear()
        st.rerun()

tab1, tab2, tab3 = st.tabs(["🧭 Plan trip", "📊 Insights", "💾 My trips"])
with tab1:
    df = rank(stops, routes, trips, model, home, budget, deadline, hour, wd, pri, mw)
    if df.empty:
        st.warning("No routes in walking range. Increase the walking limit.")
    else:
        b = df.iloc[0]
        st.markdown(f'<div class="card top"><div class="mu">Recommended</div></div>', unsafe_allow_html=True)
        st.info(explain(b, budget))
        if st.button("💾 Save this trip", use_container_width=True):
            db("INSERT INTO saved(email,start,route,score,fare,minutes) VALUES(?,?,?,?,?,?)",
               (st.session_state.user, home, b.route, round(b.score), None if pd.isna(b.fare) else b.fare,
                round(b.time)))
            st.toast("Trip saved")
        for i, x in df.iterrows():
            fs = U if pd.isna(x.fare) else V
            st.markdown(f"""<div class="card{' top' if i == 0 else ''}"><div class="row"><b>{x.route}</b>
            <span class="score">{x.score:.0f}</span></div>
            <div class="mu">From {x.origin} · walk {x.walk:.1f} km · confidence {x.conf * 100:.0f}%</div>
            <div class="row"><span>Time {x.time:.0f} min</span><span class="pill {x.ts}">{LBL[x.ts]}</span></div>
            <div class="row"><span>Fare {'—' if pd.isna(x.fare) else '₹%d' % x.fare}</span>
            <span class="pill {fs}">{LBL[fs]}</span></div></div>""", unsafe_allow_html=True)
        st.subheader("What-if: change the budget")
        wi = [rank(stops, routes, trips, model, home, k, deadline, hour, wd, pri, mw).iloc[0] for k in (20, 30, 40, 50)]
        st.dataframe(pd.DataFrame({"Budget": ["₹20", "₹30", "₹40", "₹50"], "Best route": [r.route for r in wi],
                                   "Score": [round(r.score) for r in wi]}), hide_index=True, use_container_width=True)
with tab2:
    t = trips.merge(routes[["id", "name"]], left_on="route_id", right_on="id")
    st.plotly_chart(px.histogram(t, x="travel_min", color="name", barmode="overlay", opacity=.65,
                                 title="Travel-time distribution"), use_container_width=True)
    st.plotly_chart(px.line(t.groupby(["name", "hour"]).travel_min.mean().reset_index(), x="hour", y="travel_min",
                            color="name", title="Average travel time by hour (peak-hour pattern)"),
                    use_container_width=True)
with tab3:
    mine = pd.DataFrame(db("SELECT at,start,route,score,fare,minutes FROM saved WHERE email=? ORDER BY id DESC",
                           (st.session_state.user,)), columns=["Saved at", "Start", "Route", "Score", "Fare", "Minutes"])
    st.dataframe(mine, hide_index=True, use_container_width=True) if len(mine) else st.caption("No saved trips yet.")
  
