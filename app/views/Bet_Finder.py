"""Bet Finder — type your book's prices, get BET or SKIP.

One page for every sport and every model. Pick a game and a stat, type
the prices your book shows next to the players, and each one comes back
BET (THIN / VALUE / STRONG) or SKIP with its edge and stake — judged on
the same delivered chances the boards print (engines/bet_finder). The
game's own lines (moneyline, total, spread) sit below, and every BET can
be added to tonight's card at the bottom.

Reads what the boards already read; fits nothing.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, page_header
from engines import bet_finder as bf
from engines import live_injuries as _li
from engines import model_math as mm
from engines import model_view as mv
from engines.live_sync import sync_latest_button

EASTERN = ZoneInfo("America/New_York")

page_header("Bet Finder", "Type your book's prices — get BET or SKIP", eyebrow="EVERY SPORT",
            align="left")
sync_latest_button(key="sync_bet_finder", include_data_package=True)

st.markdown(
    f'<div style="font-size:var(--lc-text-body); line-height:1.6; color:{COLOR["text"]};">'
    f'<b>The one rule:</b> a bet is good when your book <b>pays more</b> than the price our '
    f'chance is worth. Colour on the other boards means <i>likely</i>, not <i>good</i> '
    f'&mdash; this page does the price check for you.<br>'
    f'<b>1.</b> Pick the game and the stat. <b>2.</b> Type your book&rsquo;s prices in the '
    f'<b>Your price</b> column (skip anyone you don&rsquo;t care about). <b>3.</b> Bet the '
    f'<span style="color:{COLOR["stat_high"]}; font-weight:800;">STRONG</span> / '
    f'<span style="color:{COLOR["gold"]}; font-weight:800;">VALUE</span> rows at the stake '
    f'shown; <span style="color:{COLOR["text_muted"]}; font-weight:800;">THIN</span> is a '
    f'tiny edge; SKIP means the book is not paying enough. '
    f'<span style="color:{COLOR["warn"]}; font-weight:800;">CHECK</span> means our number '
    f'and the book&rsquo;s are 10+ points apart &mdash; the book usually knows something '
    f'(injury, role, defense, game script), so it is <b>not</b> a bet until you know why. '
    f'Typing the <b>Other side</b> price too makes that check sharper.</div>',
    unsafe_allow_html=True)

_stk = mv.staking_controls("bet_finder")
ss = st.session_state
ss.setdefault("bf_card", {})


# ----------------------------------------------------------------------
# Sources — the same rows the sport's Model page prices
# ----------------------------------------------------------------------
def _nhl_games():
    from engines.slate_guard import load_slate, payload_field
    games, _d, _cur = _li.load_slate_live("nhl")
    model = payload_field("nhl", "model") or {}
    sim = payload_field("nhl", "sim") or {}
    out = []
    for g in games or []:
        if g.get("game_type") == "preseason" or g.get("status") == "final":
            continue
        out.append({"label": f"{g.get('away_abbr')} @ {g.get('home_abbr')}  "
                             f"{g.get('time_et') or ''}".strip(),
                    "g": g, "model": model, "periods": sim.get("periods")})
    return out


def _p1_group(item, sog_disp):
    """Skaters — 1st period (10-22, engines/nhl_periods): his game means at
    the MEASURED period shares. Only the markets that beat his own
    1st-period rate on unseen games are offered (no false STRONG)."""
    from engines import availability as av
    from engines import nhl_periods as npd
    per = item.get("periods") or {}
    tv = per.get("test") or {}
    mk = npd.offered(tv)
    if not mk:
        return None
    g, rows = item["g"], []
    for side in ("away", "home"):
        abbr = g.get(f"{side}_abbr") or g.get(side)
        for p in g.get(f"{side}_props") or []:
            if not av.is_out(p.get("status")):
                rows.append({"_name": f"{p.get('name')} ({abbr})",
                             "_pmfs": npd.p1_pmfs(p.get("mu"), per.get("shares"), sog_disp),
                             "_pid": p.get("pid"), "_why": p.get("why")})
    stats = tuple((s_, lab, tuple(n - 0.5 for _k, _l, st_, n in mk if st_ == s_))
                  for s_, lab, _ln in npd.P1_STATS if any(m[2] == s_ for m in mk))
    return {"label": "Skaters — 1st period", "rows": rows, "stats": stats, "markets": mk,
            "cal": mv.calibration_map(tv, mk)}


def _nhl_groups(item):
    from engines import availability as av
    from engines import nhl_model as nm
    g, model = item["g"], item["model"]
    pv = model.get("props_validation") or {}
    sog_disp = (model.get("skater_priors") or {}).get("sog_dispersion")
    shot_disp = (model.get("shots") or {}).get("dispersion")
    sk, gk = [], []
    for side in ("away", "home"):
        abbr = g.get(f"{side}_abbr") or g.get(side)
        for p in g.get(f"{side}_props") or []:
            if av.is_out(p.get("status")):
                continue
            _f = av.flag(p)
            sk.append({"_name": f"{p.get('name')} ({abbr})" + (f" ⚠ {_f}" if _f else ""),
                       "_why": p.get("why"), "_dvp": p.get("dvp") or {},
                       "_pmfs": nm.skater_pmfs(p.get("mu"), sog_disp), "_pid": p.get("pid")})
        for gp in g.get(f"{side}_goalie_props") or []:
            pm = nm.saves_pmf(gp.get("exp_sa"), shot_disp, gp.get("sv_pct"))
            if pm:
                gk.append({"_name": f"{gp.get('name')} ({abbr})", "_pmfs": {"sv": pm},
                           "_pid": gp.get("pid")})
    groups = [{"label": "Skaters", "rows": sk, "stats": nm.STATS, "markets": nm.MARKETS,
               "cal": mv.calibration_map(pv, nm.MARKETS)}]
    if gk:
        groups.append({"label": "Goalies (saves)", "rows": gk, "stats": nm.SAVE_STATS,
                       "markets": nm.SAVE_MARKETS,
                       "cal": mv.calibration_map(model.get("saves_validation") or {},
                                                 nm.SAVE_MARKETS)})
    p1 = _p1_group(item, sog_disp)
    if p1 and p1["rows"]:
        groups.append(p1)
    away, home = g.get("away_abbr") or g.get("away"), g.get("home_abbr") or g.get("home")
    return groups, bf.game_line_items(g.get("model"), g.get("odds"), away, home)


def _nfl_games():
    from engines.nfl_week import load_week
    payload, _state = _li.load_week_live()
    payload = payload or {}
    out = []
    for g in payload.get("games") or []:
        if g.get("status") == "final":
            continue
        out.append({"label": f"{g.get('away_abbr')} @ {g.get('home_abbr')}  "
                             f"{g.get('kickoff_label') or g.get('kick_date_et') or ''}".strip(),
                    "g": g, "league": payload.get("league") or {}, "dvp": payload.get("dvp"),
                    "quarters": (payload.get("sim") or {}).get("quarters")})
    return out


def _nfl_groups(item):
    g, league = item["g"], item["league"]
    from engines import availability as av
    rows = [r for r in mv.nfl_game_prop_rows(g, league, item.get("dvp"))
            if not av.is_out(r.get("Status")) and r.get("_pmfs")]
    for r in rows:
        if av.maybe_label(r.get("Status")):
            r["_name"] += f" ⚠ {av.maybe_label(r.get('Status'))}"
    stats = tuple((s, lab, (0.5,)) for s, lab, *_ in mv.NFL_STATS)
    away, home = g.get("away_abbr") or g.get("away"), g.get("home_abbr") or g.get("home")
    groups = [{"label": "Players", "rows": rows, "stats": stats, "markets": (),
               "cal": mv.nfl_calibration(league), "per_player_line": True}]
    q = _nfl_quarter_group(rows, item.get("quarters"))
    if q:
        groups.append(q)
    return groups, bf.game_line_items(g.get("model"), g.get("odds"), away, home)


def _nfl_quarter_group(rows, qmeta):
    """Players — 1st quarter / 1st half (10-22, engines/nfl_quarters): his
    game projection through the measured 1Q / 1H spread. Only the spans
    and stats that BEAT his own 1Q / 1H rate on unseen games are offered."""
    from engines import nfl_quarters as nq
    qmeta = qmeta or {}
    keys = nq.offered(qmeta.get("test"))
    if not keys or not qmeta.get("model"):
        return None
    out = []
    for r in rows:
        pm = {}
        for k in keys:
            per, st_ = k.split("_", 1)
            mu = (r.get("_means") or {}).get(st_)
            x = nq.pmf(qmeta["model"], per, st_, mu) if mu else None
            if x:
                pm[k] = x
        if pm:
            out.append({"_name": r["_name"], "_pmfs": pm, "_pid": r.get("_pid"),
                        "_why": r.get("_why")})
    if not out:
        return None
    cal = {f"@{k}": (qmeta["test"][k] or {}).get("calibration") for k in keys
           if (qmeta["test"][k] or {}).get("calibration")}
    stats = tuple((k, nq.label(*k.split("_", 1)).capitalize(), (0.5,)) for k in keys)
    return {"label": "Players — 1st quarter / 1st half", "rows": out, "stats": stats,
            "markets": (), "cal": cal, "per_player_line": True}


def _mlb_games():
    from engines.weather_engine import get_todays_games_with_weather
    from engines import mlb_game_model as mgm
    from engines.team_abbreviations import team_abbr
    model = mgm.load_model()
    games, _err = get_todays_games_with_weather(datetime.now(EASTERN).strftime("%Y-%m-%d"))
    lines = mgm.posted_lines() if model else {}
    return [{"label": f"{team_abbr(g.get('away'))} @ {team_abbr(g.get('home'))}",
             "g": g, "model": model, "odds": lines.get(g.get("game_pk"))}
            for g in games or []]


def _mlb_groups(item):
    from engines import mlb_game_model as mgm
    from engines import mlb_props as mp
    from engines.roster import get_confirmed_lineup, get_last_starting_lineup
    from engines.team_abbreviations import team_abbr
    g = item["g"]
    bat, pit = [], []
    for side, team, opp_sp, opp_name in (
            ("away", g.get("away"), g.get("home_pitcher_id"), g.get("home_pitcher")),
            ("home", g.get("home"), g.get("away_pitcher_id"), g.get("away_pitcher"))):
        lineup, confirmed = get_confirmed_lineup(g.get("game_pk"), side)
        batters = [p for p in (lineup or []) if not p.get("is_pitcher")]
        if not confirmed or not batters:
            last, _d, ok = get_last_starting_lineup(team)
            batters = [p for p in (last or []) if not p.get("is_pitcher")] if ok else []
        rows, _v, _n = mv.mlb_lineup_props(batters, opp_sp, opp_name)
        for r in rows:
            if r.get("_pmfs"):
                bat.append(dict(r, _name=f"{r.get('_name') or r.get('Batter')} "
                                          f"({team_abbr(team)})"))
        prow, _pv, _pn = mv.mlb_starter_props(batters, opp_sp, opp_name)
        if prow and prow.get("_pmfs"):
            pit.append(prow)
    groups = [{"label": "Batters", "rows": bat, "stats": mp.STATS, "markets": mp.MARKETS,
               "cal": mv.mlb_calibration()}]
    if pit:
        groups.append({"label": "Starting pitchers", "rows": pit, "stats": mp.PITCHER_STATS,
                       "markets": mp.PITCHER_MARKETS, "cal": mv.mlb_calibration(pitcher=True)})
    proj = None
    if item.get("model"):
        proj = mgm.project_game(g.get("home"), g.get("away"), g.get("home_pitcher_id"),
                                g.get("away_pitcher_id"), model=item["model"],
                                market=item.get("odds"))
    return groups, bf.game_line_items(proj, item.get("odds"), team_abbr(g.get("away")),
                                      team_abbr(g.get("home")))


def _nba_games():
    from engines import nba_view as nv
    games, model, _pget = nv.load()
    if not model:
        return []
    return [{"label": f"{g.get('away_abbr')} @ {g.get('home_abbr')}  "
                      f"{g.get('time_et') or ''}".strip(), "g": g, "model": model}
            for g in games if g.get("status") != "final" and g.get("game_type") != "preseason"]


def _nba_groups(item):
    from engines import availability as av
    from engines import nba_model as nm
    from engines import nba_view as nv
    g, model = item["g"], item["model"]
    rows = []
    for side in ("away", "home"):
        abbr = g.get(f"{side}_abbr")
        for r in g.get(f"{side}_props") or []:
            if av.is_out(r.get("status")):
                continue
            lab = av.maybe_label(r.get("status"))
            rows.append({"_name": f"{r['name']} ({abbr})" + (f" \u26a0 {lab}" if lab else "")
                         + nv.tags(r),
                         "_why": r.get("why"), "_untested": bool(r.get("new")),
                         "_grade": r.get("grade") or {},
                         "_pmfs": nm.player_pmfs(r.get("mu"), model.get("sizes")),
                         "_pid": r.get("pid")})
    stats = tuple((s, lab, (0.5,)) for s, lab in nm.PAGE_STATS
                  if s != "q1pts" or ((model.get("test") or {}).get("q1pts")))
    away, home = g.get("away_abbr"), g.get("home_abbr")
    return ([{"label": "Players", "rows": rows, "stats": stats, "markets": (),
              "cal": nv.calibration(model), "per_player_line": True}],
            bf.game_line_items(g.get("model"), g.get("odds"), away, home))


@st.cache_data(ttl=600, show_spinner=False)
def _book_board(league, day):
    """DraftKings' lines and prices for the league's upcoming games, from
    the nightly's record (engines/book_props: data/props/<league>/)."""
    from engines import book_props as bp
    from engines import slate_guard as sg
    return bp.load_board(league, [sg._PUBLISHED, sg._REPO], day)


