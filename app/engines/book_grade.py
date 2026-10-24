"""
Site vs DraftKings (10-24) — step 3 of the book-lines work: does the
site's chance beat the book's, market by market?

1. CAPTURE (every nightly run, right after the book's lines are saved,
   book_props_snapshot): for every player and stat the book has a line
   for, the SITE's chance of the over at that line — the delivered
   chance, exactly as the Bet Finder prices it (bet_finder.chance_at on
   the same pmfs and the same calibration curves) — saved beside the
   book's prices in the day file (entry["ours"]). The pages work their
   chances out on the fly and never kept them: without this, a night
   could never be graded.
2. GRADE (every run, for games that are final): the box score from ESPN's
   summary; each captured line -> did the over hit; the book's chance =
   its two prices with the cut removed (over / (over + under), break-
   even chances) — graded only where the book priced BOTH sides (a
   one-sided ladder price carries the whole cut on one side and would
   flatter the site). Missing is never zero: a player with no line in
   the box (did not play) is not graded.
3. SCORECARD: per league and stat — n, the site's Brier vs the book's,
   a paired verdict (beats / thin / fails, model_math.paired_verdict),
   and the flagged plays: where the site's chance was 3+ points above
   the book's (the side it liked), how often it hit and the profit at
   the book's own price, 1 unit a play.

Pure apart from fetch functions passed in.
"""
from engines import book_props as bp
from engines import model_math as mm

EDGE_FLAG = 0.03
MAX_RUNGS = 6
# DraftKings' cut on a ONE-SIDED price (a ladder rung, "N or more"):
# MEASURED 10-23 / 10-24 — a rung at a total's own line is priced at the
# total's over, whose break-even chance over the de-vigged chance is the
# total's overround: NHL 1.072 (IQR 1.067-1.077, n 1,281), NBA 1.068
# (1.063-1.072, n 1,756). Used ONLY where the book posts no two-sided
# price for that player and stat (the NFL: its main totals come with no
# price) — graded under "<stat>*" so it never mixes with the clean grade;
# and only for rungs priced 15-85% (the cut is not proportional on long
# shots).
LADDER_OVERROUND = 1.07


# ----------------------------------------------------------------------
# 1. capture
# ----------------------------------------------------------------------
def rows_nhl(payload):
    """[(event_id, row, markets, calibration, league key)] — the NHL Bet
    Finder's skater and goalie rows from games.json."""
    from engines import model_view as mv
    from engines import nhl_model as nm
    model = (payload or {}).get("model") or {}
    sog_disp = (model.get("skater_priors") or {}).get("sog_dispersion")
    shot_disp = (model.get("shots") or {}).get("dispersion")
    cal = mv.calibration_map(model.get("props_validation") or {}, nm.MARKETS)
    cal_sv = mv.calibration_map(model.get("saves_validation") or {}, nm.SAVE_MARKETS)
    out = []
    for g in (payload or {}).get("games") or []:
        if g.get("status") == "final":
            continue
        eid = str(g.get("event_id"))
        for side in ("away", "home"):
            for p in g.get(f"{side}_props") or []:
                out.append((eid, {"_pid": p.get("pid"),
                                  "_pmfs": nm.skater_pmfs(p.get("mu"), sog_disp)},
                            nm.MARKETS, cal, "nhl"))
            for gp in g.get(f"{side}_goalie_props") or []:
                pm = nm.saves_pmf(gp.get("exp_sa"), shot_disp, gp.get("sv_pct"))
                if pm:
                    out.append((eid, {"_pid": gp.get("pid"), "_pmfs": {"sv": pm}},
                                nm.SAVE_MARKETS, cal_sv, "nhl"))
    return out


def rows_nba(payload):
    from engines import nba_model as nm
    model = (payload or {}).get("model") or {}
    cal = nm.calibration(model)
    out = []
    for g in (payload or {}).get("games") or []:
        if g.get("status") == "final":
            continue
        for side in ("away", "home"):
            for r in g.get(f"{side}_props") or []:
                out.append((str(g.get("event_id")),
                            {"_pid": r.get("pid"),
                             "_pmfs": nm.player_pmfs(r.get("mu"), model.get("sizes"))},
                            (), cal, "nba"))
    return out


