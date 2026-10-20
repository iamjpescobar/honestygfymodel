"""The bet log's session side (10-20): load the signed-in user's log once
per session, write through engines/bet_log's store, and the one button
every page uses to log a bet. The Bet Log page reads the same state."""
import streamlit as st

from engines import bet_log as bl

KEY = "bet_log"


def state(force=False):
    """{"bets", "sha", "src": "github" | "session", "err"} for this session."""
    ss = st.session_state
    if force or KEY not in ss:
        store = bl.store_for(ss.get("username"))
        cur = ss.get(KEY) or {}
        s = {"bets": cur.get("bets") or [], "sha": None, "src": "session", "err": None}
        if store is not None:
            try:
                bets, sha = store.load()
                s = {"bets": bets, "sha": sha, "src": "github", "err": None}
            except Exception as exc:  # noqa: BLE001
                s["err"] = f"Couldn't read the saved log ({type(exc).__name__}); this session only."
        ss[KEY] = s
    return ss[KEY]


def write(bets, what):
    """Save the whole list; True when it reached the saved log."""
    s = state()
    store = bl.store_for(st.session_state.get("username"))
    if store is None or s["src"] != "github":
        s["bets"] = bets
        return False
    for _attempt in range(2):
        try:
            s["sha"] = store.save(bets, s["sha"], what)
            s["bets"], s["err"] = bets, None
            return True
        except Exception as exc:  # noqa: BLE001 — a stale sha: reload, merge, retry
            try:
                fresh, sha = store.load()
                ids = {b["id"] for b in bets}
                bets = bets + [b for b in fresh if b["id"] not in ids]
                s["sha"] = sha
            except Exception:  # noqa: BLE001
                pass
            s["err"] = f"Save failed ({type(exc).__name__}) — kept for this session."
    s["bets"] = bets
    return False


def add(bet):
    if bet is None:
        return False
    return write(bl.upsert(state()["bets"], bet), f"add {bet['sport']} {bet['kind']}")


def log_button(sport, kind, desc, chance, price, default_stake, tier, legs, key):
    """A stake box + 'Log this bet' button; logs at the price you typed."""
    c1, c2 = st.columns([1, 2])
    start = default_stake or st.session_state.get("blog_last_stake") or 10.0
    stake = c1.number_input("Stake $", min_value=0.0, value=float(round(start, 2)),
                            step=1.0, key=f"{key}_stake",
                            help="What you actually put on it. The site's suggested stake when "
                                 "a bankroll is set, else your last one.")
    if c2.button("Log this bet (I placed it)", key=f"{key}_log"):
        b = bl.new_bet(sport, kind, desc, chance, price, stake, tier, legs)
        if b is None:
            st.warning("Type the book's price first.")
        else:
            st.session_state["blog_last_stake"] = stake
            saved = add(b)
            st.success("Logged — grade it on the Bet Log page when it settles."
                       + ("" if saved else " (This session only: the saved log isn't set up.)"))