def _attach_book(groups, league):
    """Each row's "_bk": {stat: the book's line / prices} (book_props.lookup);
    returns the record's as-of time (None when there is none)."""
    from engines import book_props as bp
    bd, as_of = _book_board(league, datetime.now(EASTERN).date().isoformat())
    if not bd:
        return None
    names = bd.get("_names") or {}
    for gr in groups:
        lg = league
        if league == "mlb" and "pitcher" in str(gr.get("label")).lower():
            lg = "mlb_p"
        for r in gr["rows"]:
            pid = r.get("_pid")
            if league == "mlb":
                # MLB: ESPN ids are not MLBAM's — matched by name
                pid = names.get(bp.name_key(r.get("Batter") or r.get("Pitcher")))
            if pid is None:
                continue
            bk = {s: bp.lookup(bd, lg, pid, s) for s, _l, _x in gr["stats"]}
            r["_bk"] = {k: v for k, v in bk.items() if v}
    return as_of


SOURCES = {"NHL": (_nhl_games, _nhl_groups), "MLB": (_mlb_games, _mlb_groups),
           "NFL": (_nfl_games, _nfl_groups), "NBA": (_nba_games, _nba_groups)}


# ----------------------------------------------------------------------
# Shared pieces
# ----------------------------------------------------------------------
def _pct(x):
    return "—" if x is None else f"{100 * x:.1f}%"


