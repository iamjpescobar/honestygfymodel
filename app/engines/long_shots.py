"""
Long Shots (10-11) — every player whose TESTED chance puts him between
+300 and +2000, with the price he is worth.

WHY
---
Judd Caulfield, 10-09: the model had him at 16% to score, the book hung
+1200 (7.7%), and he scored. Books price depth players lazily — the
public bets the stars — and the long-shot end of the board is where a
lazy price is worth the most. Nothing here can see a book's price (no
paid feed), so the page does the other half: every long shot the model
can stand behind, ranked, with "worth it at" in big type and a box for
the reader's price that answers BET / CHECK / SKIP through the same
guard as every other call (model_view.guarded_tier).

ONLY WELL-MEASURED CHANCES
--------------------------
A long shot is where a model is easiest to fool: a 4% call that is really
2% looks like a gift at +1500. So a row is listed only when
  - its market is TESTED (a calibration curve exists), and
  - the raw call sits inside the range that curve was graded on, with at
    least model_view.STRONG_MIN_N calls in its band (curve_support).
The chance shown is the DELIVERED one (what calls like it hit on games the
model had not seen) — for 2+ goals that pulls a 12% call down to ~7%.

Band: +300 .. +2000 = a delivered chance of 1/21 .. 1/4.

Pure — no streamlit, no requests.
"""
from engines import availability as av
from engines import model_math as mm

LO_P, HI_P = 1.0 / 21.0, 0.25        # +2000 .. +300


def in_band(p):
    return p is not None and LO_P <= p <= HI_P


def rows_from_markets(players, markets, calibration, game, sport):
    """players: [{"_name", "_probs": {market_key: raw}, "_why", "_signals",
    "team", "opp"}]; markets: ((key, label, stat, at_least), ...).
    -> long-shot candidates (delivered, in band, well measured)."""
    from engines import model_view as mv
    out = []
    for p in players or []:
        probs = p.get("_probs") or {}
        for key, label, stat, n in markets or ():
            raw = probs.get(key)
            if raw is None:
                continue
            line = n - 0.5
            ch, basis = mv.delivered_over(raw, stat, line, markets, calibration)
            if basis == "raw" or not in_band(ch):
                continue
            sup = mv.support_for(raw, stat, line, markets, calibration)
            if not sup["measured"] or not sup["in_range"] or sup["n"] < mv.STRONG_MIN_N:
                continue
            out.append({"sport": sport, "game": game, "player": p.get("_name"),
                        "team": p.get("team"), "opp": p.get("opp"), "market": label,
                        "key": key, "chance": ch, "raw": raw, "support": sup,
                        "worth": mm.fair_american(ch), "signals": p.get("_signals") or "",
                        "why": p.get("_why")})
    return out


def row_from_chance(name, label, chance, raw, bins, game, sport, team=None, opp=None,
                    signals="", why=None):
    """One long shot from a delivered chance and its curve (NFL TD)."""
    from engines import model_view as mv
    if not in_band(chance):
        return None
    sup = mv.curve_support(raw, bins)
    if not sup["measured"] or not sup["in_range"] or sup["n"] < mv.STRONG_MIN_N:
        return None
    return {"sport": sport, "game": game, "player": name, "team": team, "opp": opp,
            "market": label, "key": label, "chance": chance, "raw": raw, "support": sup,
            "worth": mm.fair_american(chance), "signals": signals, "why": why}


def rank(rows):
    """Most likely first within the band — the long shots the model is
    surest about lead; the payout never ranks a row."""
    return sorted(rows or [], key=lambda r: -r["chance"])


# ----------------------------------------------------------------------
# Signals: why a long shot is live tonight, in a few words
# ----------------------------------------------------------------------
def nhl_signals(p, env=None, goalie_sv=None, league_sv=None):
    bits = []
    ice = p.get("ice") or {}
    if ice.get("recent") and ice.get("base") and ice["recent"] >= 1.05 * ice["base"]:
        bits.append(f"ice time up ({ice['recent']:.1f} vs {ice['base']:.1f})")
    pp = p.get("pp") or {}
    if pp.get("unit") == "PP1":
        bits.append("PP1")
    if env and env.get("goal_ratio") and env["goal_ratio"] >= 1.05:
        bits.append(f"team goals +{100 * (env['goal_ratio'] - 1):.0f}% tonight")
    if goalie_sv and league_sv and goalie_sv < league_sv - 0.003:
        bits.append(f"weak goalie (.{round(goalie_sv * 1000):03d})")
    return " · ".join(bits)


def nhl_players(g, model):
    """Long-shot inputs for both sides of one NHL game."""
    from engines import edge_boards as eb
    league_sv = ((model or {}).get("save_prior") or {}).get("mean")
    out = []
    for side, other in (("away", "home"), ("home", "away")):
        abbr = g.get(f"{side}_abbr") or g.get(side)
        opp = g.get(f"{other}_abbr") or g.get(other)
        ogp = [x for x in g.get(f"{other}_goalie_props") or [] if x.get("sv_pct") is not None]
        sg = eb.likely_starter(ogp)
        sv = (sg or {}).get("sv_pct") if sg else (
            sum(x["sv_pct"] for x in ogp[:2]) / len(ogp[:2]) if ogp else None)
        env = g.get(f"{side}_env") or {}
        for p in g.get(f"{side}_props") or []:
            if av.is_out(p.get("status")):
                continue
            sig = nhl_signals(p, env, sv, league_sv)
            mi = next((m for m in p.get("milestones") or [] if m.get("short")), None)
            if mi:
                sig = (f"{sig} · " if sig else "") + f"\U0001F3C1 {mi['short']}"
            fl = av.flag(p)
            if fl:
                sig = f"\u26a0 {fl}" + (f" · {sig}" if sig else "")
            out.append({"_name": f"{p.get('name')} ({abbr})", "_probs": p.get("probs") or {},
                        "_why": p.get("why"), "team": abbr, "opp": opp,
                        "_signals": sig})
    return out