def rows_nfl(payload):
    from engines import model_view as mv
    from engines import nfl_quarters as nq
    league = (payload or {}).get("league") or {}
    cal = mv.nfl_calibration(league)
    q = ((payload or {}).get("sim") or {}).get("quarters") or {}
    qcal = {f"@{k}": x["calibration"] for k, x in (q.get("test") or {}).items()
            if (x or {}).get("calibration")}
    out = []
    for g in (payload or {}).get("games") or []:
        if g.get("status") == "final":
            continue
        eid = str(g.get("event_id"))
        for r in mv.nfl_game_prop_rows(g, league, (payload or {}).get("dvp")):
            if not r.get("_pmfs"):
                continue
            out.append((eid, {"_pid": r.get("_pid"), "_pmfs": r["_pmfs"]}, (), cal, "nfl"))
            if q.get("model"):
                pm = {}
                for per, _l, _i in nq.PERIODS:
                    for st, _sl in nq.Q_STATS:
                        mu = (r.get("_means") or {}).get(st)
                        x = nq.pmf(q["model"], per, st, mu) if mu else None
                        if x:
                            pm[nq.key(per, st)] = x
                if pm:
                    out.append((eid, {"_pid": r.get("_pid"), "_pmfs": pm}, (), qcal, "nfl"))
    return out


ROWS = {"nhl": rows_nhl, "nba": rows_nba, "nfl": rows_nfl}


def capture(league, payload, bd):
    """{event_id: [[pid, stat, line, raw over, delivered over], ...]} for
    every line the book has (its main line + up to MAX_RUNGS ladder rungs)."""
    from engines import bet_finder as bf
    fn = ROWS.get(league)
    if not fn or not bd:
        return {}
    out = {}
    for eid, row, markets, cal, lg in fn(payload):
        pid = row.get("_pid")
        if pid is None:
            continue
        for stat in row["_pmfs"]:
            bk = bp.lookup(bd, lg, pid, stat)
            if not bk:
                continue
            lines = [bk["line"]] + sorted(bk.get("ladder") or {}, key=lambda x: abs(
                x - bk["line"]))[:MAX_RUNGS]
            seen = set()
            for ln in lines:
                if ln is None or ln in seen:
                    continue
                seen.add(ln)
                ch, raw, _b = bf.chance_at(row, stat, ln, "Over", markets, cal)
                if ch is None:
                    continue
                out.setdefault(eid, []).append([str(pid), stat, float(ln), round(raw, 4),
                                                round(ch, 4)])
    return out


# ----------------------------------------------------------------------
# 2. grade
# ----------------------------------------------------------------------
def actuals_nhl(summary, eid):
    import nhl_precompute as nhp
    sk, gk = {}, {}
    nhp.parse_summary(summary, eid, "", sk, gk)
    out = {}
    for pid, r in sk.items():
        ln = (r.get("games") or {}).get(str(eid)) or {}
        out[pid] = {k: ln.get(k) for k in ("sog", "g", "a", "pts")}
    for pid, r in gk.items():
        ln = (r.get("games") or {}).get(str(eid)) or {}
        out[pid] = {"sv": ln.get("sv")}
    return out


def actuals_nba(summary, eid):
    from engines import nba_box
    out = {}
    for pid, ln in nba_box.parse(summary).items():
        v = {k: ln.get(k) for k in ("pts", "reb", "ast", "tpm")}
        if None not in (v["pts"], v["reb"], v["ast"]):
            v.update(pra=v["pts"] + v["reb"] + v["ast"], pr=v["pts"] + v["reb"],
                     pa=v["pts"] + v["ast"], ra=v["reb"] + v["ast"])
        out[str(pid)] = v
    return out


def actuals_nfl(summary, eid):
    import nfl_precompute as pc
    import nfl_prop_check as npc
    from engines import nfl_quarters as nq
    logs = {}
    pc.parse_summary_final(summary, eid, "", 0, logs)
    out = {}
    for pid, rec in logs.items():
        g = (rec.get("games") or {}).get(str(eid))
        if g:
            out[str(pid)] = dict(npc.game_values(g))
    qs = nq.parse(summary)
    for pid, st in (qs.get("players") or {}).items():
        box = out.get(str(pid))
        if box is None:
            continue
        for s, arr in st.items():
            # a quarter line only when his quarters add up to his box (the
            # model's own rule: missing is never zero)
            if box.get(s) is not None and abs(sum(arr) - box[s]) <= (1 if s.endswith("yds")
                                                                    else 0):
                for per, _l, _i in nq.PERIODS:
                    box[nq.key(per, s)] = nq._span(arr, per)
    return out


ACTUALS = {"nhl": actuals_nhl, "nba": actuals_nba, "nfl": actuals_nfl}