def _amer(x):
    return "—" if x is None else mm.fmt_american(int(x))


def _call_css(tier):
    lab, fg, bg = mv.TIER_STYLE.get(tier, mv.TIER_STYLE["none"])
    if tier == "none":
        return f"color: {COLOR['error']}; font-weight: 700;"
    if tier == "check":
        return f"color: {COLOR['warn']}; font-weight: 800; background-color: {COLOR['warn_dim']};"
    return f"color: {fg}; font-weight: 800;" + (f" background-color: {bg};" if bg else "")


MATCHUP_IN_NUMBER = {
    "NBA": "The matchup is already IN our chance (the opponent factor, tested).",
    "NFL": "The matchup is already IN our chance (the defense multiplier).",
    "MLB": "The matchup is already IN our chance (batter vs tonight's starter).",
    "NHL": "The position split is context, not in our chance (tested, did not beat); the "
           "team's goals and shots allowed are.",
}


def _grade_of(r, stat, side="Over"):
    """The A-F matchup letter for this row's stat, for the SIDE picked
    (10-26, engines/matchup_grade): the letter is about the over, so an
    Under flips it (an F defense is an A spot for the under). '—' when
    the sport has no matchup number for this stat."""
    from engines import matchup_grade as mg
    g = (r.get("_grade") or {}).get(stat)
    if not g:
        g = mg.from_card((r.get("_dvp") or {}).get(stat))
    if not g:
        return "—"
    return mg.LETTERS[4 - mg.LETTERS.index(g)] if side == "Under" else g


