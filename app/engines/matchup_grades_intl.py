"""
KBO / NPB / WNBA matchup grades — same "Matchup Grades" honesty-contract
pattern as engines/matchup_grades.py (the MLB engine), adapted per
league to the real signals each pipeline actually ships today.

HONESTY CONTRACT (read this before trusting a grade):
Same standard as the MLB engine: transparent checklists of real, named
signals, each computed only from numbers this app's own pipelines
already fetch (KBO's + NPB's official leaderboards and team stats,
WNBA's real box-score-derived team stats). These are NOT calibrated
win probabilities and NOT predictions. Every signal that fired is
listed next to the grade so the reader can weigh the evidence
themselves. No qualifying data -> no grade, stated plainly in the UI,
never silently skipped.

Each league gets its own signal set because each pipeline captures
different real numbers, and this module never fabricates a stat a
pipeline doesn't provide:
  - NPB:  starter vs. starter (WHIP/ERA/K9/HR9 — WHIP and the per-9
          rates computed from the official leaderboard's real IP/BB/H/
          HR/K) when the schedule's announced starters are both matched
          to a real stat line. Falls back to team form (below) when
          they aren't.
  - KBO:  team form only. The pipeline does not currently capture
          probable starters (they ship as "TBD"), so no starter-level
          grade is possible for KBO — that's stated in the UI rather
          than silently producing a thinner card.
  - WNBA: team form only. There's no starting-pitcher analog in
          basketball, so the whole grade is built from each team's
          real scoring, shooting, and turnover rates.

All thresholds below are this app's own fixed heuristic anchors — the
same status as the MLB engine's thresholds (real signals, reasonable
round-number cutoffs, NOT backtested or league-verified). Treat every
grade as a transparent checklist, not a probability.
"""

_GRADES = {4: "A", 3: "B", 2: "C", 1: "C-"}


def _grade(net):
    return _GRADES.get(min(net, 4), "A" if net > 4 else None)


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _winpct(record):
    """'12-5' -> 0.706. Ties (KBO/NPB) are just dropped from the
    denominator rather than guessed at how they should count."""
    if not record or not isinstance(record, str):
        return None
    parts = record.split("-")
    if len(parts) < 2:
        return None
    try:
        w, l = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    if w + l <= 0:
        return None
    return w / (w + l)


def _npb_innings(ip_raw):
    """NPB (and MLB-style) box scores print thirds-of-an-inning as a
    decimal digit, not a real decimal: '63.2' means 63 and 2/3 innings,
    not 63.2. Converts to a real float; returns None on anything that
    doesn't parse rather than guessing."""
    if ip_raw is None:
        return None
    s = str(ip_raw).strip()
    if not s:
        return None
    if "." in s:
        whole, _, frac = s.partition(".")
        try:
            whole_v = float(whole) if whole not in ("", "-") else 0.0
            frac_digit = int(frac[0]) if frac else 0
        except ValueError:
            return None
        if frac_digit not in (0, 1, 2):
            return _f(s)  # not thirds-style, treat as plain decimal
        return whole_v + frac_digit / 3.0
    return _f(s)


def _score_checks(a, h, checks, away_name, home_name):
    """Shared scoring loop: same net-signal grading as the MLB engine,
    generalized over an arbitrary (label, key, threshold, better) list
    against two flat dicts of already-computed values."""
    signals, a_pts, h_pts = [], 0, 0
    for label, key, thresh, better in checks:
        av, hv = a.get(key), h.get(key)
        if av is None or hv is None:
            continue
        gap = abs(av - hv)
        if gap < thresh:
            continue
        a_better = av < hv if better == "lower" else av > hv
        who = away_name if a_better else home_name
        if a_better:
            a_pts += 1
        else:
            h_pts += 1
        signals.append(f"{label}: edge {who} ({av:.3g} vs {hv:.3g})")

    net = abs(a_pts - h_pts)
    if net > 0:
        lean = away_name if a_pts > h_pts else home_name
        return {"lean": lean, "grade": _grade(net), "signals": signals,
                "score": f"{max(a_pts, h_pts)}-{min(a_pts, h_pts)} signals"}
    if signals:
        return {"lean": None, "grade": None, "signals": signals,
                "score": "signals split evenly — no lean"}
    return None


# =====================================================================
# KBO — team form only (no probable-starter data in this pipeline yet)
# =====================================================================

