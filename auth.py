"""RouteGuard: database, sign in, create account, sign out."""
import hashlib
import hmac
import os
import re
import sqlite3

import streamlit as st

from config import DB
from ui import chips, hero


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
    _, mid, _ = st.columns([1, 2.2, 1])
    with mid:
        _auth_body()
    st.stop()


def _auth_body():
    hero("Know the route. Know the uncertainty.")
    chips(["🚌 Bus · Metro · Train", "⏱️ Deadline-aware", "🔍 Honest data labels"])
    if st.session_state.get("fails", 0) >= 5:
        st.error("Too many failed attempts. Refresh the page and try again later.")
        st.stop()

    t1, t2 = st.tabs(["🔑  Sign in", "✨  Create account"])

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