def _results_table(res, key, line_col=True):
    """The judged list: every typed price, BETs first."""
    if not res:
        return
    df = pd.DataFrame([{
        "Call": bf.TIER_LABEL[r["tier"]], "Player": r["name"],
        **({"Line": r.get("line_label")} if line_col else {}),
        "Matchup": r.get("grade") or "—",
        "Your price": _amer(r["price"]), "Our chance": _pct(r["chance"]),
        "Book says": _pct(r.get("book")),
        "Worth it at": _amer(r["worth"]), "Edge": f"{100 * r['edge']:+.1f} pts",
        "Stake": (f"${r['stake']:.2f}" if r.get("stake") else "—"),
        "Needs": _pct(r["break_even"])} for r in res])

    def _paint(frame):
        out = pd.DataFrame("", index=frame.index, columns=frame.columns)
        for i in frame.index:
            out.at[i, "Call"] = _call_css(res[i]["tier"])
            out.at[i, "Our chance"] = mv.chance_css(res[i]["chance"])
            out.at[i, "Matchup"] = mv.matchup_css(res[i].get("grade"))
        return out
    st.dataframe(mv.painted(df, _paint), hide_index=True, width="stretch", key=key)


def _notes(res):
    """Why a call was changed by the guard — one line per player."""
    lines = [f"<b>{r['name']}</b> \u2014 {r['guard']}" for r in res if r.get("guard")]
    if lines:
        st.markdown(f'<div style="font-size:var(--lc-text-small); line-height:1.6; '
                    f'color:{COLOR["warn"]};">' + "<br>".join(lines) + "</div>",
                    unsafe_allow_html=True)


def _why_lines(judged, players, stat):
    """["<b>Name</b> (line, call) — why · this stat's matchup note"] for
    the judged / reference rows, in their order. The why is the board's
    own (the nightly's projection inputs); missing -> no line."""
    by_name = {r["_name"]: r for r in players}
    out = []
    for x in judged or []:
        r = by_name.get(x["name"]) or {}
        why = r.get("_why")
        note = (r.get("_notice") or {}).get(stat) if isinstance(r.get("_notice"), dict) else None
        if not why and not note:
            continue
        call = bf.TIER_LABEL.get(x.get("tier")) if x.get("tier") else None
        out.append(f"<b>{x['name']}</b> ({x.get('line_label')}"
                   + (f", {call}" if call else "") + f", our chance {_pct(x.get('chance'))})"
                   + (f" — {why}" if why else "")
                   + (f' <span style="color:{COLOR["warn"]};">· {note}</span>' if note else ""))
    return out


def _add_to_card(res, sport, game, what):
    n = 0
    for r in res:
        if r["call"] != "BET":
            continue
        k = bf.card_key(sport, game, r["name"], what, r.get("line") or 0.0, r.get("side") or "")
        ss["bf_card"][k] = dict(r, sport=sport, game=game, what=what)
        n += 1
    return n


# ----------------------------------------------------------------------
# The page
# ----------------------------------------------------------------------
# Opens on the sport the reader is browsing (app.py's switcher), NHL else.
_here = ss.get("lc_sport_seg") or ss.get("lc_sport")
sport = st.segmented_control("Sport", list(SOURCES),
                             default=_here if _here in SOURCES else "NHL", key="bf_sport")
sport = sport or (_here if _here in SOURCES else "NHL")
games_fn, groups_fn = SOURCES[sport]
try:
    games = games_fn()
except Exception as exc:  # noqa: BLE001 — a missing feed costs this sport, never the page
    games = []
    st.caption(f"{sport} data unavailable right now ({type(exc).__name__}).")
if sport in ("NHL", "NFL"):
    _li.render_note(sport.lower())

if not games:
    st.info(f"No upcoming {sport} games with a model on the current slate.")