def grade_kbo_matchup(g):
    """Returns {"ml": {...}|None, "ou": {...}|None, "error": str|None}
    from the team-level fields KBO.py already loads onto each game."""
    def side(s):
        tb = g.get(f"{s}_team_batting") or {}
        tp = g.get(f"{s}_team_pitching") or {}
        rs, ra = _f(g.get(f"{s}_rs_pg")), _f(g.get(f"{s}_ra_pg"))
        return {
            "OPS": _f(tb.get("ops")),
            "ERA": _f(tp.get("era")),
            "WHIP": _f(tp.get("whip")),
            "RUN_DIFF": (rs - ra) if rs is not None and ra is not None else None,
            "GAME_TOTAL": (rs + ra) if rs is not None and ra is not None else None,
            "L10_PCT": _winpct(g.get(f"{s}_last10")),
        }

    away_name, home_name = g.get("away", "Away"), g.get("home", "Home")
    a, h = side("away"), side("home")

    if all(a.get(k) is None for k in ("OPS", "ERA", "RUN_DIFF", "L10_PCT")) and \
       all(h.get(k) is None for k in ("OPS", "ERA", "RUN_DIFF", "L10_PCT")):
        return {"ml": None, "ou": None,
                "error": "No team form posted yet for either side — no grade without real data."}

    ml = _score_checks(a, h, [
        ("Team OPS", "OPS", 0.030, "higher"),
        ("Team ERA", "ERA", 0.50, "lower"),
        ("Run differential/G", "RUN_DIFF", 0.75, "higher"),
        ("Last-10 win%", "L10_PCT", 0.20, "higher"),
    ], away_name, home_name)

    over, under, ou_signals = 0, 0, []
    game_totals = [v for v in (a.get("GAME_TOTAL"), h.get("GAME_TOTAL")) if v is not None]
    if game_totals:
        avg_total = sum(game_totals) / len(game_totals)
        if avg_total >= 9.5:
            over += 1
            ou_signals.append(f"Avg game total (both teams' real R/G) {avg_total:.2g} (high)")
        elif avg_total <= 8.0:
            under += 1
            ou_signals.append(f"Avg game total (both teams' real R/G) {avg_total:.2g} (low)")
    for label, key, ov_t, un_t in [
        ("Teams' avg WHIP", "WHIP", 1.35, 1.20),
        ("Teams' avg ERA", "ERA", 4.60, 3.60),
        ("Teams' avg OPS", "OPS", 0.760, 0.680),
    ]:
        vals = [v for v in (a.get(key), h.get(key)) if v is not None]
        if len(vals) < 2:
            continue
        v = sum(vals) / 2
        if v >= ov_t:
            over += 1
            ou_signals.append(f"{label} {v:.3g} (high)")
        elif v <= un_t:
            under += 1
            ou_signals.append(f"{label} {v:.3g} (low)")

    ou = None
    net = abs(over - under)
    if net > 0:
        ou = {"lean": "Over" if over > under else "Under",
              "grade": _grade(net), "signals": ou_signals,
              "score": f"{max(over, under)}-{min(over, under)} signals"}
    elif ou_signals:
        ou = {"lean": None, "grade": None, "signals": ou_signals,
              "score": "signals split evenly — no lean"}

    return {"ml": ml, "ou": ou, "error": None}


# =====================================================================
# NPB — starter vs. starter when both are matched to a real stat line,
# team form otherwise
# =====================================================================

