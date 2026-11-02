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

The chance is UNTESTED: the simulator's player links were tested on
same-game parlays of different players, not on one player's stats moving
together, so it reads THIN beside his record until a walk-forward check of
double-doubles beats a baseline. Steals / blocks are not projected — a
double-double built on blocks is not in the chance (it is rare; the
history shows points / rebounds / assists only too).

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
