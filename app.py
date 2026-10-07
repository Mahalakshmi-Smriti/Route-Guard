"""RouteGuard main page. Run: streamlit run app.py"""
import datetime as dt
import html
import math

import streamlit as st

st.set_page_config(page_title="RouteGuard", page_icon="🛡️", layout="centered")

from auth import db, init_db, auth_screen, log_out
from config import ROAD, WEIGHTS
from data import nearby, gtfs_options
from planning import (plan, transit, card, transit_card, gtfs_card, CSS, place_picker)


# ------------------------------------------------------------ pages
def planner_tab(pri, budget, ov):
    pa = place_picker("From", "from")
    pb = place_picker("To", "to")
    c1, c2 = st.columns(2)
    day = c1.date_input("Date", dt.date.today())
    tm = c2.time_input("Leave at", dt.datetime.now().time().replace(second=0, microsecond=0))
    deadline = st.number_input("Must arrive within (minutes)", 5, 240, 60)

    if st.button("Find routes", type="primary", use_container_width=True):
        if not (pa and pb):
            st.warning("Pick both places first.")
        else:
            a, b = pa[0], pb[0]
            depart = tm.hour * 3600 + tm.minute * 60
            with st.spinner("Finding routes..."):
                res = dict(trip=f"{pa[1].split(',')[0]} → {pb[1].split(',')[0]}",
                           road=plan(a, b, deadline, budget, pri, ov))
                try:
                    res["gtfs"], res["gtfs_note"] = gtfs_options(a, b, depart, day)
                    res["gtfs_err"] = None
                except Exception as e:
                    res["gtfs"], res["gtfs_note"], res["gtfs_err"] = [], "", str(e)
                res["tr"] = transit(a, b, nearby(*a), nearby(*b), ov)
            st.session_state.results = res  # kept so Save buttons still work after the rerun

    res = st.session_state.get("results")
    if not res:
        return

    st.markdown(f"#### {html.escape(res['trip'])}")

    st.subheader("Walk / Cycle / Road")
    if res["road"] is None:
        st.info("Routing service did not respond. Try again.")
    else:
        for i, x in enumerate(res["road"]):
            st.markdown(card(x, i == 0), unsafe_allow_html=True)
            if st.button("Save this route", key=f"save{i}"):
                db("INSERT INTO saved(email,trip,route,score,fare,minutes) VALUES(?,?,?,?,?,?)",
                   (st.session_state.user, res["trip"], x["route"], x["score"],
                    None if math.isnan(x["fare"]) else x["fare"], x["time"]))
                st.success("Saved. See the Saved trips tab.")

    st.subheader("Scheduled public transport (Chennai GTFS)")
    if res["gtfs_err"]:
        st.warning(f"Timetable unavailable: {res['gtfs_err']}")
    else:
        if res["gtfs_note"]:
            st.caption(res["gtfs_note"])
        if not res["gtfs"]:
            st.info("No scheduled bus/metro/train found between these two places.")
        for t in res["gtfs"]:
            st.markdown(gtfs_card(t, ov), unsafe_allow_html=True)

    st.subheader("Other transit on OpenStreetMap")
    if res["tr"] is None:
        st.info("OpenStreetMap did not respond. Try again.")
    elif not res["tr"]:
        st.info("No OpenStreetMap route found serving both ends.")
    for t in res["tr"] or []:
        st.markdown(transit_card(t), unsafe_allow_html=True)


def saved_tab():
    rows = db("SELECT id,trip,route,score,fare,minutes,at FROM saved WHERE email=? ORDER BY id DESC",
              (st.session_state.user,))
    if not rows:
        st.info("No saved trips yet. Save a route from the Plan trip tab.")
        return
    for rid, trip, route, score, fare, minutes, at in rows:
        fare_txt = "Unavailable" if fare is None else ("Free" if fare == 0 else f"₹{fare:.0f}")
        st.markdown(
            f'<div class="card"><div class="row"><b>{html.escape(trip)}</b>'
            f'<span class="score">{score:.0f}</span></div>'
            f'<div>{html.escape(route)} · {minutes:.0f} min · Fare: {fare_txt}</div>'
            f'<div class="mu">Saved {html.escape(str(at))} UTC</div></div>', unsafe_allow_html=True)
        if st.button("Delete", key=f"del{rid}"):
            db("DELETE FROM saved WHERE id=? AND email=?", (rid, st.session_state.user))
            st.rerun()


def main():
    init_db()
    st.markdown(CSS, unsafe_allow_html=True)
    if "user" not in st.session_state:
        auth_screen()  # shows sign in / create account, then stops

    st.markdown(f'<div class="hero"><h1>🛡️ RouteGuard</h1><p>Hi {html.escape(st.session_state.name)}</p></div>',
                unsafe_allow_html=True)

    with st.sidebar:
        st.header("Settings")
        st.caption(f"Signed in as {st.session_state.user}")
        pri = st.selectbox("Priority", list(WEIGHTS))
        budget = st.number_input("Budget (₹)", 10, 2000, 200)
        st.caption("Type a fare only if you know it. Leave 0 for unknown.")
        ov = {ROAD: st.number_input(f"{ROAD} fare (₹)", 0, 2000, 0),
              "Bus": st.number_input("Bus fare (₹)", 0, 500, 0),
              "Metro": st.number_input("Metro fare (₹)", 0, 500, 0),
              "Train": st.number_input("Train fare (₹)", 0, 500, 0)}
        if st.button("Sign out", use_container_width=True):
            log_out()

    t1, t2 = st.tabs(["Plan trip", "Saved trips"])
    with t1:
        planner_tab(pri, budget, ov)
    with t2:
        saved_tab()


main()