def grade_npb_matchup(g):
    away_name, home_name = g.get("away", "Away"), g.get("home", "Home")
    a_sp, h_sp = g.get("away_starter_stats"), g.get("home_starter_stats")

    if a_sp and h_sp:
        def sp_vals(sp):
            ip = _npb_innings(sp.get("innings_pitched"))
            bb, hits = _f(sp.get("walks")), _f(sp.get("hits_allowed"))
            hr, k = _f(sp.get("home_runs_allowed")), _f(sp.get("strikeouts"))
            out = {"ERA": _f(sp.get("era"))}
            if ip:
                if bb is not None and hits is not None:
                    out["WHIP"] = (bb + hits) / ip
                if hr is not None:
                    out["HR9"] = hr * 9 / ip
                if k is not None:
                    out["K9"] = k * 9 / ip
            return out

        a, h = sp_vals(a_sp), sp_vals(h_sp)
        ml = _score_checks(a, h, [
            ("WHIP", "WHIP", 0.15, "lower"),
            ("ERA", "ERA", 0.75, "lower"),
            ("K/9", "K9", 1.5, "higher"),
            ("HR/9", "HR9", 0.40, "lower"),
        ], away_name, home_name)

        over, under, ou_signals = 0, 0, []
        for label, key, ov_t, un_t in [
            ("Starters' avg WHIP", "WHIP", 1.30, 1.15),
            ("Starters' avg ERA", "ERA", 4.20, 3.30),
            ("Starters' avg HR/9", "HR9", 1.10, 0.80),
        ]:
            vals = [v for v in (a.get(key), h.get(key)) if v is not None]
            if len(vals) < 2:
                continue
            v = sum(vals) / 2
            if v >= ov_t:
                over += 1
                ou_signals.append(f"{label} {v:.3g} (high)")
            elif v <= un_t:
                under += 1
                ou_signals.append(f"{label} {v:.3g} (low)")

        ou = None
        net = abs(over - under)
        if net > 0:
            ou = {"lean": "Over" if over > under else "Under",
                  "grade": _grade(net), "signals": ou_signals,
                  "score": f"{max(over, under)}-{min(over, under)} signals"}
        elif ou_signals:
            ou = {"lean": None, "grade": None, "signals": ou_signals,
                  "score": "signals split evenly — no lean"}

        return {"ml": ml, "ou": ou, "error": None}

    # Fallback: one or both starters not yet matched to a real stat
    # line — grade off team form instead of leaving the card empty.
    def side(s):
        rs, ra = _f(g.get(f"{s}_rs_pg")), _f(g.get(f"{s}_ra_pg"))
        return {
            "RUN_DIFF": (rs - ra) if rs is not None and ra is not None else None,
            "GAME_TOTAL": (rs + ra) if rs is not None and ra is not None else None,
            "L10_PCT": _winpct(g.get(f"{s}_last10")),
        }

    a, h = side("away"), side("home")
    if a.get("RUN_DIFF") is None and h.get("RUN_DIFF") is None and \
       a.get("L10_PCT") is None and h.get("L10_PCT") is None:
        return {"ml": None, "ou": None,
                "error": "Starters not matched to a real stat line yet, and no team form posted — no grade."}

    ml = _score_checks(a, h, [
        ("Run differential/G", "RUN_DIFF", 0.75, "higher"),
        ("Last-10 win%", "L10_PCT", 0.20, "higher"),
    ], away_name, home_name)

    ou = None
    game_totals = [v for v in (a.get("GAME_TOTAL"), h.get("GAME_TOTAL")) if v is not None]
    if game_totals:
        avg_total = sum(game_totals) / len(game_totals)
        if avg_total >= 9.0:
            ou = {"lean": "Over", "grade": "C", "signals":
                  [f"Avg game total (both teams' real R/G) {avg_total:.2g} (high)"],
                  "score": "1-0 signals"}
        elif avg_total <= 7.5:
            ou = {"lean": "Under", "grade": "C", "signals":
                  [f"Avg game total (both teams' real R/G) {avg_total:.2g} (low)"],
                  "score": "1-0 signals"}

    return {"ml": ml, "ou": ou, "error": None,
            "note": "Starters not yet matched to a real stat line — graded on team form instead."}


# =====================================================================
# WNBA — team form (no starting-pitcher analog in basketball)
# =====================================================================

