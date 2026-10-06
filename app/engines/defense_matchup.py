"""
DEFENSE VS POSITION — what a defense allows to the kind of player a prop
is about, this season and last, ranked against the league.

One engine for every sport (NHL, NFL, MLB). Each sport's precompute
hands it the same shape — one row per player-game the defense faced:

    {"season": "cur" | "prior", "defense": team id, "game": game id,
     "group": position group ("C", "W", "D" / "QB", "RB", "WR", "TE" /
              a batter or pitcher bucket), "stats": {stat: value}}

and gets back a table it ships in its JSON. Pages read cards off the
table; nothing here fetches anything.

HOW A DEFENSE'S NUMBER IS BUILT
-------------------------------
Per game, everything one position group got against that defense is
summed (two centres with 3 shots each = 6 shots allowed to centres that
night). Then, per defense:

    this season   = allowed this season / games this season
    last season   = allowed last season / games last season
    blended       = (x_cur + w * x_prior + league * s) / (n_cur + w * n_prior + s)

  - s (how many games of league-average evidence a defense starts from)
    is FITTED by a gamma-Poisson likelihood over every defense — the same
    model_math.fit_gamma_prior the props use. Yards are not counts, so on
    yardage this is a quasi-likelihood, exactly as the NFL props treat it.
  - w (what a game last season is worth this season) is FITTED by
    model_math.fit_prior_weight on the defenses present in both seasons
    (standing rule 14: never 0 by habit, never 1 by hope). When it cannot
    be fitted (no current games yet) there is NO blended number: the
    card shows the season it has and says which.

RANK 1 = ALLOWS THE MOST. The question a prop asks is "is this a good
spot for him?", so the top of the list is the softest defense. Ties
share the better rank; a defense with nothing measured gets no rank,
never a last place (rule 6).

TIER ("Soft" / "Tough") is a QUARTILE CUT — top quarter of the league
by what it allows is Soft, bottom quarter Tough. That is a presentation
choice about where to draw a flag, not a measured effect size, and the
page shows the rank and the per-game number beside it so the reader can
judge the size himself.

IS THE MATCHUP REAL? (reliability)
----------------------------------
A defense ranked 3rd might be 3rd because it is bad at it, or because
of four bad nights. On last season's games each defense is split into
odd and even games; the correlation of the two halves across the league
(Spearman-Brown corrected — the textbook split-half reliability) says how
much of a ranking repeats. ~0 = the ranking is mostly noise; toward 1 =
it is a stable trait. The page prints it beside the rank in those words.

WHETHER THE SPLIT MOVES THE CHANCE is a different question, answered per
sport by that sport's own walk-forward (e.g. nhl_model.validate_dvp). A
real, stable difference can still add nothing once the model already
knows the team's TOTAL allowed. Only a split that beats the model on
games it had not seen is allowed into the number; otherwise it is
context, and the page says which.

Pure — no streamlit, no requests.
"""
from math import ceil

from engines import model_math as mm

CUR, PRIOR = "cur", "prior"


# ----------------------------------------------------------------------
# Building the table
# ----------------------------------------------------------------------
def _per_game(lines):
    """{(season, defense, game): {group: {stat: sum}}} plus, per game, the
    stats that were RECORDED at all — a stat no row in a game carries is
    unmeasured that game, not a zero (rule 6). A group absent from a game
    whose stat WAS recorded is a real zero: they played, he got nothing."""
    games = {}
    recorded = {}
    for ln in lines or []:
        season, d, gid, grp = ln.get("season"), ln.get("defense"), ln.get("game"), ln.get("group")
        if season not in (CUR, PRIOR) or d in (None, "") or gid in (None, "") or not grp:
            continue
        key = (season, str(d), str(gid))
        slot = games.setdefault(key, {}).setdefault(grp, {})
        rec = recorded.setdefault(key, set())
        for stat, v in (ln.get("stats") or {}).items():
            if v is None:
                continue
            slot[stat] = slot.get(stat, 0.0) + float(v)
            rec.add(stat)
    return games, recorded


def _rank_desc(values):
    """{team: rank}, 1 = largest value; ties share the better rank."""
    have = sorted(((t, v) for t, v in values.items() if v is not None), key=lambda x: -x[1])
    out, prev, prev_rank = {}, None, 0
    for i, (t, v) in enumerate(have, start=1):
        r = prev_rank if prev is not None and abs(v - prev) < 1e-12 else i
        out[t] = r
        prev, prev_rank = v, r
    return out


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sxx * syy) ** 0.5


