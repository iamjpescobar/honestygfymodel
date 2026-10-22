"""
MLB game simulator (10-22) — play tonight's game thousands of times, plate
appearance by plate appearance, every batter's and both starters' lines
drawn TOGETHER, so a same-game parlay is priced on how its legs move
together.

ONE SIMULATED GAME
------------------
  1. Each plate appearance: the batter in the order against the starter
     (his outcome rates x the starter's allowed rates / the league's —
     engines/mlb_props.combine, the props model's own per-PA numbers),
     until the starter has faced the number of batters drawn for him
     from his own batters-faced distribution (mlb_props.starter_bf_dist);
     then the bullpen as a league-average arm. Outcomes 1B 2B 3B HR BB K
     OUT.
  2. What the play does to the bases, the outs and the score: drawn from
     the season's REAL plate appearances — for every base-out state (24)
     and outcome, how often it led to each next state and how many runs
     scored (measure_transitions; a single with a man on second scores
     him as often as it really did, a ground out turns two as often as it
     really did). Runners keep their order; whoever crosses the plate is
     credited a run, the batter an RBI for each run on his play (the
     site's RBI definition, engines/mlb_props.RBI_NOTE).
  3. Nine innings; no bottom of the ninth when the home team leads; a
     walk-off ends it; extra innings start with a runner on second (the
     batter before the leadoff man), to 15, then a coin.

WHAT IT GIVES: every batter's hits, total bases, HR, RBI, runs, H+R+RBI,
strikeouts, walks; both starters' strikeouts, outs, hits, walks, runs;
the score by inning (first five innings and the full game).

WHAT IT CHANGES: the JOINT chance of a same-game parlay — the legs'
delivered chances multiplied, times the simulator's LIFT (P(all) / the
product of P(each), both from the simulator).

TESTED (rule 1, mlb_prop_precompute.build_sim): the last 30 days of
games, walked forward like the props test — two / three teammates with a
hit, two teammates with 2+ total bases, a hit or a homer + his team wins,
the starter's strikeouts + his team wins, a hitter from each side —
priced with the lift vs plain multiplication, against what happened. A
kind that has not beaten that stays at THIN.

numpy, no streamlit, no requests.
"""
import numpy as np

OUTCOMES = ("1B", "2B", "3B", "HR", "BB", "K", "OUT")
OI = {o: i for i, o in enumerate(OUTCOMES)}
TB = np.array([1, 2, 3, 4, 0, 0, 0])
HIT = np.array([1, 1, 1, 1, 0, 0, 0])
MAX_INN = 15
SGP_MAX_LEGS = 8
SGP_SIMS = 50_000         # ~4 s on the page; the lift's standard error is printed
SGP_CHUNK = 25_000
STRONG_MIN_COMBOS = 100
BAT_STATS = ("h", "tb", "hr", "rbi", "r", "hrr", "k", "bb", "s", "d")
SP_STATS = ("k", "outs", "h", "bb", "er")
KIND_LABEL = {"HH": "2 teammates with a hit", "HHH": "3 teammates with a hit",
              "TT": "2 teammates with 2+ total bases", "HW": "a hit + his team wins",
              "RW": "a home run + his team wins", "KW": "the starter's strikeouts + his team wins",
              "HHopp": "a hitter from each side"}


# ----------------------------------------------------------------------
# The base-out transitions, measured on the season's plate appearances
# ----------------------------------------------------------------------
def _na(v):
    """True for None, NaN and pandas' NA (any value that is not itself)."""
    if v is None:
        return True
    try:
        return bool(v != v)
    except TypeError:
        return True