def grade_wnba_matchup(g):
    def side(s):
        pf, pa = _f(g.get(f"{s}_pf_pg")), _f(g.get(f"{s}_pa_pg"))
        return {
            "PPG_DIFF": (pf - pa) if pf is not None and pa is not None else None,
            "FG_PCT": _f(g.get(f"{s}_fg_pct")),
            "TO_PG": _f(g.get(f"{s}_to_g")),
            "WIN_PCT": _winpct(g.get(f"{s}_record")),
            "PF_PG": pf, "PA_PG": pa,
            "AVG_TOTAL": _f(g.get(f"{s}_avg_total")),
        }

    away_name, home_name = g.get("away", "Away"), g.get("home", "Home")
    a, h = side("away"), side("home")

    if all(a.get(k) is None for k in ("PPG_DIFF", "FG_PCT", "TO_PG", "WIN_PCT")) and \
       all(h.get(k) is None for k in ("PPG_DIFF", "FG_PCT", "TO_PG", "WIN_PCT")):
        return {"ml": None, "ou": None,
                "error": "No team form posted yet for either side — no grade without real data."}

    ml = _score_checks(a, h, [
        ("Point differential/G", "PPG_DIFF", 4.0, "higher"),
        ("FG%", "FG_PCT", 3.0, "higher"),
        ("Turnovers/G", "TO_PG", 2.0, "lower"),
        ("Win%", "WIN_PCT", 0.150, "higher"),
    ], away_name, home_name)

    over, under, ou_signals = 0, 0, []

    # Prefer each team's own real avg game total if the pipeline has
    # it; otherwise build the same number from PF/G + PA/G.
    totals = []
    for side_d in (a, h):
        if side_d.get("AVG_TOTAL") is not None:
            totals.append(side_d["AVG_TOTAL"])
        elif side_d.get("PF_PG") is not None and side_d.get("PA_PG") is not None:
            totals.append(side_d["PF_PG"] + side_d["PA_PG"])
    if totals:
        avg_total = sum(totals) / len(totals)
        if avg_total >= 168:
            over += 1
            ou_signals.append(f"Avg game total {avg_total:.3g} (high)")
        elif avg_total <= 158:
            under += 1
            ou_signals.append(f"Avg game total {avg_total:.3g} (low)")

    fg_vals = [v for v in (a.get("FG_PCT"), h.get("FG_PCT")) if v is not None]
    if len(fg_vals) == 2:
        v = sum(fg_vals) / 2
        if v >= 45.0:
            over += 1
            ou_signals.append(f"Teams' avg FG% {v:.3g} (high)")
        elif v <= 41.0:
            under += 1
            ou_signals.append(f"Teams' avg FG% {v:.3g} (low)")

    to_vals = [v for v in (a.get("TO_PG"), h.get("TO_PG")) if v is not None]
    if len(to_vals) == 2:
        v = sum(to_vals) / 2
        if v <= 13.0:
            over += 1
            ou_signals.append(f"Teams' avg TO/G {v:.3g} (low — more possessions)")
        elif v >= 16.0:
            under += 1
            ou_signals.append(f"Teams' avg TO/G {v:.3g} (high — fewer possessions)")

    ou = None
    net = abs(over - under)
    if net > 0:
        ou = {"lean": "Over" if over > under else "Under",
              "grade": _grade(net), "signals": ou_signals,
              "score": f"{max(over, under)}-{min(over, under)} signals"}
    elif ou_signals:
        ou = {"lean": None, "grade": None, "signals": ou_signals,
              "score": "signals split evenly — no lean"}

    return {"ml": ml, "ou": ou, "error": None}


# =====================================================================
# Shared card renderer — same visual as the MLB Game Card's Matchup
# Grades panel, reused so KBO/NPB/WNBA don't each hand-roll their own.
# =====================================================================

def render_matchup_grades_card(grades, subtitle, source_line):
    import streamlit as st
    from styles.kc_theme import card, COLOR

    with card("matchup_grades_card"):
        st.markdown(
            f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Matchup Grades</div>'
            f'<div class="pf-card-subtitle">{subtitle}</div>',
            unsafe_allow_html=True,
        )
        if grades.get("error"):
            st.caption(grades["error"])
            return
        if grades.get("note"):
            st.caption(grades["note"])

        gcol1, gcol2 = st.columns(2)
        for gcol, key, title in ((gcol1, "ml", "Moneyline"), (gcol2, "ou", "Over / Under")):
            with gcol:
                res = grades.get(key)
                st.markdown(
                    f'<div style="font-weight:700; color:{COLOR["magenta_purple"]}; '
                    f'font-size:13px;">{title}</div>',
                    unsafe_allow_html=True,
                )
                if not res:
                    st.caption("No qualifying signals — no lean either way.")
                    continue
                if res.get("lean"):
                    st.markdown(
                        f'<div style="font-size:16px; font-weight:800; color:{COLOR["stat_high"]};">'
                        f'Lean: {res["lean"]} \u00b7 Grade {res["grade"]}</div>'
                        f'<div style="font-size:11px; color:{COLOR["gold"]};">{res["score"]}</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div style="font-size:13px; color:{COLOR["gold"]};">{res["score"]}</div>',
                        unsafe_allow_html=True,
                    )
                for s in res.get("signals", []):
                    st.markdown(
                        f'<div style="font-size:11.5px; color:{COLOR["text"]};">\u2713 {s}</div>',
                        unsafe_allow_html=True,
                    )
        st.caption(source_line)
