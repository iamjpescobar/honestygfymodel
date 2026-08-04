"""
Calibration — the scorecard for this app's own picks. ADMIN ONLY.

Picks are written down BEFORE the games and graded against official
box scores after they're final. That ordering is the whole point: any
list of good hitters looks sharp on the nights it lands, and the only
way to know whether a model adds value is to record it in advance and
count.

This page is restricted to the admin profile because it is diagnostic,
not a product feature — it shows raw records, sample sizes, and the
storage path, including the honest answer when a board has no history
yet.

Each board is graded on the outcome it is actually trying to produce:
  Daily 13           -> at least one hit
  HR Edge (top 5)    -> at least one home run
  Player of the Day  -> at least one extra-base hit
  WNBA boards        -> cleared the line the board implied
"""
import json

import pandas as pd
import streamlit as st

from styles.kc_theme import inject_kc_theme, card, footer, COLOR
from auth import require_admin
from engines.calibration_trend import render_calibration_trend
from engines.calibration import (summary, grade_pending, reopen_recent_days,
                                 set_odds, BOARDS, _load, _LOG_PATH)

# Theme injection lives in app.py, which renders once per script run
# before this view is exec'd. It used to be called here as well, so the
# same ~26KB of inline CSS was serialised, shipped and parsed TWICE on
# every rerun of every page. Same cascade either way (the two layers
# overlap only on properties resolved by specificity), so the second
# copy bought nothing.
require_admin()

st.markdown(
    f'<div style="display:flex; align-items:center; gap:8px; margin-bottom:var(--lc-space-hair);">'
    f'<span style="font-size:var(--lc-text-title); font-weight:800; letter-spacing:-0.02em; '
    f'color:{COLOR["text"]};">CALIBRATION</span>'
    f'<span style="font-size:var(--lc-text-caption); font-weight:700; padding:var(--lc-space-hair) var(--lc-space-md); border-radius:var(--lc-radius-sm); '
    f'background:{COLOR["error"]}22; color:{COLOR["error"]};">ADMIN</span></div>',
    unsafe_allow_html=True,
)

# Baselines a board has to BEAT to be adding value. Without these a
# hit rate is just a number — 33% looks fine until you know a coin
# flip on the same target is also 33%.
# Fallback prose only — the REAL baselines are measured, not asserted.
#
# These used to be hardcoded guesses, and two of them were badly wrong:
# "~12%" for a home run and "~33%" for an extra-base hit are both roughly
# double the true rates. HR Edge was therefore being judged against an
# inflated bar, which made a working board look broken (and would have
# made a broken one look catastrophic).
#
# precompute.build_baselines now measures each rate from the same
# league-wide Statcast data the picks come from, and summary() attaches
# it as "baseline". This dict is used only for the plain-English
# explanation, and as a last resort before the first nightly ships the
# measured file.
BASELINE_NOTES = {
    "daily13": "share of league starters with a hit, measured nightly",
    "hr_edge": "share of league starters with a home run, measured nightly",
    "potd": "share of league starters with an extra-base hit, measured nightly",
    "wnba_props": "a line set at a player's own average is cleared about half the time",
    "wnba_defense": "same — these are graded against each player's own recent form",
}

if st.button("\u27f3 Grade pending picks now", key="cal_grade"):
    with st.spinner("Grading any completed slates\u2026"):
        n = grade_pending()
    st.success(f"Graded {n} pick(s).")
    st.rerun()

with st.expander("Recover ungraded days"):
    st.caption(
        "If recent days show as graded but stuck on DNP (an older bug froze "
        "days before box scores posted), this reopens the last few days and "
        "re-checks them against the official box scores, which have since "
        "posted. Only stuck DNPs are cleared \u2014 real hits and misses are "
        "left as they are."
    )
    _rd = st.slider("Days back to reopen", 1, 10, 5, key="cal_reopen_days")
    if st.button("Reopen & re-grade", key="cal_reopen"):
        with st.spinner("Reopening recent days and re-grading\u2026"):
            _r = reopen_recent_days(_rd)
            _g = grade_pending()
        st.success(f"Reopened {_r} pick(s); newly graded {_g}.")
        st.rerun()

data = _load()
sums = summary()