def state_rows(pa):
    """[(before_bases, outs, outcome, after_bases, runs, outs_added)] from a
    plate-appearance frame with inning, inning_topbot, outs_when_up,
    on_1b / on_2b / on_3b, bat_score, post_bat_score (rows in game and
    at-bat order). A half-inning's last PA ends it (outs to 3)."""
    need = ("game_pk", "at_bat_number", "inning", "inning_topbot", "outs_when_up", "on_1b",
            "on_2b", "on_3b", "bat_score", "post_bat_score", "outcome")
    if pa is None or not all(c in pa.columns for c in need):
        return []
    df = pa.sort_values(["game_pk", "at_bat_number"])
    # Statcast's nullable integer columns hold pandas' NA, whose truth value
    # raises ("boolean value of NA is ambiguous" — the 10-22 nightly): every
    # missing value becomes None before any comparison
    cols = {c: [None if _na(v) else v for v in df[c].tolist()] for c in need}
    out = []
    n = len(df)
    for i in range(n):
        o = cols["outs_when_up"][i]
        if o is None or int(o) > 2:
            continue
        bb = sum(b for b, c in ((1, "on_1b"), (2, "on_2b"), (4, "on_3b"))
                 if cols[c][i] is not None)
        try:
            runs = int(cols["post_bat_score"][i]) - int(cols["bat_score"][i])
        except (TypeError, ValueError):
            continue
        if runs < 0 or runs > 4:
            continue
        same = (i + 1 < n and cols["game_pk"][i + 1] == cols["game_pk"][i]
                and cols["inning"][i + 1] == cols["inning"][i]
                and cols["inning_topbot"][i + 1] == cols["inning_topbot"][i])
        if same:
            o2 = cols["outs_when_up"][i + 1]
            if o2 is None or int(o2) < int(o):
                continue
            ab = sum(b for b, c in ((1, "on_1b"), (2, "on_2b"), (4, "on_3b"))
                     if cols[c][i + 1] is not None)
            add = int(o2) - int(o)
        else:
            ab, add = 0, 3 - int(o)
        oc = cols["outcome"][i]
        if oc not in OI:
            continue
        out.append((bb, int(o), oc, ab, runs, add))
    return out


def measure_transitions(rows, min_n=20):
    """{"T": {"<bases>|<outs>|<outcome>": [[after, runs, outs_added, n], ...]},
    "n": rows used}. A cell with fewer than min_n plays borrows the same
    bases-and-outcome cell over all outs (outs added capped so the inning
    still ends)."""
    from collections import Counter
    cell, by_bo = {}, {}
    for bb, o, oc, ab, runs, add in rows:
        cell.setdefault((bb, o, oc), Counter())[(ab, runs, add)] += 1
        by_bo.setdefault((bb, oc), Counter())[(ab, runs, add)] += 1
    T = {}
    for bb in range(8):
        for o in range(3):
            for oc in OUTCOMES:
                c = cell.get((bb, o, oc))
                if not c or sum(c.values()) < min_n:
                    c = by_bo.get((bb, oc))
                if not c:
                    continue
                agg = Counter()
                for (ab, runs, add), k in c.items():
                    agg[(ab, runs, min(add, 3 - o))] += k
                T[f"{bb}|{o}|{oc}"] = [[ab, runs, add, k] for (ab, runs, add), k in
                                       sorted(agg.items())]
    return {"T": T, "n": len(rows)}


def _move(before, after, runs, add, oc):
    """Where each of [runner on 3rd, on 2nd, on 1st, batter] goes: 1-3 a
    base, 4 scored, 0 out / gone, -1 nobody there. Runners keep their
    order; on an out the batter is the one out first."""
    src = [k for k, b in ((0, 4), (1, 2), (2, 1)) if before & b] + [3]
    scored, rem = src[:runs], src[runs:]
    dest_bases = [b for b in (3, 2, 1) if after & (1 << (b - 1))]
    extra = len(rem) - len(dest_bases)
    if extra > 0:
        if oc in ("K", "OUT") and 3 in rem:
            rem.remove(3)
            extra -= 1
        while extra > 0 and rem:
            rem.pop(0)
            extra -= 1
    out = [-1, -1, -1, -1]
    for k in src:
        out[k] = 0
    for k in scored:
        out[k] = 4
    for k, b in zip(rem, dest_bases):
        out[k] = b
    return out


