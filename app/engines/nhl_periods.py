"""
NHL periods (10-22) — what a box score can't say: each period's score,
shots and every skater's goals, assists and shots on goal BY PERIOD, from
ESPN's game summary (the play-by-play).

parse(summary, goalie_ids) -> {
  "lines":   {team_id: [p1, p2, p3, (ot...)]}   team goals per period
  "sog":     {team_id: [p1, p2, p3]}            team shots on goal (plays)
  "players": {pid: [[g, a, sog] x 3]}           regulation periods only
  "first_goal": {"pid", "team", "period"} | None
}
A shot on goal is a "Shot" play (saved) or a "Goal"; the shooter is the
play's first participant. A goal's assisters are the next participants
that are NOT a goalie (ESPN lists the goalie on scoring plays too).
Missing is never zero: a shape this parser can't read leaves the field
empty, and the backfill's [verify] lines count, game by game, whether
each skater's periods add up to his box score.

ESPN's NHL summary: header.competitions[0].competitors[].linescores[];
plays[] ({type: {text}, text, period: {number}, team: {id},
participants: [{athlete: {id}}], scoringPlay}).

Pure — no requests.
"""
PERIODS = 3


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def lines(summary):
    comp = (((summary or {}).get("header") or {}).get("competitions") or [{}])[0] or {}
    out = {}
    for c in comp.get("competitors") or []:
        tid = str((c.get("team") or {}).get("id") or c.get("id") or "")
        ls = [_num(x.get("displayValue") if isinstance(x, dict) else x)
              for x in c.get("linescores") or []]
        if tid and ls and None not in ls:
            out[tid] = ls
    return out


def _pids(play):
    out = []
    for p in play.get("participants") or []:
        a = (p or {}).get("athlete") or {}
        if a.get("id") is not None:
            out.append(str(a["id"]))
    return out


def _period(play):
    p = play.get("period")
    return (p or {}).get("number") if isinstance(p, dict) else p


def _kind(play):
    t = (((play.get("type") or {}).get("text")) or "").strip().lower()
    if t == "goal" or (play.get("scoringPlay") and "shootout" not in t):
        return "goal"
    if t in ("shot", "shot on goal"):
        return "shot"
    return None


def parse(summary, goalie_ids=()):
    gk = {str(x) for x in goalie_ids or ()}
    plays = [p for p in (summary or {}).get("plays") or [] if isinstance(p, dict)]
    out = {"lines": lines(summary), "sog": {}, "players": {}, "first_goal": None}

    def slot(pid):
        return out["players"].setdefault(pid, [[0, 0, 0] for _ in range(PERIODS)])
    for pl in plays:
        k = _kind(pl)
        per = _period(pl)
        if k is None or not isinstance(per, int) or per < 1:
            continue
        team = str((pl.get("team") or {}).get("id") or "")
        ids = [x for x in _pids(pl) if x not in gk]
        if per <= PERIODS and team:
            s = out["sog"].setdefault(team, [0] * PERIODS)
            s[per - 1] += 1
        if not ids:
            continue
        if k == "goal" and out["first_goal"] is None and per <= PERIODS + 1:
            out["first_goal"] = {"pid": ids[0], "team": team or None, "period": per}
        if per > PERIODS:
            continue
        slot(ids[0])[per - 1][2] += 1                 # every goal is a shot on goal
        if k == "goal":
            slot(ids[0])[per - 1][0] += 1
            for a in ids[1:3]:
                slot(a)[per - 1][1] += 1
    return out


def check(rec, box):
    """{"players", "goals_ok", "assists_ok", "sog_ok"}: how many skaters'
    regulation periods add up to the box score's g / a / sog (box: {pid:
    {"g", "a", "sog"}}). OT goals make a few honest misses."""
    n = ok_g = ok_a = ok_s = 0
    for pid, b in (box or {}).items():
        per = (rec.get("players") or {}).get(pid) or [[0, 0, 0]] * PERIODS
        n += 1
        ok_g += int(sum(x[0] for x in per) == int(b.get("g") or 0))
        ok_a += int(sum(x[1] for x in per) == int(b.get("a") or 0))
        if b.get("sog") is not None:
            ok_s += int(sum(x[2] for x in per) == int(b.get("sog") or 0))
    return {"players": n, "goals_ok": ok_g, "assists_ok": ok_a, "sog_ok": ok_s}