with card("cal_summary"):
    st.markdown(
        f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Tracked record by board</div>'
        f'<div class="pf-card-subtitle">Picks are logged before games and graded after. '
        f'"Did not play" is excluded from the rate rather than counted as a miss \u2014 a '
        f'scratched player is not a bad pick. Beat the baseline and the model is adding '
        f'value; sit at it and it is not.</div>',
        unsafe_allow_html=True,
    )
    rows = []
    for board, cfg in BOARDS.items():
        s = sums.get(board, {})
        # Measured baseline from summary(), not a hardcoded guess.
        _b = s.get("baseline")
        base = f"{_b:.1f}%" if _b is not None else "\u2014"
        rows.append({
            "Board": cfg.get("label", board),
            "Graded on": cfg.get("question", "\u2014"),
            "Record": f'{s.get("hits", 0)}/{s.get("total", 0)}' if s.get("total") else "\u2014",
            "Rate": f'{s["rate"]:.1f}%' if s.get("rate") is not None else "\u2014",
            "Baseline": base,
            # The gap IS the model's contribution. Rate alone says
            # nothing: matching the baseline means the board added zero.
            "Edge": (f'{s["edge"]:+.1f}' if s.get("edge") is not None else "\u2014"),
            "Verdict": s.get("verdict", "\u2014"),
            # Profit answers a DIFFERENT question than hit rate, and it's
            # the one that decides whether a board was worth betting.
            # 65% loses money all season at -200 and prints at -150.
            "Units": (f'{s["profit"]["units"]:+.2f}'
                      if s.get("profit", {}).get("priced") else "\u2014"),
            "ROI": (f'{s["profit"]["roi"]:+.1f}%'
                    if s.get("profit", {}).get("priced") else "\u2014"),
            "Break-even": (f'{s["profit"]["breakeven"]:.1f}%'
                           if s.get("profit", {}).get("priced") else "\u2014"),
            "Priced": s.get("profit", {}).get("priced", 0),
            "DNP": s.get("dnp", 0),
            "Days logged": len(data.get(board, {})),
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    _any = any(s.get("total") for s in sums.values())
    if not _any:
        st.info(
            "No graded results yet. Picks only appear here after their slate is final and "
            "the pipeline has graded them, so a brand-new record stays empty for a day. "
            "If it is still empty after a couple of nightly runs, the handoff is broken \u2014 "
            "check the storage path below."
        )
    else:
        st.caption(
            "Read these over weeks, not nights. Even a genuinely strong model loses most "
            "days on a home-run board and has losing streaks of four or five on any board."
        )

# Per-board detail
for board, cfg in BOARDS.items():
    days = data.get(board, {})
    if not days:
        continue
    with st.expander(f'{cfg.get("label", board)} \u2014 {len(days)} day(s) logged'):
        # Trend first: direction matters more than the cumulative total,
        # and a table of numbers can't show it.
        render_calibration_trend(days, sums.get(board, {}).get("baseline"),
                                 cfg.get("label", board))
        _s = sums.get(board, {})
        _b, _why = _s.get("baseline"), BASELINE_NOTES.get(board, "")
        if _b is not None:
            st.caption(
                f"Baseline {_b:.1f}% \u2014 {_why}. "
                f"Verdict: {_s.get('verdict', 'not enough graded picks yet')}."
            )
        elif _why:
            st.caption(
                f"Baseline not measured yet ({_why}) \u2014 it ships with the "
                f"next nightly build."
            )
        detail = []
        for day in sorted(days.keys(), reverse=True):
            picks = days[day].get("picks", [])
            hits = sum(1 for p in picks if p.get("result") == "hit")
            miss = sum(1 for p in picks if p.get("result") == "miss")
            dnp = sum(1 for p in picks if p.get("result") == "dnp")
            pending = sum(1 for p in picks if p.get("result") is None)
            detail.append({
                "Date": day,
                "Record": f"{hits}/{hits + miss}" if (hits + miss) else "\u2014",
                "Hits": hits, "Misses": miss, "DNP": dnp, "Pending": pending,
                "Names": ", ".join(p.get("name", "?") for p in picks[:6])
                         + ("\u2026" if len(picks) > 6 else ""),
            })
        st.dataframe(pd.DataFrame(detail), width="stretch", hide_index=True)

        # ---- price entry -------------------------------------------
        # Typed in, not fetched. Nothing here has a sportsbook feed, and
        # a scraped consensus would be the wrong number anyway: profit
        # depends on the price YOU took, not on a market average.
        st.caption(
            "Enter the American odds you actually got (e.g. -180 or +320). "
            "Picks left at 0 are EXCLUDED from the profit figures rather "
            "than assumed to be even money — an assumed price would invent "
            "a profit that never happened."
        )
        _day = st.selectbox(
            "Day to price", sorted(days.keys(), reverse=True),
            key=f"odds_day_{board}", label_visibility="collapsed",
        )
        # KEY AND MATCH ON THE MARKET AS WELL AS THE PLAYER.
        #
        # A day used to hold one market per board, so a player id was a
        # unique handle here. It no longer is: WNBA Props logs five
        # markets under one board, and the same player can appear on the
        # points list AND the rebounds list on the same night. That broke
        # two things at once — two number_inputs sharing a widget key
        # (Streamlit raises a duplicate-key error and the page dies), and
        # set_odds() writing one price onto both picks, inventing a
        # number for a market that was never priced.
        for _pk in (days.get(_day, {}).get("picks", []) or []):
            _stat = _pk.get("stat")
            _c1, _c2 = st.columns([3, 1])
            with _c1:
                _mkt = f' · {_stat}' if _stat else ""
                st.caption(f'{_pk.get("name", "?")}{_mkt} · '
                           f'{_pk.get("result") or "pending"}')
            with _c2:
                _cur = int(_pk["odds"]) if _pk.get("odds") else 0
                _new = st.number_input(
                    "odds", value=_cur, step=5, format="%d",
                    key=f'odds_{board}_{_day}_{_pk.get("id")}_{_stat}',
                    label_visibility="collapsed",
                )
                if _new != _cur:
                    set_odds(board, _day, _pk.get("id"), _new or None,
                             stat=_stat)

with card("cal_storage"):
    st.markdown(
        f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Storage</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"Record path: `{_LOG_PATH}` \u00b7 boards tracked: {len(BOARDS)} \u00b7 "
        f"total days on file: {sum(len(d) for d in data.values())}. "
        "The nightly pipeline restores the previous record, grades finished slates, and "
        "republishes it inside the data archive, so history survives redeploys."
    )
    with st.expander("Raw record (JSON)"):
        st.code(json.dumps(data, indent=2)[:20000] or "{}", language="json")

footer()