def tables(trans):
    """numpy lookups from measure_transitions: per cell index (bases*21 +
    outs*7 + outcome) the cumulative probabilities and each result's
    after-bases, runs, outs added and runner moves."""
    T = (trans or {}).get("T") or {}
    K = max([len(v) for v in T.values()] or [1])
    C = 8 * 3 * 7
    cum = np.ones((C, K))
    after = np.zeros((C, K), dtype=np.int8)
    runs = np.zeros((C, K), dtype=np.int8)
    add = np.ones((C, K), dtype=np.int8)
    move = np.full((C, K, 4), -1, dtype=np.int8)
    for key, res in T.items():
        bb, o, oc = key.split("|")
        bb, o = int(bb), int(o)
        idx = bb * 21 + o * 7 + OI[oc]
        tot = sum(r[3] for r in res)
        acc = 0.0
        for j, (ab, rr, ad, k) in enumerate(res):
            acc += k / tot
            cum[idx, j] = acc
            after[idx, j], runs[idx, j], add[idx, j] = ab, rr, ad
            move[idx, j] = _move(bb, ab, rr, ad, oc)
        cum[idx, len(res) - 1:] = 1.0
        for j in range(len(res), K):
            after[idx, j], runs[idx, j], add[idx, j] = after[idx, 0], runs[idx, 0], add[idx, 0]
            move[idx, j] = move[idx, 0]
    return {"cum": cum, "after": after, "runs": runs, "add": add, "move": move}


# ----------------------------------------------------------------------
# One simulated game
# ----------------------------------------------------------------------
def _cum(rows):
    """9 x 7 cumulative outcome probabilities from 9 {outcome: p} dicts."""
    a = np.array([[float(r.get(o, 0.0)) for o in OUTCOMES] for r in rows])
    a = a / a.sum(axis=1, keepdims=True)
    c = np.cumsum(a, axis=1)
    c[:, -1] = 1.0
    return c


