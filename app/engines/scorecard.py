"""
The Model Scorecard — every model the site grades, one verdict each.

WHY (10-08)
-----------
The records already existed, spread over three files and two pages:
the pick boards in calibration.json (Results), Top Plays in
data/top_plays (Top Plays), the game bets in data/model_picks
(Results, lower down). Nobody could answer "is every model doing its
job right now?" without reading all three and doing the arithmetic,
and a model slipping for two weeks would go unseen until somebody did.

ONE TEST PER KIND OF RECORD, NOT ONE FOR ALL
--------------------------------------------
A record is judged against the number it is supposed to beat, and that
number differs by kind (rule 9, right label):

  vs baseline   A pick board (Daily 13, HR Edge, Player of the Day)
                claims to beat the league rate for its outcome. Its
                target is that measured rate.
  vs promise    Top Plays and the game bets print a chance per pick.
                Their target is the SUM of what they promised: 20 plays
                at 80% should land about 16. Beating that is a bonus;
                landing it is the job; falling short is the alarm.
  no target     A board graded against its own printed number (the
                strikeout board, the WNBA boards) has no league rate to
                beat, and inventing one would be a wrong number under a
                right-looking label. It is listed, never coloured as good
                or bad.

THE VERDICT (the site's convention: two standard errors)
--------------------------------------------------------
  TOO EARLY    under MIN_N graded picks. Nothing is concluded.
  BEATING      z >= 2 above its target.
  ON TARGET    vs promise, inside two standard errors: it is delivering
               what it printed — which is what makes a price trustworthy.
  NO EDGE YET  vs baseline, inside two standard errors: not
               distinguishable from the league rate yet.
  SLIPPING     z <= -2 below its target, over the whole record OR over
               the last RECENT_DAYS days (with at least MIN_N picks in
               that window). The window is what catches a model that
               WAS good and has stopped being good.
  RETIRED      game bets priced by the model-only formula retired on
               10-04. Kept and shown — the record is the record — but
               never judged, so they cannot sink or flatter the formula
               that replaced them.

The recent window is anchored to the record's own newest graded date,
not the wall clock, so a stale feed reads as "nothing new", never as a
model that stopped picking.

Pure — no streamlit, no file reads; the page passes the records in.
"""
from datetime import date, timedelta

MIN_N = 30            # same floor as calibration._edge_verdict / Results
Z = 2.0               # the site's significance convention
RECENT_DAYS = 30

STATUS = {
    # key: (label, theme colour key, sort order — problems first)
    "slipping":    ("SLIPPING", "error", 0),
    "beating":     ("BEATING", "stat_high", 1),
    "on_target":   ("ON TARGET", "accent", 2),
    "no_edge":     ("NO EDGE YET", "warn", 3),
    "too_early":   ("TOO EARLY", "text_faint", 4),
    "no_picks":    ("NO PICKS YET", "text_faint", 5),
    "no_target":   ("NO TARGET", "text_muted", 6),
    "retired":     ("RETIRED", "text_faint", 7),
}