# ----------------------------------------------------------------------
# THE PERIOD MODEL (10-22): each period's share of the game's goals and of
# its shots on goal, MEASURED on last season's period lines (fit window)
# — 1st period 29% of regulation goals but 33% of shots (empty nets and
# the score push goals late). A skater's 1st-period line is his game
# projection at those shares: points and goals Poisson, shots negative
# binomial at the board's size (binomial thinning keeps the size).
# MEASURED 10-22 on 2025-26's final 60 days (17,102 skater-games), against
# his own 1st-period hit rate over his last 20: point z 11.3, 1+ SOG z
# 13.0, 2+ SOG z 12.1, goal z 11.9, each calibrated (predicted 12.6% vs
# 12.2% points). Blending in his own 1st-period history did NOT help
# (Brier worse at every weight), so it is not in the number.
# ----------------------------------------------------------------------
DEFAULT_SHARES = {"goals": [0.292, 0.348, 0.360], "sog": [0.325, 0.352, 0.323]}
P1_MARKETS = (("p1pt", "1st-period point O0.5", "p1pts", 1),
              ("p1sog1", "1st-period SOG O0.5", "p1sog", 1),
              ("p1sog2", "1st-period SOG O1.5", "p1sog", 2),
              ("p1g", "1st-period goal O0.5", "p1g", 1))
P1_STATS = (("p1pts", "1st-period points", (0.5,)), ("p1sog", "1st-period SOG", (0.5, 1.5)),
            ("p1g", "1st-period goals", (0.5,)))
GAME_MARKETS = (("p1tot15", "1st-period total O1.5"), ("p1lead_home", "Home leads after 1"))


def shares(games, lo=None, hi=None):
    """{"goals": [s1, s2, s3], "sog": [...], "n"} from period lines of
    games dated in [lo, hi)."""
    import numpy as np
    G, S, n = np.zeros(3), np.zeros(3), 0
    for g in (games or {}).values() if isinstance(games, dict) else games or []:
        d = g.get("date") or ""
        if (lo and d < lo) or (hi and d >= hi):
            continue
        ok = False
        for _t, ln in (g.get("lines") or {}).items():
            if len(ln) >= 3:
                G += np.array(ln[:3], dtype=float)
                ok = True
        for _t, s in (g.get("sog") or {}).items():
            if len(s) >= 3:
                S += np.array(s[:3], dtype=float)
        n += int(ok)
    if n < 100 or G.sum() <= 0 or S.sum() <= 0:
        return dict(DEFAULT_SHARES, n=n)
    return {"goals": [round(float(x), 4) for x in G / G.sum()],
            "sog": [round(float(x), 4) for x in S / S.sum()], "n": n}


def p1_pmfs(mu, sh, size):
    """{stat: pmf} for a skater's 1st period from his game means."""
    from engines import model_math as mm
    sh = sh or DEFAULT_SHARES
    g, a, s = (mu or {}).get("g") or 0.0, (mu or {}).get("a") or 0.0, (mu or {}).get("sog") or 0.0
    sg, ss = sh["goals"][0], sh["sog"][0]
    return {"p1pts": mm.poisson_pmf((g + a) * sg, 8), "p1g": mm.poisson_pmf(g * sg, 6),
            "p1sog": mm.nb_pmf(s * ss, size, 15)}


def team_p1(mu_home, mu_away, sh):
    """{"p1tot15", "p1lead_home", "p1tie", "p1lead_away"} — 1st-period goals
    per team Poisson at the goal share of the game model's goals."""
    from engines import model_math as mm
    sg = (sh or DEFAULT_SHARES)["goals"][0]
    h, a = mm.poisson_pmf(mu_home * sg, 10), mm.poisson_pmf(mu_away * sg, 10)
    lead = sum(h[i] * a[j] for i in range(len(h)) for j in range(len(a)) if i > j)
    tie = sum(h[i] * a[i] for i in range(min(len(h), len(a))))
    tot = mm.poisson_pmf((mu_home + mu_away) * sg, 12)
    return {"p1tot15": 1 - tot[0] - tot[1], "p1lead_home": lead, "p1tie": tie,
            "p1lead_away": 1 - lead - tie}


def history(skaters, games):
    """{pid: [(date, [[g, a, sog] x 3])]} — every game he PLAYED (box score),
    the periods from the play-by-play, 0s where the plays never named him
    (he played and did nothing that period — not missing)."""
    side = {}
    for g in (games or {}).values():
        side[(g["date"], str(g["home"]))] = g
        side[(g["date"], str(g["away"]))] = g
    zero = [[0, 0, 0]] * PERIODS
    out = {}
    for pid, p in (skaters or {}).items():
        for row in sorted(p.get("games") or [], key=lambda x: x[0] or ""):
            g = side.get((row[0], str(row[1])))
            if g is not None:
                out.setdefault(str(pid), []).append((row[0], g["players"].get(str(pid), zero)))
    return out