def split_half_reliability(per_team_games):
    """Spearman-Brown corrected odd/even split-half correlation across
    defenses. per_team_games: {team: [per-game value in date order]}.
    None when fewer than three defenses have games in both halves."""
    xs, ys = [], []
    for vals in per_team_games.values():
        odd, even = vals[0::2], vals[1::2]
        if not odd or not even:
            continue
        xs.append(sum(odd) / len(odd))
        ys.append(sum(even) / len(even))
    r = _pearson(xs, ys)
    if r is None:
        return None
    if r <= -1:
        return 0.0
    rel = 2 * r / (1 + r)
    return round(max(rel, 0.0), 3)


def build_table(lines, stats, groups, game_dates=None):
    """The defense-vs-position table for one sport.

    stats: stat keys to tabulate; groups: position groups (an "ALL" group
    — everyone the defense faced — is always added). game_dates
    ({game id: date}) orders last season's games for the reliability
    split; without it games are taken in id order.
    """
    games, recorded = _per_game(lines)
    all_groups = list(groups) + ["ALL"]
    defenses = sorted({k[1] for k in games})
    table = {"stats": {}, "teams": defenses, "of": len(defenses)}
    order = (lambda k: (game_dates or {}).get(k[2], k[2]))
    for stat in stats:
        st = table["stats"][stat] = {}
        for grp in all_groups:
            acc = {d: {CUR: [0.0, 0], PRIOR: [0.0, 0]} for d in defenses}
            prior_series = {}
            for key in sorted(games, key=order):
                season, d, _gid = key
                if stat not in recorded.get(key, ()):
                    continue
                byg = games[key]
                v = (sum(g.get(stat, 0.0) for g in byg.values()) if grp == "ALL"
                     else byg.get(grp, {}).get(stat, 0.0))
                acc[d][season][0] += v
                acc[d][season][1] += 1
                if season == PRIOR:
                    prior_series.setdefault(d, []).append(v)
            st[grp] = _summarise(acc, prior_series)
    return table


def _poisson_ll(pairs, mean, strength, w):
    from math import log
    tot = 0.0
    for (x0, n0), (x1, n1) in pairs:
        if not n1:
            continue
        r = max(mm.prior_season_rate(x0, n0, 0, 0, mean, strength, w), 1e-9)
        tot += x1 * log(r * n1) - r * n1
    return tot


def _dispersion(prior_series):
    """Quasi-Poisson dispersion phi: Pearson chi-square per degree of
    freedom of each defense's games around its own mean. ~1 for counts
    that behave like Poisson; large for yards. It scales the likelihood
    test below so a yardage table is not judged as if every yard were an
    independent event."""
    num, df = 0.0, 0
    for vals in prior_series.values():
        if len(vals) < 2:
            continue
        mu = sum(vals) / len(vals)
        if mu <= 0:
            continue
        num += sum((v - mu) ** 2 for v in vals) / mu
        df += len(vals) - 1
    return max(num / df, 1.0) if df else 1.0


def fit_season_weight(acc, prior_series, mean, strength):
    """(weight, report) — what a game last season is worth this season.

    The direct fit (last season -> this season, model_math.fit_prior_weight)
    is the right number once this season says something. In its first
    weeks it cannot: with two games a team the likelihood is flat and its
    maximum lands at 0 or 1 by noise (measured 10-06: NHL C 0.0, W 1.0 on
    the same night). So there is a reference weight that IS identified —
    last season's FIRST half predicting its SECOND half, the same fit on
    a split that has 40 games a side — and the direct fit replaces it only
    when this season's own likelihood prefers it by a likelihood-ratio
    test (chi-square, 1 df, 95%: 1.92 log-lik units, scaled by the
    measured dispersion). No games-played cutoff is chosen anywhere."""
    split_pairs = []
    for vals in prior_series.values():
        h = len(vals) // 2
        if h and len(vals) - h:
            split_pairs.append(((sum(vals[:h]), h), (sum(vals[h:]), len(vals) - h)))
    ref = mm.fit_prior_weight([(split_pairs, mean, strength)], kind="poisson") if split_pairs else None
    cur_pairs = [((a[PRIOR][0], a[PRIOR][1]), (a[CUR][0], a[CUR][1]))
                 for a in acc.values() if a[PRIOR][1] and a[CUR][1]]
    direct = mm.fit_prior_weight([(cur_pairs, mean, strength)], kind="poisson") if cur_pairs else None
    phi = _dispersion(prior_series)
    report = {"reference_split_half": ref, "direct": direct, "dispersion": round(phi, 2)}
    if ref is None and direct is None:
        return None, report
    if direct is None:
        report["used"] = "reference"
        return ref["weight"], report
    if ref is None:
        report["used"] = "direct"
        return direct["weight"], report
    lr = (_poisson_ll(cur_pairs, mean, strength, direct["weight"])
          - _poisson_ll(cur_pairs, mean, strength, ref["weight"])) / phi
    report["lr_log_lik"] = round(lr, 3)
    if lr > 1.92:
        report["used"] = "direct"
        return direct["weight"], report
    report["used"] = "reference"
    return ref["weight"], report


