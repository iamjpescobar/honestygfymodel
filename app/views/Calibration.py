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
from auth import require_admin, render_account_sidebar
from engines.calibration import summary, grade_pending, reopen_recent_days, BOARDS, _load, _LOG_PATH

inject_kc_theme()
render_account_sidebar()
require_admin()

st.markdown(
    f'<div style="display:flex; align-items:center; gap:8px; margin-bottom:2px;">'
    f'<span style="font-size:20px; font-weight:800; letter-spacing:-0.02em; '
    f'color:{COLOR["text"]};">CALIBRATION</span>'
    f'<span style="font-size:11px; font-weight:700; padding:2px 8px; border-radius:4px; '
    f'background:{COLOR["error"]}22; color:{COLOR["error"]};">ADMIN</span></div>',
    unsafe_allow_html=True,
)

# Baselines a board has to BEAT to be adding value. Without these a
# hit rate is just a number — 33% looks fine until you know a coin
# flip on the same target is also 33%.
BASELINES = {
    "daily13": ("~65%", "a good contact hitter gets a hit in about 2 of every 3 games"),
    "hr_edge": ("~12%", "a given hitter homers in roughly 1 game in 8"),
    "potd": ("~33%", "a hitter records an extra-base hit in roughly 1 game in 3"),
    "wnba_props": ("~50%", "a line set at a player's own average is cleared about half the time"),
    "wnba_defense": ("~50%", "same — these are graded against each player's own recent form"),
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
        base, _why = BASELINES.get(board, ("\u2014", ""))
        rows.append({
            "Board": cfg.get("label", board),
            "Graded on": cfg.get("question", "\u2014"),
            "Record": f'{s.get("hits", 0)}/{s.get("total", 0)}' if s.get("total") else "\u2014",
            "Rate": f'{s["rate"]:.1f}%' if s.get("rate") is not None else "\u2014",
            "Baseline": base,
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
        base, why = BASELINES.get(board, ("\u2014", ""))
        if why:
            st.caption(f"Baseline {base}: {why}.")
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
