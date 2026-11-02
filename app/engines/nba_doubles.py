"""
NBA double-doubles and triple-doubles (11-02) — NBA Trends' "Double-double
/ Triple-double" card.

Izzy (11-02): "how can I research double doubles and triple doubles?"

  history   from each shipped game (the trend rows): how many of points /
            rebounds / assists reached 10 — a double-double is 2+, a
            triple-double 3. Hit chips per window (L5 / L10 / L20 / Season /
            H2H) count games where it HAPPENED, never two hit rates
            multiplied (his points and rebounds rise together on big-minute
            nights).
  chance    the NBA simulator (engines/nba_sim) plays tonight's game out
            with his projected points / rebounds / assists drawn TOGETHER
            through minutes, blowouts and pace; the share of simulated
            games with 2+ (3+) of them at 10+.

MEASURED 11-02 on last season's final 45 days (6,652 player-games the
model had not seen; walk-forward projections, nba_sim.simulate per player,
fit on the first 23 days, scored on the last 22):
  double-double happened 7.95%; the simulator said 6.9% (low, most in its
  under-2% games: 0.5% said, 1.8% happened) and scored no better than his
  own record (last 30 games, shrunk 10 games toward the league's 7.95%).
  The BLEND  logit p = 0.3 + 0.3 logit(sim) + 0.8 logit(record)  beat both
  on the unseen half: log loss 0.2194 vs sim 0.2325 / record 0.2242; paired
  by date (Brier) z 2.94 vs the sim, 3.01 vs the record. -> dd_chance().
  triple-double: 45 happened, the simulator said 23 — about HALF. Too few
  to fit a correction; shown as the simulator's number, read as a floor,
  THIN.
The simulator draws one player's stats together only through minutes,
blowouts and pace — it scored the same as treating them as independent —
so his record carries what it misses. Steals / blocks are not projected — a
double-double built on blocks is not in the chance (the history shows
points / rebounds / assists only too).

Pure — no streamlit.
"""
import numpy as np

CATS = (("pts", "PTS"), ("reb", "REB"), ("ast", "AST"))
DD_LINE, TD_LINE = 1.5, 2.5      # categories in double figures: > 1.5 = 2+, > 2.5 = 3


def game_cats(g):
    """(number of categories at 10+, "PTS+REB") or (None, None) when a
    stat is missing (missing is never zero)."""
    vals = [(lab, g.get(k)) for k, lab in CATS]
    if any(v is None for _l, v in vals):
        return None, None
    hit = [lab for lab, v in vals if v >= 10]
    return len(hit), "+".join(hit)


def history(row, include_pre=False):
    """[(label, n_cats, which, tag, opp)] oldest first."""
    out = []
    for g in row.get("trend") or []:
        if g.get("tag") == "PRE" and not include_pre:
            continue
        n, which = game_cats(g)
        if n is None:
            continue
        md = g["date"][5:].replace("-", "/")
        pre = "PRE " if g.get("tag") == "PRE" else ""
        out.append((f"{pre}{md} {g.get('opp') or ''}".strip(), n, which, g.get("tag"),
                    g.get("opp")))
    return out


def how_he_got_them(hist, need=2):
    """{"PTS+REB": games, ...} among the games with `need`+ categories."""
    out = {}
    for _l, n, which, tag, _o in hist:
        if tag != "PRE" and n >= need:
            out[which] = out.get(which, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def sim_chance(stats):
    """{"dd", "td"} from one player's simulated arrays {stat: int array}."""
    arrs = [np.asarray(stats.get(k)) for k, _l in CATS if stats.get(k) is not None]
    if len(arrs) < 3:
        return None
    n10 = sum((a >= 10).astype(int) for a in arrs)
    return {"dd": float((n10 >= 2).mean()), "td": float((n10 >= 3).mean())}


# measured 11-02 (see the docstring) — re-measure before changing
DD_A, DD_B, DD_C = 0.3, 0.3, 0.8
DD_K = 10                 # games of the league rate his record is shrunk with
DD_LEAGUE = 0.0795        # double-doubles per player-game, last season's test window
DD_RECORD_N = 30          # his last 30 regular games (what the trend ships)


def _logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return float(np.log(p / (1 - p)))


def record_rate(hist):
    """(his double-double rate shrunk toward the league, games) over his
    last DD_RECORD_N regular games."""
    reg = [n for _l, n, _w, t, _o in hist if t != "PRE"][-DD_RECORD_N:]
    return (sum(1 for n in reg if n >= 2) + DD_K * DD_LEAGUE) / (len(reg) + DD_K), len(reg)


def dd_chance(sim_dd, hist):
    """The tested double-double chance: the simulator's and his record's,
    blended on the logit scale with the measured weights."""
    if sim_dd is None:
        return None
    rec, _n = record_rate(hist)
    x = DD_A + DD_B * _logit(sim_dd) + DD_C * _logit(rec)
    return float(1 / (1 + np.exp(-x)))