def test(rows, games, skaters, sh, size, lo):
    """The 1st-period markets on games from `lo`, walked forward: each
    skater's game projection (nhl_sim.test_rows) at the shares, against
    his own 1st-period hit rate over his last 20 games; the game lines
    against the league's rate in the fit window. -> {market: {n,
    model_brier, baseline_brier, verdict, calibration}}."""
    from engines import model_math as mm
    by = {(g["date"], str(g["home"])): g for g in (games or {}).values()}
    hist = history(skaters, games)
    zero = [[0, 0, 0]] * PERIODS
    acc = {k: ([], []) for k, *_ in P1_MARKETS}
    for (d, h), gm_ in sorted(rows.items()):
        pg = by.get((d, h))
        if not pg or d < lo:
            continue
        for pid, _side, mu, _line, _act in gm_["players"]:
            arr = pg["players"].get(pid, zero)
            prev = [a for dd, a in hist.get(pid, []) if dd < d][-20:]
            if len(prev) < 5:
                continue
            pm = p1_pmfs(mu, sh, size)
            act = {"p1pts": arr[0][0] + arr[0][1], "p1g": arr[0][0], "p1sog": arr[0][2]}
            past = {"p1pts": [x[0][0] + x[0][1] for x in prev], "p1g": [x[0][0] for x in prev],
                    "p1sog": [x[0][2] for x in prev]}
            for k, _l, st, n in P1_MARKETS:
                y = 1 if act[st] >= n else 0
                acc[k][0].append((mm.prob_at_least(pm[st], n), y))
                acc[k][1].append((sum(1 for v in past[st] if v >= n) / len(past[st]), y))
    # the game lines: the league's own rate before the window is the baseline
    base_t = [sum(g["lines"][t][0] for t in g["lines"]) for g in (games or {}).values()
              if g["date"] < lo and all(len(v) >= 3 for v in g["lines"].values())]
    base_tot = sum(1 for x in base_t if x >= 2) / max(1, len(base_t))
    base_ld = [1 if g["lines"][str(g["home"])][0] > g["lines"][str(g["away"])][0] else 0
               for g in (games or {}).values() if g["date"] < lo
               and str(g["home"]) in g["lines"] and str(g["away"]) in g["lines"]]
    base_lead = sum(base_ld) / max(1, len(base_ld))
    gacc = {k: ([], []) for k, _l in GAME_MARKETS}
    for (d, h), gm_ in sorted(rows.items()):
        pg = by.get((d, h))
        if not pg or d < lo or str(gm_["home"]) not in pg["lines"] \
                or str(gm_["away"]) not in pg["lines"]:
            continue
        lh, la = pg["lines"][str(gm_["home"])][0], pg["lines"][str(gm_["away"])][0]
        t = team_p1(gm_["mu_h"], gm_["mu_a"], sh)
        gacc["p1tot15"][0].append((t["p1tot15"], 1 if lh + la >= 2 else 0))
        gacc["p1tot15"][1].append((base_tot, 1 if lh + la >= 2 else 0))
        gacc["p1lead_home"][0].append((t["p1lead_home"], 1 if lh > la else 0))
        gacc["p1lead_home"][1].append((base_lead, 1 if lh > la else 0))
    out = {}
    for k, (m, b) in list(acc.items()) + list(gacc.items()):
        sm, sb = mm.score_predictions(m), mm.score_predictions(b)
        out[k] = {"n": sm["n"], "model_brier": sm["brier"], "baseline_brier": sb["brier"],
                  "verdict": (mm.paired_verdict([(p - y) ** 2 for p, y in m],
                                                [(q - y) ** 2 for q, y in b]) if m else None),
                  "calibration": mm.calibration_bins(m) if m else [],
                  "predicted": round(sum(p for p, _y in m) / len(m), 4) if m else None,
                  "actual": round(sum(y for _p, y in m) / len(m), 4) if m else None}
    return out


def offered(test_block):
    """The 1st-period player markets a bet can be priced on: only those
    that BEAT his own 1st-period rate on unseen games (no false STRONG)."""
    tv = test_block or {}
    return tuple(m for m in P1_MARKETS
                 if ((tv.get(m[0]) or {}).get("verdict") or {}).get("verdict") == "beats")