def _summarise(acc, prior_series):
    pooled = [(a[CUR][0] + a[PRIOR][0], a[CUR][1] + a[PRIOR][1]) for a in acc.values()]
    mean, strength = mm.fit_gamma_prior([(x, n) for x, n in pooled if n])
    n_cur_tot = sum(a[CUR][1] for a in acc.values())
    n_pri_tot = sum(a[PRIOR][1] for a in acc.values())
    league_cur = (sum(a[CUR][0] for a in acc.values()) / n_cur_tot) if n_cur_tot else None
    league_pri = (sum(a[PRIOR][0] for a in acc.values()) / n_pri_tot) if n_pri_tot else None

    weight, report = None, None
    if mean is not None and strength is not None and n_pri_tot:
        weight, report = fit_season_weight(acc, prior_series, mean, strength)

    teams, blend_v, cur_v, pri_v = {}, {}, {}, {}
    for d, a in acc.items():
        (xc, nc), (xp, npr) = a[CUR], a[PRIOR]
        row = {"n_cur": nc, "n_prior": npr,
               "cur": round(xc / nc, 3) if nc else None,
               "prior": round(xp / npr, 3) if npr else None}
        if weight is not None and (nc or npr):
            row["blend"] = round(mm.prior_season_rate(xp, npr, xc, nc, mean, strength, weight), 3)
        teams[d] = row
        blend_v[d], cur_v[d], pri_v[d] = row.get("blend"), row["cur"], row["prior"]
    rb, rc, rp = _rank_desc(blend_v), _rank_desc(cur_v), _rank_desc(pri_v)
    for d, row in teams.items():
        row["rank"], row["rank_cur"], row["rank_prior"] = rb.get(d), rc.get(d), rp.get(d)
    return {
        "league": round(mean, 3) if mean is not None else None,
        "league_cur": round(league_cur, 3) if league_cur is not None else None,
        "league_prior": round(league_pri, 3) if league_pri is not None else None,
        "strength_games": round(strength, 2) if strength is not None else None,
        "weight": weight, "weight_report": report,
        "reliability": split_half_reliability(prior_series),
        "ranked": {"blend": len(rb), "cur": len(rc), "prior": len(rp)},
        "teams": teams,
    }


# ----------------------------------------------------------------------
# Reading the table
# ----------------------------------------------------------------------
def tier(rank, of):
    """'soft' (top quarter by what it allows), 'tough' (bottom quarter),
    'neutral', or None without a rank. A quartile cut, not a measured
    effect size — see the module docstring."""
    if not rank or not of:
        return None
    q = ceil(of / 4.0)
    if rank <= q:
        return "soft"
    if rank > of - q:
        return "tough"
    return "neutral"


def card(table, defense, group, stat):
    """Everything the page needs about one defense against one position
    group on one stat, or None when the table does not cover it.

    The rank and tier come from the BLENDED number when there is one,
    else from whichever single season exists — and `basis` says which,
    because a this-season rank on three games and a blended rank are not
    the same claim (rule 9)."""
    s = ((table or {}).get("stats") or {}).get(stat) or {}
    g = s.get(group)
    if not g:
        return None
    row = (g.get("teams") or {}).get(str(defense))
    if not row:
        return None
    if row.get("blend") is not None:
        basis, value, rank, of, league = "blend", row["blend"], row.get("rank"), g["ranked"]["blend"], g.get("league")
    elif row.get("cur") is not None:
        basis, value, rank, of, league = "cur", row["cur"], row.get("rank_cur"), g["ranked"]["cur"], g.get("league_cur")
    elif row.get("prior") is not None:
        basis, value, rank, of, league = "prior", row["prior"], row.get("rank_prior"), g["ranked"]["prior"], g.get("league_prior")
    else:
        return None
    vs = round(100.0 * (value / league - 1.0), 1) if league else None
    return {
        "group": group, "stat": stat, "basis": basis,
        "per_game": value, "league": league, "vs_league_pct": vs,
        "rank": rank, "of": of, "tier": tier(rank, of),
        "cur": row.get("cur"), "n_cur": row.get("n_cur"), "rank_cur": row.get("rank_cur"),
        "of_cur": g["ranked"]["cur"],
        "prior": row.get("prior"), "n_prior": row.get("n_prior"),
        "rank_prior": row.get("rank_prior"), "of_prior": g["ranked"]["prior"],
        "reliability": g.get("reliability"), "weight": g.get("weight"),
    }


