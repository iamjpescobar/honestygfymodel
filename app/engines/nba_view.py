"""
What every NBA page reads (10-20): the slate through the live injury
check, the model block, and one chance function — so the Tonight page,
the Props board, Trends, the Bet Finder and Live can never disagree
about a number.
"""
from engines import nba_model as nm


def load():
    """(games, model, payload_get) — games through the live injury check."""
    from engines import live_injuries as li
    from engines.slate_guard import payload_field
    games, _d, _cur = li.load_slate_live("nba")
    model = payload_field("nba", "model") or {}
    return games or [], model, (lambda k, default=None: payload_field("nba", k, default))


def calibration(model):
    return nm.calibration(model)


def verdicts(model):
    return {k: ((v.get("verdict") or {}).get("verdict"))
            for k, v in ((model or {}).get("test") or {}).items() if isinstance(v, dict)}


def in_the_number(model):
    """One sentence: what tonight's numbers include and what they don't
    (engines/nba_context). Every NBA page's caption reads it, so the claim
    follows the model the nightly actually shipped."""
    ctx = (model or {}).get("context") or {}
    on_opp = [s for s in nm.BASE if (ctx.get("opp") or {}).get(s)]
    on_out = [s for s in nm.BASE if (ctx.get("out") or {}).get(s)]
    vb = ctx.get("vs_base") or {}
    won = sum(1 for s, _l in nm.STATS if (vb.get(s) or {}).get("verdict") == "beats")
    if not (on_opp or on_out):
        return ("NOT in the number: tonight's opponent and pace, a teammate out (see Next Man "
                "Up), rest.")
    lab = {"pts": "points", "reb": "rebounds", "ast": "assists", "tpm": "3s"}
    bits = []
    if on_opp:
        bits.append("tonight's opponent, defense and pace (" + ", ".join(lab[s] for s in on_opp)
                    + ")")
    if on_out:
        bits.append("teammates ruled OUT (" + ", ".join(lab[s] for s in on_out) + ")")
    return ("IN the number: " + " and ".join(bits) + f" — better than without them on {won} of "
            f"{len(nm.STATS)} stats on last season's unseen games. NOT in it: late scratches "
            f"after the nightly, rest / back-to-backs.")


def chance(row, stat, line, model, side="Over"):
    """(delivered chance, raw chance, support) for one player's line —
    the model's over chance mapped through what calls like it delivered
    on last season's unseen games ("@stat" curve), and how well measured
    it is (the guard reads support)."""
    from engines import model_view as mv
    mu = (row.get("mu") or {}).get(stat)
    raw = nm.over(mu, ((model or {}).get("sizes") or {}).get(stat), line)
    if raw is None:
        return None, None, None
    cal = calibration(model)
    ch, _basis = mv.delivered_over(raw, stat, line, (), cal)
    sup = mv.support_for(raw, stat, line, (), cal)
    if side == "Under":
        return 1 - ch, 1 - raw, sup
    return ch, raw, sup


def his_line(row, stat):
    """A book-like line for him: his last-10 regular-season average at the
    half point (what the model was tested against), else his projection's."""
    vals = [g.get(stat) for g in (row.get("trend") or []) if g.get("tag") != "PRE"
            and g.get(stat) is not None][-10:]
    if vals:
        return nm.half_line(vals)
    mu = (row.get("mu") or {}).get(stat)
    return None if mu is None else int(mu) + 0.5


def all_props(games):
    out = []
    for g in games or []:
        label = f"{g.get('away_abbr')} @ {g.get('home_abbr')}"
        for side, other in (("away", "home"), ("home", "away")):
            for r in g.get(f"{side}_props") or []:
                out.append(dict(r, team=g.get(f"{side}_abbr"), opp=g.get(f"{other}_abbr"),
                                game=label, time=g.get("time_et")))
    return out


# ----------------------------------------------------------------------
# Trend chart (10-20): last season, this season and the preseason, each
# game labelled; preseason marked PRE and left out of every hit rate.
# ----------------------------------------------------------------------
def trend_values(row, stat, include_pre=False):
    """[(label, value, tag)] oldest first."""
    out = []
    for g in row.get("trend") or []:
        if g.get(stat) is None or (g.get("tag") == "PRE" and not include_pre):
            continue
        md = g["date"][5:].replace("-", "/")
        pre = "PRE " if g.get("tag") == "PRE" else ""
        out.append((f"{pre}{md} {g.get('opp') or ''}".strip(), g[stat], g.get("tag")))
    return out


def render_trend(row, stat, line, window="L10", include_pre=False, key="nba_tr"):
    import streamlit as st
    from engines.trend_chart import WINDOW_N, render_trend_bars, window_hit_chips
    reg = [v for _l, v, t in trend_values(row, stat) if t != "PRE"]
    if not reg and not include_pre:
        st.caption("No regular-season games for him yet.")
        return
    window_hit_chips(reg, line, window, windows=("Season", "L25", "L10", "L5"))
    shown = trend_values(row, stat, include_pre)
    n = WINDOW_N.get(window)
    if n:
        # the window counts REGULAR games; preseason ones in that span ride along
        regs = [i for i, (_l, _v, t) in enumerate(shown) if t != "PRE"]
        start = regs[-n] if len(regs) >= n else 0
        shown = shown[start:]
    render_trend_bars([l for l, _v, _t in shown], [v for _l, v, _t in shown],
                      nm.LABEL.get(stat, stat), line)
    seasons = {t for _l, _v, t in shown}
    st.caption("Hit chips count regular-season games only (\"Season\" = every game shipped: this "
               "season, then last season's latest). "
               + ("PRE bars are preseason — reference, never in a hit rate or a projection. "
                  if "PRE" in seasons else "")
               + ("Bars before this season's opener are last season's. " if "LAST" in seasons
                  else ""))
