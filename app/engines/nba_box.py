"""
NBA box scores from ESPN's game summary (10-20) — one parser for last
season's collector, the nightly and the Live page.

Matched on ESPN's column LABELS (MIN, PTS, REB, AST, 3PT "made-att",
STL, BLK, TO), the way the WNBA parser has read the same feed all
summer. A stat ESPN does not send is missing, never zero (rule 6); a
player who did not play (no minutes) has no line at all.

Pure — no streamlit, no requests.
"""
from engines import espn_feed as ef

LABELS = {"min": "MIN", "pts": "PTS", "reb": "REB", "ast": "AST", "stl": "STL",
          "blk": "BLK", "tov": "TO"}
ORDER = ("min", "pts", "reb", "ast", "tpm", "stl", "blk", "tov")


def _made(s):
    a, _b = ef.pair(s)
    return a


def teams(summary):
    """[{"id", "abbr", "name", "logo"}] in the box's order (away first)."""
    out = []
    for b in (((summary or {}).get("boxscore") or {}).get("players") or []):
        t = b.get("team") or {}
        out.append({"id": str(t.get("id") or ""), "abbr": t.get("abbreviation") or "",
                    "name": t.get("displayName") or "", "logo": ef.team_logo(t)})
    return out


def parse(summary):
    """{pid: {"name", "pos", "team_id", "opp_id", "starter", "min", "pts",
    "reb", "ast", "tpm", "stl", "blk", "tov"} + (when ESPN sends them)
    "fgm", "fga", "ftm", "fta", "tpa", "oreb"} for everyone who played."""
    blocks = (((summary or {}).get("boxscore") or {}).get("players") or [])
    ids = [str(((b.get("team") or {}).get("id")) or "") for b in blocks]
    out = {}
    for i, b in enumerate(blocks):
        opp = ids[1 - i] if len(ids) == 2 else ""
        for grp in b.get("statistics") or []:
            labels = [str(x).upper() for x in (grp.get("labels") or grp.get("names") or [])]
            if "PTS" not in labels:
                continue
            idx = {k: labels.index(v) for k, v in LABELS.items() if v in labels}
            t3 = labels.index("3PT") if "3PT" in labels else None
            # 11-02 (shot profile): field goals / free throws "made-att" and
            # offensive rebounds, for the shot check and the team ranks
            pairs = {k: labels.index(v) for k, v in (("fg", "FG"), ("ft", "FT"), ("tp", "3PT"))
                     if v in labels}
            oreb = labels.index("OREB") if "OREB" in labels else None
            for ent in grp.get("athletes") or []:
                if ent.get("didNotPlay"):
                    continue
                ath = ent.get("athlete") or {}
                stats = ent.get("stats") or []
                if not ath.get("id") or not stats:
                    continue
                line = {k: ef.num(stats[j]) for k, j in idx.items() if j < len(stats)}
                if t3 is not None and t3 < len(stats):
                    line["tpm"] = _made(stats[t3])
                for k, j in pairs.items():
                    if j < len(stats):
                        m_, a_ = ef.pair(stats[j])
                        if a_ is not None:
                            line[f"{k}m"], line[f"{k}a"] = m_, a_
                if oreb is not None and oreb < len(stats):
                    line["oreb"] = ef.num(stats[oreb])
                if not line.get("min"):
                    continue
                line.update({"name": ath.get("displayName") or ath.get("shortName"),
                             "pos": (ath.get("position") or {}).get("abbreviation") or "",
                             "team_id": ids[i], "opp_id": opp,
                             "starter": bool(ent.get("starter"))})
                out[str(ath["id"])] = line
    return out


def as_tuple(date_str, line):
    """The model's game tuple: [date, team_id, opp_id, min, pts, reb, ast,
    tpm, stl, blk, tov] (engines/nba_model.IDX)."""
    return [date_str, line.get("team_id"), line.get("opp_id")] + [line.get(k) for k in ORDER]
