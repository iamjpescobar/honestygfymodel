"""
The nightly half of the milestone watch (10-14, engines/milestones):
keep data/<sport>/career_prior.json filled for tonight's players, hang
each player's within-reach milestones on his row, and list the marks
reached in the last few days.

NHL and NFL only — MLB's career line is read live by the page (one stats
API call per lineup), so it needs nothing here.

A failure here costs the watch, never the slate: both nightlies call it
inside their own try.
"""
import json
import time
from datetime import timedelta
from pathlib import Path

from engines import espn_feed as ef
from engines import milestones as ms

ROOT = Path(__file__).resolve().parent
CAREER_FILE = "career_prior.json"
# New players fetched per night, per sport. ~25 minutes of budget at most
# on the first night; after that only call-ups and trades are new.
FETCH_CAP = 400
HAPPENED_DAYS = {"nhl": 3, "nfl": 8}


def career_url(league, pid):
    sport, lg = ef._paths(league)
    return (f"https://site.web.api.espn.com/apis/common/v3/sports/{sport}/{lg}/"
            f"athletes/{pid}/stats")


def path_for(league, root=None):
    return Path(root or ROOT / "data") / league / CAREER_FILE


def load(league, start_year, root=None):
    p = path_for(league, root)
    try:
        data = json.loads(p.read_text())
    except Exception:  # noqa: BLE001 — no file yet is the first night
        data = {}
    return ms.PriorCareer(data, start_year)


def _minus(a, b):
    return {k: v - (b or {}).get(k, 0) for k, v in (a or {}).items()}


def run(league, holders, season_of, last_game, today, root=None, fetch=None,
        cap=FETCH_CAP, pause=0.15, first_probe=None, also=None):
    """holders: [(pid, name, row)] — each row gets "milestones": [items]
    (with "short"); season_of: {pid: this season's totals}; last_game:
    {pid: (date_str, that game's totals)}; also: [(pid, name)] fetched too
    (who played lately, so a mark reached last night is seen even when he
    is not on tonight's slate). Returns the verify dict,
    including "happened": [{date, pid, name, scope, stat, mark, what}]."""
    start = ms.season_start_year(today, league)
    pc = load(league, start, root)
    names = {str(pid): name for pid, name in also or []}
    names.update({str(pid): name for pid, name, _r in holders})
    get = fetch or (lambda pid: ef.get_json(career_url(league, pid)))
    probe = {}

    def _get(pid):
        data = get(pid)
        if not probe and isinstance(data, dict):
            cats = data.get("categories") or []
            probe.update({"pid": pid, "keys": sorted(data)[:12],
                          "categories": [str((c or {}).get("name")) for c in cats][:8],
                          "first_names": list(((cats or [{}])[0] or {}).get("names") or [])[:12],
                          "season_rows": [ms.season_label(r) for r in
                                          ((cats or [{}])[0] or {}).get("statistics") or []][-4:]})
        return data

    want = [pid for pid, _n, _r in holders]
    want += [pid for pid, _n in also or [] if pid not in set(want)]
    pc.fill(want, names, _get, league, cap=cap,
            sleep=(lambda: time.sleep(pause)) if pause else None)
    # Written only when something new was read: a run that fetched no one
    # (no network, a test calling main) leaves the committed file alone.
    if not pc.suspect and pc.fetched:
        p = path_for(league, root)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(pc.to_json(), separators=(",", ":")))

    n_watch = 0
    for pid, _name, row in holders:
        prior = pc.prior(pid)
        season = season_of.get(str(pid))
        if season is None:
            continue
        career = ms.add(prior, season) if prior is not None else None
        items = ms.needs(career, season, league)
        for it in items:
            it["short"] = ms.short(it)
        if items:
            row["milestones"] = items
            n_watch += 1

    since = (today - timedelta(days=HAPPENED_DAYS.get(league, 3))).isoformat()
    happened = []
    for pid, (d, line) in (last_game or {}).items():
        if not d or d < since:
            continue
        prior = pc.prior(pid)
        season = season_of.get(str(pid))
        if season is None:
            continue
        before_s = _minus(season, line)
        after = {"career": ms.add(prior, season) if prior is not None else {}, "season": season}
        before = {"career": ms.add(prior, before_s) if prior is not None else {},
                  "season": before_s}
        for scope, stat, mark, what in ms.crossed(before, after, league):
            happened.append({"date": d, "pid": str(pid),
                             "name": (pc.players.get(str(pid)) or {}).get("name")
                             or names.get(str(pid)),
                             "scope": scope, "stat": stat, "mark": mark, "what": what})
    happened.sort(key=lambda x: (x["date"], x["mark"]), reverse=True)
    if first_probe is not None:
        first_probe.update(probe)
    return {"known": len(pc.players), "fetched": pc.fetched, "failed": pc.failed,
            "suspect": pc.suspect, "watch": n_watch, "happened": happened, "probe": probe}


def verify_line(league, res):
    pr = res.get("probe") or {}
    head = (f"  [verify] {league.upper()} milestones: {res['known']} careers on file "
            f"({res['fetched']} fetched tonight, {res['failed']} unreadable); "
            f"{res['watch']} players within reach; {len(res['happened'])} marks reached lately")
    if res.get("suspect"):
        head += (" -> FEED SHAPE SUSPECT (too many players with no earlier season): "
                 "tonight's fetch NOT saved")
    if pr:
        head += (f"\n  [verify] {league.upper()} career feed probe pid {pr.get('pid')}: "
                 f"keys {pr.get('keys')} categories {pr.get('categories')} "
                 f"names {pr.get('first_names')} last seasons {pr.get('season_rows')}")
    return head
