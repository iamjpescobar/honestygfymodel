"""
What every NBA page reads (10-20): the slate through the live injury
check, the model block, and one chance function — so the Tonight page,
the Props board, Trends, the Bet Finder and Live can never disagree
about a number.
"""
from engines import availability as av
from engines import model_math as mm
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
    if ctx.get("vol"):
        bits.append("his team's rotation adding up to 240 minutes")
    return ("IN the number: " + " and ".join(bits) + f" — better than without them on {won} of "
            f"{len(nm.STATS)} stats on last season's unseen games. NOT in it: late scratches "
            f"after the nightly, rest / back-to-backs.")


def tags(row):
    """The player's flags after his name: NEW (no NBA games on file), NEW
    TEAM (his games so far are mostly another team's), ROLE up / down
    (this season's minutes outside his opening projection, beyond noise)."""
    t = ""
    if row.get("new"):
        t += " · NEW"
    if row.get("new_team"):
        t += " · NEW TEAM"
    rd = (row.get("role") or {}).get("dir")
    if rd:
        t += " · ROLE ↑" if rd == "up" else " · ROLE ↓"
    return t


def tags_note(rows, model):
    """One caption for whichever flags are on these rows, or ''."""
    rows = list(rows or [])
    out = []
    if any(r.get("new_team") for r in rows):
        out.append("NEW TEAM = most of his games on file are for another team. His old-team "
                   "games are NOT discounted — measured on last season's 129 mid-season moves, "
                   "cutting them did not beat keeping them; his minutes follow the new team "
                   "within a few games, and his team's rotation must add up to 240 minutes.")
    rc = (model or {}).get("role") or {}
    if any((r.get("role") or {}).get("dir") for r in rows):
        up, dn = rc.get("up") or {}, rc.get("down") or {}
        out.append(f"ROLE ↑ / ↓ = his minutes this season run {nm.ROLE_MIN:g}+ above / below "
                   f"his opening-night projection, beyond noise"
                   + (f" (last season about {100 * up['held']:.0f}% of such rises held over the "
                      f"next 10 games, {100 * dn['held']:.0f}% of drops — so a drop is only "
                      f"partly believed)" if up.get("held") is not None and dn.get("held")
                      is not None else "") + ".")
    return " ".join(out)


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
    lad = (((model or {}).get("ladder") or {}).get(stat) or {})
    if not sup.get("in_range") and lad.get("calibration") and \
            (lad.get("verdict") or {}).get("verdict") == "beats":
        # past his own line's tested range (an alt line, a long shot):
        # the ladder curve graded every rung on unseen games
        from engines import top_plays_board as tpb
        c2 = tpb.calibrate(raw, lad["calibration"])
        if c2 is not None:
            ch, sup = c2, mv.curve_support(raw, lad["calibration"])
    if row.get("new"):
        # projected from preseason only — the model was never tested on
        # players like him, so no call on him goes above THIN
        sup = {"measured": False, "in_range": False, "n": 0, "untested": True}
    if side == "Under":
        return 1 - ch, 1 - raw, sup
    return ch, raw, sup


def long_shots(games, model):
    """Long Shots rows (engines/long_shots shape) from tonight's NBA slate:
    every ladder rung of every projected player, delivered through the
    ladder curve, in the +300..+2000 band and well measured — only stats
    whose ladder BEAT his own hit rate on unseen games."""
    from engines import long_shots as ls
    lad = (model or {}).get("ladder") or {}
    sizes = (model or {}).get("sizes") or {}
    markets, cal = [], {}
    for st, rungs in nm.LADDER.items():
        x = lad.get(st) or {}
        if (x.get("verdict") or {}).get("verdict") != "beats" or not x.get("calibration"):
            continue
        for n in rungs:
            key = f"{st}{n}"
            markets.append((key, f"{n}+ {nm.LADDER_LABEL[st]}", st, n))
            cal[key] = x["calibration"]
    if not markets:
        return []
    rows = []
    for g in games or []:
        if g.get("status") == "final":
            continue
        label = f"{g.get('away_abbr')} @ {g.get('home_abbr')}"
        for side, other in (("away", "home"), ("home", "away")):
            players = []
            for r in g.get(side + "_props") or []:
                if av.is_out(r.get("status")) or r.get("new"):
                    continue                  # a newcomer is untested: never a long shot
                probs = {}
                for key, _lab, st, n in markets:
                    pm = nm.pmf((r.get("mu") or {}).get(st), sizes.get(st))
                    if pm:
                        probs[key] = mm.prob_at_least(pm, n)
                c = (r.get("ctx") or {})
                bits = [f"~{r.get('min', 0):.0f} min"]
                opp = {k: v for k, v in (c.get("opp") or {}).items() if abs(v - 1) >= 0.03}
                if opp:
                    bits.append(f"vs {g.get(other + '_abbr')}: " + ", ".join(
                        f"{k} {100 * (v - 1):+.0f}%" for k, v in opp.items()))
                if any(v - 1 >= 0.02 for v in (c.get("bump") or {}).values()):
                    bits.append("teammate out")
                if av.flag(r):
                    bits.append(f"\u26a0 {av.flag(r)}")
                players.append({"_name": f"{r.get('name')} ({g.get(side + '_abbr')})",
                                "_probs": probs, "_why": r.get("why"), "_signals": " · ".join(bits),
                                "team": g.get(side + "_abbr"), "opp": g.get(other + "_abbr")})
            rows += ls.rows_from_markets(players, markets, cal, label, "NBA")
    return rows


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


def grade(row, stat, side="Over"):
    """The A-F matchup letter (10-26, engines/matchup_grade) for one row's
    stat, for the side picked (an Under flips it), or '—'."""
    from engines import matchup_grade as mg
    g = (row.get("grade") or {}).get(stat)
    if not mg.base(g):
        return "—"
    return mg.flip(g) if side == "Under" else g


def slate_teams(rows):
    """Tonight's teams in game-time order, each once: [(team, label)]
    with the label "BOS vs NYK · 7:30 PM" (10-25: Trends picks a team
    first, then one of his teammates who can play)."""
    seen, out = set(), []
    for r in rows or []:
        t = r.get("team")
        if not t or t in seen:
            continue
        seen.add(t)
        out.append((t, f"{t} vs {r.get('opp') or '?'}" + (f" · {r['time']}" if r.get("time") else "")))
    return out


def team_players(rows, team):
    """(available, ruled_out) for one team. Available = not ruled out on
    the live injury check, most projected minutes first (starters at the
    top); ruled_out = names only, said under the picker so a missing
    player is explained, not silently dropped."""
    from engines import availability as av
    mine = [r for r in rows or [] if r.get("team") == team]
    ok = [r for r in mine if not av.is_out(r.get("status"))]
    ok.sort(key=lambda r: (-(r.get("min") or 0), r.get("name") or ""))
    out = sorted(r.get("name") or "?" for r in mine if av.is_out(r.get("status")))
    return ok, out


def player_label(r):
    from engines import availability as av
    m = av.maybe_label(r.get("status"))
    return f"{r.get('name')} · ~{(r.get('min') or 0):.0f} min" + (f" · {m}" if m else "")


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