else:
    gi = st.selectbox("Game", range(len(games)), format_func=lambda i: games[i]["label"],
                      key=f"bf_game_{sport}")
    item = games[gi]
    game_label = item["label"]
    with st.spinner("Loading the model's numbers for this game…"):
        try:
            groups, line_items = groups_fn(item)
        except Exception as exc:  # noqa: BLE001
            groups, line_items = [], []
            st.caption(f"Could not load this game's props ({type(exc).__name__}).")

    # ---------------- player props ----------------
    with card("bf_props"):
        st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                    f'Player props</div>', unsafe_allow_html=True)
        groups = [gr for gr in groups if gr["rows"]]
        book_asof = None
        if sport in ("NHL", "NBA", "NFL", "MLB"):
            try:
                book_asof = _attach_book(groups, sport.lower())
            except Exception as exc:  # noqa: BLE001 — costs the book's lines, never the page
                st.caption(f"DraftKings' lines unavailable right now ({type(exc).__name__}).")
        if not groups:
            st.caption("No player numbers for this game yet (lineups or the nightly build "
                       "may still be pending).")
        else:
            c1, c2, c3 = st.columns([2, 2, 1])
            gname = c1.selectbox("Who", [gr["label"] for gr in groups],
                                 key=f"bf_grp_{sport}_{gi}")
            grp = next(gr for gr in groups if gr["label"] == gname)
            labels = {s: lab for s, lab, _l in grp["stats"]}
            avail = [s for s, _lab, _l in grp["stats"]
                     if any(s in (r.get("_pmfs") or {}) for r in grp["rows"])]
            stat = c2.selectbox("Stat", avail, format_func=lambda s: labels[s],
                                key=f"bf_stat_{sport}_{gi}_{gname}")
            side = c3.radio("Side", ["Over", "Under"], horizontal=True,
                            key=f"bf_side_{sport}_{gi}_{gname}")
            per_player = grp.get("per_player_line")
            default_lines = next(l for s, _lab, l in grp["stats"] if s == stat)
            # THE BOOK'S LINE (10-23): rows open on DraftKings' own line and
            # price where the nightly's record has them (engines/book_props)
            from engines import book_props as _bp
            has_book = any(((r.get("_bk") or {}).get(stat)) for r in grp["rows"])
            other = "Under" if side == "Over" else "Over"
            if has_book:
                per_player = True
            # SITE vs DRAFTKINGS (10-24, engines/book_grade): this market's
            # graded record against the book decides how far its calls may go
            _mk = {"status": "grading", "n": 0, "z": None}
            from engines import book_grade as _bg
            if sport in ("NHL", "NBA", "NFL"):
                try:
                    from engines import slate_guard as _sg
                    _mk = _bg.market_status(_bg.load_scorecard([_sg._PUBLISHED, _sg._REPO]),
                                            sport.lower(), stat)
                except Exception:  # noqa: BLE001
                    pass
                _lab = {"beats": ("BEATS DRAFTKINGS", COLOR["stat_high"]),
                        "no_edge": ("NO EDGE PROVEN vs DraftKings — calls capped at THIN",
                                    COLOR["warn"]),
                        "behind": ("BEHIND DraftKings so far — calls capped at THIN",
                                   COLOR["error"]),
                        "grading": (f"BEING GRADED vs DraftKings ({_mk['n']} of "
                                    f"{_bg.MIN_GRADED} lines) — not proven yet",
                                    COLOR["text_muted"])}[_mk["status"]]
                st.markdown(f'<div style="font-size:var(--lc-text-small); font-weight:800; '
                            f'color:{_lab[1]};">{labels[stat]}: {_lab[0]}'
                            + (f' (z={_mk["z"]}, n={_mk["n"]})' if _mk["status"] != "grading"
                               else "") + '</div>', unsafe_allow_html=True)
            if per_player:
                line = None
                st.caption(
                    ("Each row opens on DraftKings' line with its price filled in"
                     + (f" (as of {book_asof.replace('T', ' ').replace('Z', ' UTC')})"
                        if book_asof else "") + "; players without one start at the line "
                     "nearest a coin flip for him. Change a line or a price to your book's."
                     # 10-25 probe: 0 of 744 / 664 NFL items carried a price in any
                     # query variant — DraftKings' free feed gives NFL LINES only
                     + (" NFL: DraftKings' free feed posts the LINE but no price "
                        "(measured 10-25), so type your price in." if sport == "NFL" else ""))
                    if has_book else
                    "Lines differ by player for this stat — each row starts at the line "
                    "nearest a coin flip for him. Change it to your book's line.")
            else:
                line = st.selectbox("Line (as your book lists it)",
                                    sorted(set(default_lines) | {x + 0.5 for x in range(0, 12)}),
                                    index=sorted(set(default_lines)
                                                 | {x + 0.5 for x in range(0, 12)}).index(
                                        default_lines[0]),
                                    key=f"bf_line_{sport}_{gi}_{gname}_{stat}")

            players = [r for r in grp["rows"] if stat in (r.get("_pmfs") or {})]
            # Most likely first — the order a book lists its prices in, so
            # typing down the column follows the book down its list.
            players.sort(key=lambda r: -(mv._pmf_mean((r.get("_pmfs") or {}).get(stat)) or 0))

            def _bk(r):
                return (r.get("_bk") or {}).get(stat)

            def _start_line(r):
                if line is not None:
                    return line
                if _bk(r):
                    return float(_bk(r)["line"])
                return float(mv.balanced_line((r.get("_pmfs") or {}).get(stat)))

            def _dk(r):
                b = _bk(r)
                if not b:
                    return "—"
                o, u = b.get("over"), b.get("under")
                return (f"{b['line']:g}: O {_amer(o) if o is not None else '—'} · "
                        f"U {_amer(u) if u is not None else '—'}")

            starts = [_start_line(r) for r in players]
            prefill = [(_bp.price_at(_bk(r), starts[i], side),
                        _bp.price_at(_bk(r), starts[i], other)) for i, r in enumerate(players)]
            base = pd.DataFrame([{"Player": r["_name"], "Line": starts[i],
                                  "Your price": prefill[i][0], "Other side": prefill[i][1]}
                                 for i, r in enumerate(players)])
            if has_book:
                base.insert(1, "DraftKings", [_dk(r) for r in players])
            base.insert(1, "Matchup", [_grade_of(r, stat, side) for r in players])
            ed_key = f"bf_ed_{sport}_{gi}_{gname}_{stat}_{side}_{line}"
            edited = st.data_editor(
                base, key=ed_key, hide_index=True, width="stretch",
                disabled=["Player", "DraftKings", "Matchup"] + ([] if per_player else ["Line"]),
                column_config={
                    "Line": st.column_config.NumberColumn(step=0.5, format="%.1f"),
                    "Your price": st.column_config.NumberColumn(
                        help="Your book's American price, e.g. +700 or -150. Leave blank to skip.",
                        step=5, format="%d"),
                    "Other side": st.column_config.NumberColumn(
                        help="Optional: the opposite side's price (the Under if you are on the "
                             "Over). It lets the page read the BOOK's own chance and catch a "
                             "line where the book knows something the model doesn't.",
                        step=5, format="%d"),
                })

            if any(_grade_of(r, stat, side) != "—" for r in players):
                st.caption("**Matchup** = A (great spot) to F (very tough) for the side you "
                           "picked: tonight's opponent ranked on what it gives up on this stat "
                           "to his kind of player, in fifths of the league. "
                           + MATCHUP_IN_NUMBER.get(sport, ""))
            res, ref = [], []
            for i, r in enumerate(players):
                ln = float(edited.at[i, "Line"]) if per_player else line
                _yp, _os = edited.at[i, "Your price"], edited.at[i, "Other side"]
                if ln != starts[i] and _bk(r):
                    # the line was moved: a prefilled price was for the book's
                    # line, so it is swapped for the book's price at the new
                    # line (a ladder rung) or cleared — never priced at the wrong line
                    if _yp == prefill[i][0]:
                        _yp = _bp.price_at(_bk(r), ln, side)
                    if _os == prefill[i][1]:
                        _os = _bp.price_at(_bk(r), ln, other)
                ch, raw, basis = bf.chance_at(r, stat, ln, side, grp["markets"], grp["cal"])
                if ch is None or not 0 < ch < 1:
                    continue
                row = {"name": r["_name"], "chance": ch, "raw": raw, "basis": basis,
                       "grade": _grade_of(r, stat, side),
                       "worth": mm.fair_american(ch), "line": ln, "side": side,
                       "line_label": f"{side[0]}{ln:g}"}
                ref.append(row)
                _sup = bf.support_at(r, stat, ln, grp["markets"], grp["cal"])
                if _mk["status"] in ("no_edge", "behind"):
                    # graded against DraftKings and did not beat it: THIN at most
                    _sup = dict(_sup or {}, untested=True)
                j = bf.judge(ch, _yp, _stk, _os, _sup)
                if j:
                    res.append(dict(row, price=bf.valid_price(_yp), support=_sup, **j))
            res.sort(key=lambda x: (bf.CALL_ORDER[x["tier"]], -x["edge"]))

            if res:
                n_bet = sum(1 for x in res if x["call"] == "BET")
                st.markdown(f"**{n_bet} BET{'s' if n_bet != 1 else ''}** out of "
                            f"{len(res)} price{'s' if len(res) != 1 else ''} typed")
                _results_table(res, key=f"bf_res_{ed_key}")
                _notes(res)
                if n_bet and st.button("Add these BETs to tonight's card",
                                       key=f"bf_add_{ed_key}"):
                    k = _add_to_card(res, sport, game_label, labels[stat])
                    st.success(f"Added {k} to tonight's card (bottom of the page).")
                mv.parlay_add_ui([{"player": x["name"], "game": game_label,
                                   "what": f"{labels[stat]} {x['line_label']}",
                                   "chance": x["chance"], "price": x["price"],
                                   "support": x.get("support"), "tier": x["tier"]}
                                  for x in res], sport, f"bf_{ed_key}")
            else:
                st.caption("Type a price in **Your price** for anyone you're looking at. "
                           "Until then, here is what each one is worth:")
                ref.sort(key=lambda x: -x["chance"])
                ref_df = pd.DataFrame([{"Player": r["name"], "Line": r["line_label"],
                                        "Our chance": _pct(r["chance"]),
                                        "Worth it at": _amer(r["worth"])} for r in ref])

                def _paint_ref(frame):
                    out = pd.DataFrame("", index=frame.index, columns=frame.columns)
                    for i in frame.index:
                        out.at[i, "Our chance"] = mv.chance_css(ref[i]["chance"])
                    return out
                st.dataframe(mv.painted(ref_df, _paint_ref), hide_index=True, width="stretch",
                             key=f"bf_ref_{ed_key}")
            st.caption("Our chance = what calls like this actually hit on games the model had "
                       "not seen (the same number every board prints). Worth it at = the price "
                       "that breaks even; your book must pay MORE to be a bet. Needs = the hit "
                       "rate your price requires.")
            # WHY (10-24): the model's own inputs behind each player's number
            # — his rate, minutes / ice time, tonight's opponent and defense,
            # teammates out — said plainly, and which of them are IN the
            # number vs shown as context. Bets first, then the rest.
            _why_rows = _why_lines(res or ref, players, stat)
            if _why_rows:
                with st.expander(f"Why these numbers ({len(_why_rows)} players)",
                                 expanded=bool(res)):
                    st.markdown("".join(
                        f'<div style="font-size:var(--lc-text-small); line-height:1.6; '
                        f'margin-bottom:10px; padding-left:10px; border-left:2px solid '
                        f'{COLOR["border"]};">{w}</div>' for w in _why_rows),
                        unsafe_allow_html=True)

    # ---------------- game lines ----------------
    with card("bf_lines"):
        st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                    f'Game lines</div>', unsafe_allow_html=True)
        if not line_items:
            st.caption("No posted line for this game yet, so nothing to anchor a game bet to.")
        else:
            base = pd.DataFrame([{"Bet": it["name"],
                                  "Posted": (None if it.get("posted") is None
                                             else int(it["posted"])),
                                  "Your price": None} for it in line_items])
            lk = f"bf_lines_{sport}_{gi}"
            edl = st.data_editor(base, key=lk, hide_index=True, width="stretch",
                                 disabled=["Bet", "Posted"],
                                 column_config={"Your price": st.column_config.NumberColumn(
                                     step=5, format="%d",
                                     help="Your book's price for this exact line.")})
            lres = []
            for i, it in enumerate(line_items):
                j = bf.judge(it["chance"], edl.at[i, "Your price"], _stk, None,
                             bf.MARKET_SUPPORT)
                if j:
                    lres.append(dict(it, price=bf.valid_price(edl.at[i, "Your price"]),
                                     line=0.0, side=it["name"], **j))
            lres.sort(key=lambda x: (bf.CALL_ORDER[x["tier"]], -x["edge"]))
            if lres:
                _results_table(lres, key=f"bf_lres_{lk}", line_col=False)
                _notes(lres)
                if any(x["call"] == "BET" for x in lres) and st.button(
                        "Add these BETs to tonight's card", key=f"bf_ladd_{lk}"):
                    k = _add_to_card(lres, sport, game_label, "game line")
                    st.success(f"Added {k} to tonight's card.")
                mv.parlay_add_ui([{"player": x["name"], "game": game_label,
                                   "what": "game line", "chance": x["chance"],
                                   "price": x["price"], "support": bf.MARKET_SUPPORT,
                                   "tier": x["tier"]} for x in lres], sport, f"bf_l_{lk}")
            st.caption("Game lines are priced on the MARKET's chance, moved toward the model "
                       "only as far as the model has beaten the market on past games. When the "
                       "model has not earned a say, a BET here means your book's price is better "
                       "than the posted one — line shopping, which is real money too. Only "
                       "the posted line is priced; for another line use the Model page's alt "
                       "lines.")