def devig(over, under):
    """The book's over chance with its cut removed (both sides needed)."""
    io, iu = bp.implied(over), bp.implied(under)
    if io is None or iu is None or io + iu <= 0:
        return None
    return io / (io + iu)


def grade_event(entry, actual):
    """[[pid, stat, line, ours, book, y, over price, under price]] for one
    finished event's captured rows that the book priced on both sides."""
    if not entry or not entry.get("ours"):
        return []
    bd = bp.board([{"x": entry}])
    out = []
    for pid, stat, line, _raw, ours in entry["ours"]:
        a = (actual.get(str(pid)) or {}).get(stat)
        if a is None:
            continue
        lg_markets = [lg for lg, m in bp.MARKETS.items() if stat in m]
        bk = None
        for lg in lg_markets:
            bk = bp.lookup(bd, lg, pid, stat)
            if bk:
                break
        if not bk:
            continue
        o, u = bp.price_at(bk, line, "Over"), bp.price_at(bk, line, "Under")
        book, key = devig(o, u), stat
        two_sided_main = bk.get("over") is not None and bk.get("under") is not None
        if book is None and o is not None and not two_sided_main:
            io = bp.implied(o)
            if 0.15 <= io <= 0.85:
                book, key = io / LADDER_OVERROUND, stat + "*"
        if book is None:
            continue
        out.append([str(pid), key, line, ours, round(book, 4), 1 if a > line else 0, o, u])
    return out


# ----------------------------------------------------------------------
# 3. scorecard
# ----------------------------------------------------------------------
def _profit(price, won):
    if price is None:
        return 0.0
    return (price / 100.0 if price > 0 else 100.0 / -price) if won else -1.0


def scorecard(graded):
    """{stat: {"n", "brier_site", "brier_book", "verdict", "flagged": {"n",
    "hits", "units", "roi"}}} from graded rows [date, eid, pid, stat, line,
    ours, book, y, over, under]."""
    by = {}
    for r in graded or []:
        by.setdefault(r[3], []).append(r)
    out = {}
    for st, rows in sorted(by.items()):
        m = [(r[5], r[7]) for r in rows]
        b = [(r[6], r[7]) for r in rows]
        sm, sb = mm.score_predictions(m), mm.score_predictions(b)
        fl = {"n": 0, "hits": 0, "units": 0.0}
        for r in rows:
            ours, book, y, o, u = r[5], r[6], r[7], r[8], r[9]
            if ours - book >= EDGE_FLAG:
                won, price = y == 1, o
            elif book - ours >= EDGE_FLAG and u is not None:
                won, price = y == 0, u
            else:
                continue
            fl["n"] += 1
            fl["hits"] += int(won)
            fl["units"] += _profit(price, won)
        fl["units"] = round(fl["units"], 2)
        fl["roi"] = round(fl["units"] / fl["n"], 3) if fl["n"] else None
        out[st] = {"n": sm["n"], "brier_site": sm["brier"], "brier_book": sb["brier"],
                   "verdict": mm.paired_verdict([(p - y) ** 2 for p, y in m],
                                                [(q - y) ** 2 for q, y in b]),
                   "flagged": fl}
    return out


# ----------------------------------------------------------------------
# 4. what the pages say (decided BEFORE any grade was seen, 10-24): a
# market needs MIN_GRADED graded lines before it gets a verdict; then
# "beats" = the paired verdict says the site's chances beat the book's
# de-vigged ones; anything else = "no edge proven", and the Bet Finder
# caps that market's calls at THIN.
# ----------------------------------------------------------------------
MIN_GRADED = 300


def load_scorecard(roots):
    import json
    from pathlib import Path
    for root in roots:
        p = Path(root) / "props" / "scorecard.json"
        if p.exists():
            try:
                return json.loads(p.read_text())
            except Exception:  # noqa: BLE001
                continue
    return None


def market_status(card, league, stat):
    """{"status": "beats" | "no_edge" | "grading", "n", "z", "key"} for one
    league / stat (the two-sided grade, else the one-sided "stat*")."""
    sc = ((card or {}).get("leagues") or {}).get(league) or {}
    key = stat if stat in sc else (stat + "*" if stat + "*" in sc else None)
    x = sc.get(key) if key else None
    if not x:
        return {"status": "grading", "n": 0, "z": None, "key": stat}
    v = (x.get("verdict") or {})
    if (x.get("n") or 0) < MIN_GRADED:
        st = "grading"
    else:
        st = "beats" if v.get("verdict") == "beats" else "no_edge"
    return {"status": st, "n": x.get("n") or 0, "z": v.get("z"), "key": key}