def simulate(game, tab, n=10000, seed=7):
    """game: {"home": side, "away": side}; side = {"pids": [9 batter ids in
    order], "vs_sp": [9 {outcome: p}] against the OTHER team's starter,
    "vs_pen": [9 {outcome: p}] against a league-average arm, "bf": {bf: p}
    for this side's OWN starter, "sp": his id}. tab: tables().
    -> {"home", "away" (runs), "inn": {side: (n, innings)}, "stats":
    {pid: {stat: int16}}, "sp": {side: {stat: int16}}}"""
    rng = np.random.default_rng(seed)
    S = {}
    for side in ("home", "away"):
        g = game[side]
        S[side] = {"sp_cum": _cum(g["vs_sp"]), "pen_cum": _cum(g["vs_pen"]),
                   "pos": np.zeros(n, dtype=np.int64),
                   "bat": {k: np.zeros((n, 9), dtype=np.int32) for k in
                           ("h", "tb", "hr", "rbi", "r", "k", "bb", "s", "d")},
                   "runs": np.zeros((n, MAX_INN), dtype=np.int32)}
        bf = g.get("bf") or {}
        ks = np.array(sorted(int(k) for k in bf)) if bf else np.array([18])
        ps = np.array([float(bf.get(k, bf.get(str(k), 0))) for k in ks]) if bf else np.ones(1)
        ps = ps / ps.sum()
        S[side]["limit"] = rng.choice(ks, size=n, p=ps)
        S[side]["bf"] = np.zeros(n, dtype=np.int64)
        S[side]["spl"] = {k: np.zeros(n, dtype=np.int32) for k in SP_STATS}
    total = {"home": np.zeros(n, dtype=np.int32), "away": np.zeros(n, dtype=np.int32)}
    over = np.zeros(n, dtype=bool)
    ar = np.arange(n)
    for inn in range(MAX_INN):
        for bat, pit in (("away", "home"), ("home", "away")):
            B, P = S[bat], S[pit]
            live = ~over
            if bat == "home" and inn >= 8:
                live &= ~(total["home"] > total["away"])     # no bottom half when ahead
            if not live.any():
                continue
            outs = np.zeros(n, dtype=np.int64)
            occ = np.zeros((n, 3), dtype=np.int64)           # [3rd, 2nd, 1st]: slot + 1
            if inn >= 9:                                     # the extra-inning runner
                occ[:, 1] = np.where(live, (B["pos"] - 1) % 9 + 1, 0)
            act = live.copy()
            guard = 0
            while act.any() and guard < 40:
                guard += 1
                ix = ar[act]
                slot = B["pos"][ix]
                vs = P["bf"][ix] < P["limit"][ix]
                cum = np.where(vs[:, None], B["sp_cum"][slot], B["pen_cum"][slot])
                oc = (rng.random(len(ix))[:, None] > cum).sum(axis=1)
                oc = np.minimum(oc, 6)
                bases = ((occ[ix, 2] > 0) * 1 + (occ[ix, 1] > 0) * 2 + (occ[ix, 0] > 0) * 4)
                cell = bases * 21 + outs[ix] * 7 + oc
                j = (rng.random(len(ix))[:, None] > tab["cum"][cell]).sum(axis=1)
                j = np.minimum(j, tab["cum"].shape[1] - 1)
                rr = tab["runs"][cell, j].astype(np.int64)
                ad = tab["add"][cell, j].astype(np.int64)
                mv = tab["move"][cell, j]                    # (m, 4)
                src = np.stack([occ[ix, 0], occ[ix, 1], occ[ix, 2], slot + 1], axis=1)
                new = np.zeros((len(ix), 3), dtype=np.int64)
                for k in range(4):
                    for b, col in ((3, 0), (2, 1), (1, 2)):
                        put = mv[:, k] == b
                        new[put, col] = src[put, k]
                    sc = (mv[:, k] == 4) & (src[:, k] > 0)
                    if sc.any():
                        np.add.at(B["bat"]["r"], (ix[sc], src[sc, k] - 1), 1)
                occ[ix] = new
                bt = B["bat"]
                np.add.at(bt["h"], (ix, slot), HIT[oc])
                np.add.at(bt["tb"], (ix, slot), TB[oc])
                np.add.at(bt["hr"], (ix, slot), (oc == 3).astype(np.int32))
                np.add.at(bt["k"], (ix, slot), (oc == 5).astype(np.int32))
                np.add.at(bt["bb"], (ix, slot), (oc == 4).astype(np.int32))
                np.add.at(bt["s"], (ix, slot), (oc == 0).astype(np.int32))
                np.add.at(bt["d"], (ix, slot), (oc == 1).astype(np.int32))
                np.add.at(bt["rbi"], (ix, slot), rr)
                sp = P["spl"]
                sp["k"][ix] += (vs & (oc == 5)).astype(np.int32)
                sp["h"][ix] += (vs * HIT[oc]).astype(np.int32)
                sp["bb"][ix] += (vs & (oc == 4)).astype(np.int32)
                sp["er"][ix] += (vs * rr).astype(np.int32)
                sp["outs"][ix] += (vs * np.minimum(ad, 3 - outs[ix])).astype(np.int32)
                P["bf"][ix] += 1
                total[bat][ix] += rr
                B["runs"][ix, inn] += rr
                B["pos"][ix] = (slot + 1) % 9
                outs[ix] += ad
                done = outs[ix] >= 3
                if bat == "home" and inn >= 8:
                    done |= total["home"][ix] > total["away"][ix]   # walk-off
                act[ix[done]] = False
        if inn >= 8:
            over |= total["home"] != total["away"]
        if over.all():
            break
    tie = total["home"] == total["away"]
    coin = rng.random(n) < 0.5
    total["home"] = total["home"] + (tie & coin)
    total["away"] = total["away"] + (tie & ~coin)
    out = {"home": total["home"], "away": total["away"],
           "inn": {s: S[s]["runs"] for s in ("home", "away")}, "stats": {}, "sp": {}}
    for side in ("home", "away"):
        bt = S[side]["bat"]
        for i, pid in enumerate(game[side]["pids"]):
            st = {k: bt[k][:, i].astype(np.int16) for k in bt}
            st["hrr"] = (bt["h"][:, i] + bt["r"][:, i] + bt["rbi"][:, i]).astype(np.int16)
            out["stats"][str(pid)] = st
        out["sp"][side] = {k: v.astype(np.int16) for k, v in S[side]["spl"].items()}
    return out