def ordinal(n):
    if n is None:
        return "—"
    n = int(n)
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def reliability_words(rel):
    """The split-half number in words, with the number beside it. The
    three bands are labels for a reader, printed with the value; they do
    not change any probability."""
    if rel is None:
        return "untested"
    if rel < 0.3:
        word = "mostly noise"
    elif rel < 0.6:
        word = "partly repeatable"
    else:
        word = "a stable trait"
    return f"{word} (split-half {rel:.2f})"


BASIS_WORDS = {"blend": "this season + last, blended",
               "cur": "this season only", "prior": "last season only"}


def rank_text(c):
    """'3rd-most of 32' in the top half, '2nd-fewest of 32' in the bottom
    half (rank 31 of 32 IS the 2nd-fewest) — or an em-dash."""
    if not c or not c.get("rank"):
        return "—"
    r, of = int(c["rank"]), int(c.get("of") or 0)
    if of and r > (of + 1) / 2:
        return f"{ordinal(of - r + 1)}-fewest of {of}"
    return f"{ordinal(r)}-most of {of}"


def notice(c, stat_label, group_label, defense_label, fmt="{:.1f}"):
    """One sentence for the play: who, what, how much, and whether it
    repeats. None when there is no card.

        Soft matchup — MTL allows the 3rd-most shots on goal to centres
        (8.9 a game vs 7.6 league, +17%; this season 2nd of 32, last
        season 6th). Ranking is partly repeatable (split-half 0.41).
    """
    if not c:
        return None
    fmt = c.get("fmt") or fmt
    head = {"soft": "Soft matchup", "tough": "Tough matchup",
            "neutral": "Neutral matchup"}.get(c.get("tier"), "Matchup")
    pg = fmt.format(c["per_game"]) if c.get("per_game") is not None else "—"
    lg = fmt.format(c["league"]) if c.get("league") is not None else "—"
    vs = f", {c['vs_league_pct']:+.0f}%" if c.get("vs_league_pct") is not None else ""
    seasons = []
    if c.get("rank_cur"):
        seasons.append(f"this season {ordinal(c['rank_cur'])} of {c['of_cur']} "
                       f"over {c['n_cur']} game{'s' if c['n_cur'] != 1 else ''}")
    if c.get("rank_prior"):
        seasons.append(f"last season {ordinal(c['rank_prior'])} of {c['of_prior']}")
    tail = f"; {', '.join(seasons)}" if seasons else ""
    unit = c.get("unit") or "a game"
    rel = (f" That ranking is {reliability_words(c.get('reliability'))}."
           if "reliability" in c else "")
    return (f"{head} — {defense_label} allows the {rank_text(c)} {stat_label} to "
            f"{group_label} ({pg} {unit} vs {lg} league{vs}{tail}; ranked on "
            f"{BASIS_WORDS[c['basis']]}).{rel}")


def badge(c):
    """Short cell text: 'SOFT · 3rd-most' / 'TOUGH · 2nd-fewest' / '14th-most'
    (a neutral defense is just its rank) / '—'."""
    if not c or not c.get("rank"):
        return "—"
    short = rank_text(c).rsplit(" of ", 1)[0]
    t = c.get("tier")
    return f"{t.upper()} · {short}" if t in ("soft", "tough") else short


# ----------------------------------------------------------------------
# MLB: the "defense" is a pitcher (10-06)
# ----------------------------------------------------------------------
# A batter prop's defense is tonight's STARTER, and what matters is his
# rate per plate appearance, not per game (a game is however long he
# lasted). Each stat below is a per-PA expectation from the seven-outcome
# rates the prop model already uses.
MLB_STAT_OUTCOMES = {
    "h": {"1B": 1, "2B": 1, "3B": 1, "HR": 1},
    "tb": {"1B": 1, "2B": 2, "3B": 3, "HR": 4},
    "hr": {"HR": 1}, "k": {"K": 1}, "bb": {"BB": 1},
    "s": {"1B": 1}, "d": {"2B": 1},
}
MLB_STAT_LABELS = {"h": "hits", "tb": "total bases", "hr": "home runs", "k": "strikeouts",
                   "bb": "walks", "s": "singles", "d": "doubles"}