def _d(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def z_vs_rate(hits, n, p0):
    """z of hits/n against a fixed rate p0 (0-1). None if undefined."""
    if not n or p0 is None or not 0 < p0 < 1:
        return None
    se = (p0 * (1 - p0) / n) ** 0.5
    return (hits / n - p0) / se


def z_vs_promise(hits, probs):
    """z of hits against the sum of per-pick promised chances."""
    probs = [p for p in probs if p is not None]
    if not probs:
        return None
    var = sum(p * (1 - p) for p in probs)
    if var <= 0:
        return None
    return (hits - sum(probs)) / var ** 0.5


def verdict(n, z, kind):
    """kind: "baseline" | "promise"."""
    if not n or n < MIN_N or z is None:
        return "too_early"
    if z >= Z:
        return "beating"
    if z <= -Z:
        return "slipping"
    return "on_target" if kind == "promise" else "no_edge"


def _with_recent(status, recent_n, recent_z):
    """A record that is fine overall but has fallen off over the recent
    window is SLIPPING — that is the case the scorecard exists for."""
    if status in ("beating", "on_target", "no_edge") and recent_n >= MIN_N \
            and recent_z is not None and recent_z <= -Z:
        return "slipping", True
    return status, False


def _pct(x):
    return None if x is None else round(100.0 * x, 1)


def _row(model, sport, status, kind, n, hits, rate, target, recent, why,
         units=None, record=None, fell_off=False):
    lab, colour, order = STATUS[status]
    return {"model": model, "sport": sport, "status": status, "label": lab,
            "colour": colour, "order": order, "kind": kind,
            "n": n, "hits": hits, "rate": rate, "target": target,
            "gap": (round(rate - target, 1) if rate is not None and target is not None
                    else None),
            "recent": recent, "units": units, "record": record,
            "fell_off": fell_off, "why": why}


# ----------------------------------------------------------------------
# Pick boards (calibration.summary())
# ----------------------------------------------------------------------
BOARD_SPORT = {"daily13": "MLB", "hr_edge": "MLB", "potd": "MLB", "k_board": "MLB",
               "wnba_props": "WNBA", "wnba_defense": "WNBA"}


def board_rows(summary):
    """summary: engines.calibration.summary() — {board: {"label","hits",
    "total","rate","baseline","days":[{"date","hits","total"}], ...}}."""
    out = []
    for board, s in (summary or {}).items():
        n, hits = s.get("total") or 0, s.get("hits") or 0
        rate, base = s.get("rate"), s.get("baseline")
        label, sport = s.get("label") or board, BOARD_SPORT.get(board, "")
        days = [d for d in (s.get("days") or []) if _d(d.get("date"))]
        last = max((_d(d["date"]) for d in days), default=None)
        rn = rh = 0
        if last:
            cut = last - timedelta(days=RECENT_DAYS - 1)
            for d in days:
                if _d(d["date"]) >= cut:
                    rn += d.get("total") or 0
                    rh += d.get("hits") or 0
        recent = {"n": rn, "hits": rh, "rate": _pct(rh / rn) if rn else None}
        if not n:
            out.append(_row(label, sport, "no_picks", "baseline", 0, 0, None, base, recent,
                            "Nothing graded yet."))
            continue
        if base is None:
            out.append(_row(label, sport, "no_target", "none", n, hits, rate, None, recent,
                            "Graded against its own printed number, not a league rate, so "
                            "there is no fair bar to call this good or bad. Listed, not judged."))
            continue
        p0 = base / 100.0
        z = z_vs_rate(hits, n, p0)
        status = verdict(n, z, "baseline")
        status, fell = _with_recent(status, rn, z_vs_rate(rh, rn, p0))
        out.append(_row(label, sport, status, "baseline", n, hits, rate, base, recent,
                        _why(status, "baseline", n, z, fell, base=base), fell_off=fell))
    return out


# ----------------------------------------------------------------------
# Top Plays (data/top_plays/<sport>.json)
# ----------------------------------------------------------------------
def top_play_rows(plays_by_sport):
    """{"MLB": [play, ...], "NHL": [...]} — each play carries p_cal (the
    delivered chance printed on the page) and a result. A value may also
    be (sport, plays), with the key as the display name — the other
    records kept in the same shape (NHL Player of the Day, multi-goal
    watch)."""
    out = []
    for key, val in (plays_by_sport or {}).items():
        if isinstance(val, tuple):
            (sport, plays), name = val, key
        else:
            sport, plays, name = key, val, f"{key} Top Plays"
        g = [p for p in plays or [] if p.get("result") in ("hit", "miss")
             and (p.get("p_cal") if p.get("p_cal") is not None else p.get("p")) is not None]
        if not g:
            out.append(_row(name, sport, "no_picks", "promise", 0, 0, None, None,
                            {"n": 0, "hits": 0, "rate": None, "promised": None},
                            "Nothing graded yet."))
            continue

        def prob(p):
            return p["p_cal"] if p.get("p_cal") is not None else p["p"]
        n, hits = len(g), sum(1 for p in g if p["result"] == "hit")
        promised = [prob(p) for p in g]
        last = max((_d(p.get("date")) for p in g if _d(p.get("date"))), default=None)
        rg = [p for p in g if last and _d(p.get("date"))
              and _d(p["date"]) >= last - timedelta(days=RECENT_DAYS - 1)]
        rh = sum(1 for p in rg if p["result"] == "hit")
        recent = {"n": len(rg), "hits": rh, "rate": _pct(rh / len(rg)) if rg else None,
                  "promised": _pct(sum(prob(p) for p in rg) / len(rg)) if rg else None}
        z = z_vs_promise(hits, promised)
        status = verdict(n, z, "promise")
        status, fell = _with_recent(status, len(rg), z_vs_promise(rh, [prob(p) for p in rg]))
        out.append(_row(name, sport, status, "promise", n, hits, _pct(hits / n),
                        _pct(sum(promised) / n), recent,
                        _why(status, "promise", n, z, fell, expected=sum(promised), hits=hits),
                        fell_off=fell))
    return out


# ----------------------------------------------------------------------
# Game bets (data/model_picks/<sport>.json)
# ----------------------------------------------------------------------
def _units(rows):
    return round(sum(r.get("units") or 0 for r in rows), 2)


def game_pick_rows(picks_by_sport):
    """{"NFL": [pick, ...], ...}. Market-anchored picks are judged
    against the chance they were logged at; model-only picks (the formula
    retired 10-04) are listed as RETIRED and never judged."""
    out = []
    for sport, picks in (picks_by_sport or {}).items():
        graded = [p for p in picks or [] if p.get("result") in ("win", "loss", "push")]
        cur = [p for p in graded if p.get("formula") == "market-anchored"]
        old = [p for p in graded if p.get("formula") != "market-anchored"]
        pending = sum(1 for p in picks or [] if not p.get("result")
                      and p.get("formula") == "market-anchored")
        name = f"{sport} game bets"
        decided = [p for p in cur if p["result"] != "push"]
        if not decided:
            why = ("No bet has cleared the bar under the current formula yet. The market's "
                   "price stands until this model beats the market on past games, so a "
                   "bet only appears when the model has earned a say. That is the "
                   "protection working, not a broken page.")
            if pending:
                why = f"{pending} logged and waiting on results. " + why
            out.append(_row(name, sport, "no_picks", "promise", 0, 0, None, None,
                            {"n": 0, "hits": 0, "rate": None}, why,
                            units=_units(cur) if cur else None,
                            record=_wlp(cur) if cur else None))
        else:
            n, w = len(decided), sum(1 for p in decided if p["result"] == "win")
            probs = [p.get("p") for p in decided]
            z = z_vs_promise(w, probs)
            status = verdict(n, z, "promise")
            out.append(_row(name, sport, status, "promise", n, w, _pct(w / n),
                            _pct(sum(probs) / n),
                            {"n": 0, "hits": 0, "rate": None},
                            _why(status, "promise", n, z, False, expected=sum(probs), hits=w),
                            units=_units(cur), record=_wlp(cur)))
        if old:
            od = [p for p in old if p["result"] != "push"]
            ow = sum(1 for p in od if p["result"] == "win")
            out.append(_row(f"{sport} game bets (old formula)", sport, "retired", "none",
                            len(od), ow, _pct(ow / len(od)) if od else None, None,
                            {"n": 0, "hits": 0, "rate": None},
                            "Priced on the model alone, before the 10-04 fix that anchors "
                            "every bet to the market. Kept for the record, not counted "
                            "against or for any model running today.",
                            units=_units(old), record=_wlp(old)))
    return out


def _wlp(rows):
    w = sum(1 for r in rows if r["result"] == "win")
    lo = sum(1 for r in rows if r["result"] == "loss")
    pu = sum(1 for r in rows if r["result"] == "push")
    return f"{w}-{lo}-{pu}"


# ----------------------------------------------------------------------
# Plain-language reason
# ----------------------------------------------------------------------
def _why(status, kind, n, z, fell_off, base=None, expected=None, hits=None):
    zs = "" if z is None else f" (z {z:+.1f})"
    if status == "too_early":
        return (f"{n} graded so far; it takes {MIN_N} before any call is made. "
                f"Keep reading the picks, don't judge the model yet.")
    if fell_off:
        return (f"Fine over the whole record, but the last {RECENT_DAYS} days fell more than "
                f"two standard errors short. Lean on it less until it recovers; don't "
                f"retune it after one bad stretch.")
    if kind == "baseline":
        if status == "beating":
            return (f"Hitting above the {base:.1f}% league rate by more than luck explains"
                    f"{zs}. This is the model doing its job.")
        if status == "slipping":
            return (f"Below the {base:.1f}% league rate by more than luck explains{zs}. "
                    f"Its picks are worse than an average player right now.")
        return (f"Not separable from the {base:.1f}% league rate yet{zs}. Could be an edge, "
                f"could be nothing; more picks will tell.")
    exp = "" if expected is None else f" {hits} landed vs {expected:.1f} promised."
    if status == "beating":
        return f"Landing more than it promised{zs}.{exp} Its chances are, if anything, modest."
    if status == "slipping":
        return (f"Landing fewer than it promised{zs}.{exp} Its printed chances are running "
                f"too high; trust them less until this recovers.")
    return (f"Landing what it promised{zs}.{exp} When it says 70%, it hits about 70%, so the "
            f"chance it prints is safe to compare against your book's price.")


def all_rows(summary=None, plays_by_sport=None, picks_by_sport=None):
    rows = board_rows(summary) + top_play_rows(plays_by_sport) + game_pick_rows(picks_by_sport)
    return sorted(rows, key=lambda r: (r["order"], -(r["n"] or 0)))


def headline(rows):
    """{"judged","beating","on_target","no_edge","slipping","early"} over
    rows that can be judged (not retired / no target / no picks)."""
    c = {k: sum(1 for r in rows if r["status"] == k) for k in STATUS}
    return {"beating": c["beating"], "on_target": c["on_target"], "no_edge": c["no_edge"],
            "slipping": c["slipping"], "early": c["too_early"],
            "judged": c["beating"] + c["on_target"] + c["no_edge"] + c["slipping"]}