# ----------------------------------------------------------------------
# Legs and the joint chance
# ----------------------------------------------------------------------
def leg_hits(sim, leg):
    """leg {"pid", "stat", "line", "side"}: pid "_game" (stat home_win /
    away_win / total / home_margin / away_margin / f5_total /
    f5_home_margin / f5_away_margin), "_sp_home" / "_sp_away" (a starter's
    k / outs / h / bb / er), else a batter's stat."""
    pid = str(leg.get("pid"))
    st = leg["stat"]
    if pid == "_game":
        h, a = sim["home"], sim["away"]
        if st.startswith("f5_"):
            h, a = sim["inn"]["home"][:, :5].sum(axis=1), sim["inn"]["away"][:, :5].sum(axis=1)
            st = st[3:]
        if st == "home_win":
            return h > a
        if st == "away_win":
            return a > h
        v = (h + a) if st == "total" else ((h - a) if st == "home_margin" else (a - h))
    elif pid.startswith("_sp_"):
        v = sim["sp"][pid[4:]][st]
    else:
        v = sim["stats"][pid][st]
    hit = v > leg["line"]
    return hit if leg.get("side", "Over") == "Over" else ~hit


def joint(sim, legs):
    hits = [leg_hits(sim, lg) for lg in legs]
    each = [float(h.mean()) for h in hits]
    allp = float(np.logical_and.reduce(hits).mean()) if hits else None
    prod = float(np.prod(each)) if each else None
    return {"each": each, "all": allp, "product": prod,
            "lift": (allp / prod) if prod else None}


def joint_precise(game, tab, legs, n=SGP_SIMS, chunk=SGP_CHUNK, seed=7):
    each_hits = [0] * len(legs)
    all_hits = done = k = 0
    while done < n:
        m = min(chunk, n - done)
        sim = simulate(game, tab, n=m, seed=seed + 1000 * k)
        hs = [leg_hits(sim, lg) for lg in legs]
        for i, h in enumerate(hs):
            each_hits[i] += int(h.sum())
        all_hits += int(np.logical_and.reduce(hs).sum()) if hs else 0
        done += m
        k += 1
    each = [h / n for h in each_hits]
    allp = all_hits / n if legs else None
    prod = float(np.prod(each)) if each else None
    lift = (allp / prod) if (prod and allp) else None
    se = (float(np.sqrt(allp * (1 - allp) / n)) / prod) if lift else None
    return {"each": each, "all": allp, "product": prod, "lift": lift, "lift_se": se, "n": n}


def combo_kind(legs, side_of):
    """The graded kind of a parlay, or None. side_of: {pid: side} for
    batters (starters are "_sp_home" / "_sp_away")."""
    if any(lg.get("side", "Over") != "Over" for lg in legs):
        return None
    ts = []
    for lg in legs:
        pid, st = str(lg.get("pid")), lg.get("stat")
        if pid == "_game":
            if st not in ("home_win", "away_win"):
                return None
            ts.append(("W", st.split("_")[0]))
        elif pid.startswith("_sp_"):
            if st != "k":
                return None
            ts.append(("K", pid[4:]))
        elif st == "h" and lg.get("line") == 0.5:
            ts.append(("H", (side_of or {}).get(pid)))
        elif st == "tb" and lg.get("line") == 1.5:
            ts.append(("T", (side_of or {}).get(pid)))
        elif st == "hr" and lg.get("line") == 0.5:
            ts.append(("R", (side_of or {}).get(pid)))
        else:
            return None
    kind = "".join(sorted((t for t, _s in ts), key="HTRKW".index))
    sides = {s for _t, s in ts}
    if None in sides:
        return None
    if kind == "HH" and len(sides) == 2:
        return "HHopp"
    if kind in ("HH", "HHH", "TT", "HW", "RW", "KW") and len(sides) == 1:
        return kind
    return None


def sgp_support(combos, legs, side_of):
    kind = combo_kind(legs, side_of)
    g = (combos or {}).get(kind) if kind else None
    if not g or (g.get("verdict") or {}).get("verdict") != "beats":
        return {"measured": False, "in_range": False, "n": 0, "untested": True, "kind": kind,
                "why": "untested" if not g else "not_beaten"}
    return {"measured": True, "in_range": g["n"] >= STRONG_MIN_COMBOS, "n": g["n"],
            "untested": False, "kind": kind, "why": None}


def sgp_guard(sup, tier):
    from engines import nhl_sim as _h
    return _h.sgp_guard(sup, tier)