# ---------------- tonight's card ----------------
with card("bf_card"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                f'Tonight’s card</div>', unsafe_allow_html=True)
    if ss["bf_card"] and st.button("Clear the card", key="bf_clear"):
        ss["bf_card"] = {}
    rows = bf.card_rows(ss["bf_card"])
    if not rows:
        st.caption("Every BET you add lands here, across sports and games, so you can place "
                   "them in one go. It lasts while this page is open.")
    else:
        bankroll = _stk[0]
        stakes = [r.get("stake") or 0.0 for r in rows]
        scaled, f = mv.scale_to_slate(stakes, bankroll, mv.slate_cap())
        df = pd.DataFrame([{
            "Call": bf.TIER_LABEL[r["tier"]], "Sport": r["sport"], "Game": r["game"],
            "Bet": f"{r['name']} · {r['what']}"
                   + (f" {r['line_label']}" if r.get("line_label") else ""),
            "Price": _amer(r["price"]), "Our chance": _pct(r["chance"]),
            "Edge": f"{100 * r['edge']:+.1f} pts",
            "Stake": (f"${s:.2f}" if s else "—")} for r, s in zip(rows, scaled)])

        def _paint_card(frame):
            out = pd.DataFrame("", index=frame.index, columns=frame.columns)
            for i in frame.index:
                out.at[i, "Call"] = _call_css(rows[i]["tier"])
            return out
        st.dataframe(mv.painted(df, _paint_card), hide_index=True, width="stretch",
                     key="bf_card_tab")
        tot = sum(x for x in scaled if x)
        st.caption((f"Total staked ${tot:.2f}"
                    + (f" (scaled down together to your per-slate cap)" if f < 1 else "")
                    + ". " if bankroll else "Set a bankroll above to see stakes. ")
                   + "Long shots lose most nights even when they are good bets; the money is "
                     "in repeating good prices for weeks. Check the Results page to see how "
                     "the models are doing.")