def per_pa(counts, priors, stat):
    """Shrunk per-PA expectation of `stat` (beta-binomial per outcome, the
    prop model's own fitted priors). None without priors."""
    w = MLB_STAT_OUTCOMES.get(stat)
    if not w or not priors:
        return None
    n = (counts or {}).get("PA", 0) or 0
    tot = 0.0
    for o, mult in w.items():
        mean, s_ = (priors.get(o) or [None, None])
        if mean is None:
            return None
        tot += mult * ((counts or {}).get(o, 0) + mean * s_) / (n + s_)
    return tot


def _blend_counts(cur, prior, weight):
    if not prior or not weight:
        return dict(cur or {})
    keys = set(cur or {}) | set(prior)
    return {k: (cur or {}).get(k, 0) + weight * prior.get(k, 0) for k in keys
            if k in MLB_ALL_OUTCOMES or k == "PA"}


MLB_ALL_OUTCOMES = ("1B", "2B", "3B", "HR", "BB", "K", "OUT")


def mlb_starter_table(cur_counts, prior_counts, weight, priors, starters):
    """{"of", "league", "pitchers": {pid: {stat: {...}}}} — every starter
    this season, his allowed per-PA rates this season, last season and
    blended (last season at the FITTED pitcher weight the props use),
    ranked 1 = allows the most among this season's starters."""
    starters = [str(x) for x in starters or []]
    league = {st: per_pa({}, priors, st) for st in MLB_STAT_OUTCOMES}
    out = {"of": 0, "league": {k: round(v, 4) for k, v in league.items() if v is not None},
           "weight": weight, "pitchers": {}}
    vals = {st: {} for st in MLB_STAT_OUTCOMES}
    for pid in starters:
        c = (cur_counts or {}).get(pid) or {}
        pr = (prior_counts or {}).get(pid) or {}
        row = {"pa_cur": int(c.get("PA", 0) or 0), "pa_prior": int(pr.get("PA", 0) or 0)}
        bl = _blend_counts(c, pr, weight)
        for st in MLB_STAT_OUTCOMES:
            v = per_pa(bl, priors, st)
            row[st] = {"blend": round(v, 4) if v is not None else None,
                       "cur": round(per_pa(c, priors, st), 4) if c.get("PA") else None,
                       "prior": round(per_pa(pr, priors, st), 4) if pr.get("PA") else None}
            vals[st][pid] = v
        out["pitchers"][pid] = row
    for st in MLB_STAT_OUTCOMES:
        rk = _rank_desc(vals[st])
        for pid, r in rk.items():
            out["pitchers"][pid][st]["rank"] = r
    out["of"] = len(starters)
    return out


def mlb_starter_card(table, pid, stat):
    """The batter-prop card: tonight's starter on one stat, or None."""
    row = ((table or {}).get("pitchers") or {}).get(str(pid))
    if not row or stat not in row or row[stat].get("blend") is None:
        return None
    x = row[stat]
    league = (table.get("league") or {}).get(stat)
    of = table.get("of")
    return {"group": "batters", "stat": stat, "basis": "blend" if row["pa_prior"] and row["pa_cur"]
            else ("cur" if row["pa_cur"] else "prior"),
            "per_game": x["blend"], "unit": "per plate appearance", "league": league,
            "vs_league_pct": round(100.0 * (x["blend"] / league - 1.0), 1) if league else None,
            "rank": x.get("rank"), "of": of, "tier": tier(x.get("rank"), of),
            "cur": x.get("cur"), "n_cur": row["pa_cur"], "prior": x.get("prior"),
            "n_prior": row["pa_prior"], "fmt": "{:.3f}"}


def mlb_lineup_card(team_table, lineup_rate, stat):
    """The pitcher-prop card: tonight's lineup's per-PA rate on `stat`
    (from the nine bats the model uses), placed among this season's team
    rates — 1 = the lineup most likely to give it up. None without both."""
    teams = ((team_table or {}).get("teams") or {})
    vals = [t.get(stat) for t in teams.values() if t.get(stat) is not None]
    if lineup_rate is None or not vals:
        return None
    rank = 1 + sum(1 for v in vals if v > lineup_rate)
    of = len(vals)
    league = (team_table.get("league") or {}).get(stat)
    return {"group": "tonight's lineup", "stat": stat, "basis": "cur",
            "per_game": round(lineup_rate, 4), "unit": "per plate appearance", "league": league,
            "vs_league_pct": round(100.0 * (lineup_rate / league - 1.0), 1) if league else None,
            "rank": rank, "of": of, "tier": tier(rank, of), "fmt": "{:.3f}"}