# ---------------- the parlay slip (10-18, engines/parlay) ----------------
ss.setdefault("parlay", {})
with card("bf_parlay"):
    from engines import parlay as pl
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                f'Parlay slip</div>', unsafe_allow_html=True)
    legs = list(ss["parlay"].values())
    if not legs:
        st.caption("Add legs from the Bet Finder, Long Shots or Live with your book's price "
                   "typed — BET or SKIP. The slip checks the WHOLE ticket: the chance every "
                   "leg hits, what the payout is worth, and which leg carries or drags it.")
    else:
        keys = list(ss["parlay"])
        c1, c2, c3 = st.columns(3)
        pprice = c1.number_input("Book's parlay price (optional)", value=None, step=5,
                                 format="%d", key="pl_price",
                                 help="What your book shows for the whole ticket. Blank = the "
                                      "legs' prices multiplied.")
        boost = c2.number_input("Profit boost %", min_value=0, max_value=200, value=0, step=5,
                                key="pl_boost")
        if c3.button("Clear the slip", key="pl_clear"):
            ss["parlay"] = {}
            st.rerun()
        v = pl.judge(legs, pprice, boost / 100.0, _stk)
        df = pd.DataFrame([{
            "Leg": f"{x['player']} · {x['what']}", "Game": x.get("game") or "—",
            "Price": _amer(x["price"]), "Our chance": _pct(x["chance"]),
            "Does": (f"carries +{100 * (x['ratio'] - 1):.0f}%" if x["ratio"] >= 1
                     else f"drags {100 * (x['ratio'] - 1):.0f}%")}
            for x in (v["legs"] if v else [dict(l, ratio=1.0) for l in legs])])

        def _paint_pl(frame):
            out = pd.DataFrame("", index=frame.index, columns=frame.columns)
            src = v["legs"] if v else []
            for i in frame.index:
                if i < len(src):
                    out.at[i, "Does"] = (f"color: {COLOR['stat_high']}; font-weight: 700;"
                                         if src[i]["ratio"] >= 1 else
                                         f"color: {COLOR['error']}; font-weight: 700;")
            return out
        st.dataframe(mv.painted(df, _paint_pl), hide_index=True, width="stretch",
                     key="pl_tab")
        drop = st.multiselect("Remove a leg", range(len(keys)),
                              format_func=lambda i: f"{legs[i]['player']} · {legs[i]['what']}",
                              key="pl_drop")
        if drop and st.button("Remove", key="pl_drop_go"):
            for i in drop:
                ss["parlay"].pop(keys[i], None)
            st.rerun()
        from engines import bet_log_ui as _blu
        _sports = {x.get("sport") for x in legs}
        _sport = _sports.pop() if len(_sports) == 1 else "Mixed"
        if not v:
            st.caption("Two or more legs make a parlay.")
            x = legs[0]
            if x.get("price") is not None:
                _blu.log_button(_sport, "single", f"{x['player']} · {x['what']}", x["chance"],
                                x["price"], None, x.get("single_tier"), [], "pl_single")
        else:
            lab, fg, bg = mv.TIER_STYLE[v["tier"]]
            call = "SKIP" if v["tier"] == "none" else lab
            st.markdown(
                f'<div style="font-size:var(--lc-text-body); line-height:1.7;">'
                f'<span style="color:{fg if v["tier"] != "none" else COLOR["error"]}; '
                f'font-weight:800; font-size:1.15em;">{call}</span> &nbsp; '
                f'All {len(v["legs"])} hit: <b>{100 * v["chance"]:.2f}%</b> '
                f'(about 1 in {max(1, round(1 / v["chance"])):,}) · pays '
                f'<b>{_amer(v["american"])}</b>'
                + (f' with the {boost}% boost' if boost else '')
                + f' · <b>{100 * v["ev"]:+.0f}</b> per $100 over time'
                + (f' · stake ${v["stake"]:.2f}' if v.get("stake") else "")
                + "</div>", unsafe_allow_html=True)
            if v["reasons"]:
                st.markdown(f'<div style="font-size:var(--lc-text-small); color:{COLOR["warn"]};">'
                            + "<br>".join(v["reasons"]) + "</div>", unsafe_allow_html=True)
            _games = {x.get("game") for x in legs}
            _blu.log_button(_sport, "sgp" if len(_games) == 1 else "parlay",
                            " + ".join(f"{x['player']} · {x['what']}" for x in legs), v["chance"],
                            v["american"], v.get("stake"), v["tier"],
                            [f"{x['player']} · {x['what']} ({_amer(x['price'])})" for x in legs],
                            "pl_parlay")
            if v["drag"] and v["tier"] in ("none", "thin"):
                st.caption("Dragging it: " + ", ".join(
                    f"{x['player']} ({100 * (x['ratio'] - 1):+.0f}%)" for x in v["drag"])
                    + " — drop or re-price those legs and watch the call change.")
        st.caption("Carries / drags = that leg's chance times its price: above even it adds to "
                   "the ticket, below it takes away. A boost raises every leg at once. Legs "
                   "from the same game are linked (books price that) and are flagged.")

footer()

