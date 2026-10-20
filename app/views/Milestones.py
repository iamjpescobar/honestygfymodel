"""Milestone Watch — who is close to a round career or season number
tonight (a 300th goal, 10,000 passing yards, 3,000 hits), what he needs,
and the model's chance he gets it. Plus the marks reached lately.

engines/milestones says what counts and how the career number is built;
the nightlies (milestone_log) hang each NHL / NFL player's items on his
row; MLB careers are read live, one stats API call per lineup. The
chance is the one every board prices — the same distribution, delivered
through the stat's tested curve. Fits nothing.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, page_header
from engines import bet_finder as bf
from engines import live_injuries as _li
from engines import milestones as ms
from engines import model_math as mm
from engines import model_view as mv

EASTERN = ZoneInfo("America/New_York")

page_header("Milestone Watch", "Who is close to a big number tonight", eyebrow="EVERY SPORT",
            align="left")
st.markdown(
    f'<div style="font-size:var(--lc-text-body); line-height:1.6; color:{COLOR["text"]};">'
    f'Every player within one game of a round career or season number &mdash; a '
    f'<b>300th goal</b>, <b>10,000 passing yards</b>, <b>3,000 hits</b> &mdash; with what he '
    f'needs tonight and the model&rsquo;s chance he gets it.<br>'
    f'<span style="color:{COLOR["text_muted"]};">A milestone is a story, not an edge: books '
    f'know about them and the public loves betting them, so those props are often priced '
    f'<i>short</i>. Bet one only when your book pays more than '
    f'<b>Worth it at</b> &mdash; or type it into the Bet Finder.</span></div>',
    unsafe_allow_html=True)

ss = st.session_state
_day = datetime.now(EASTERN).strftime("%Y-%m-%d")


def _row(player, team, game, it, chance):
    return {"player": player, "team": team, "game": game, "what": it["what"],
            "scope": it["scope"], "have": it["have"], "need": it["need"], "stat": it["stat"],
            "chance": chance}


# ----------------------------------------------------------------------
# Sources
# ----------------------------------------------------------------------
@st.cache_data(ttl=900, show_spinner=False)
def _nhl(_d):
    from engines.slate_guard import load_slate, payload_field
    from engines import nhl_model as nm
    games, _sd, _cur = _li.load_slate_live("nhl")
    model = payload_field("nhl", "model") or {}
    cal = mv.calibration_map(model.get("props_validation") or {}, nm.MARKETS)
    disp = (model.get("skater_priors") or {}).get("sog_dispersion")
    out = []
    for g in games or []:
        if g.get("game_type") == "preseason" or g.get("status") == "final":
            continue
        label = f"{g.get('away_abbr')} @ {g.get('home_abbr')}"
        for side in ("away", "home"):
            abbr = g.get(f"{side}_abbr") or g.get(side)
            for p in g.get(f"{side}_props") or []:
                items = p.get("milestones") or []
                if not items:
                    continue
                row = {"_pmfs": nm.skater_pmfs(p.get("mu"), disp)}
                for it in items:
                    ch = None
                    if it["stat"] in row["_pmfs"]:
                        ch, _raw, _b = bf.chance_at(row, it["stat"], it["need"] - 0.5, "Over",
                                                    nm.MARKETS, cal)
                    out.append(_row(p.get("name"), abbr, label, it, ch))
    happened = payload_field("nhl", "milestones_happened") or []
    return out, happened, None


@st.cache_data(ttl=900, show_spinner=False)
def _nfl(_d):
    from engines.nfl_week import load_week
    wk, _state = _li.load_week_live()
    wk = wk or {}
    league = wk.get("league") or {}
    cal = mv.nfl_calibration(league)
    out = []
    for g in wk.get("games") or []:
        if g.get("status") == "final":
            continue
        label = f"{g.get('away_abbr')} @ {g.get('home_abbr')}"
        for r in mv.nfl_game_prop_rows(g, league, wk.get("dvp")):
            for it in r.get("_milestones") or []:
                ch = None
                if it["stat"] in (r.get("_pmfs") or {}):
                    ch, _raw, _b = bf.chance_at(r, it["stat"], it["need"] - 0.5, "Over", (), cal)
                out.append(_row(r.get("Player"), r.get("Team"), label, it, ch))
    return out, wk.get("milestones_happened") or [], None


@st.cache_data(ttl=3600, show_spinner=False)
def _mlb_careers(ids):
    import requests
    if not ids:
        return {}
    try:
        resp = requests.get("https://statsapi.mlb.com/api/v1/people",
                            params={"personIds": ",".join(ids),
                                    "hydrate": "stats(group=[hitting],type=[career])"},
                            timeout=15)
        resp.raise_for_status()
        return ms.parse_mlb_careers(resp.json())
    except Exception:  # noqa: BLE001 — no careers is no watch, never a crash
        return {}


@st.cache_data(ttl=900, show_spinner=False)
def _mlb(_d):
    from engines.weather_engine import get_todays_games_with_weather
    from engines.roster import get_confirmed_lineup, get_last_starting_lineup
    from engines.team_abbreviations import team_abbr
    from engines import mlb_props as mp
    games, _err = get_todays_games_with_weather(_d)
    games = games or []
    regular = [g for g in games if (g.get("game_type") or "R") == "R"]
    if games and not regular:
        return [], [], ("Every MLB game today is a postseason game, and postseason stats do "
                        "not count toward career totals. The MLB watch returns on opening day.")
    cal = mv.mlb_calibration()
    out = []
    for g in regular:
        label = f"{team_abbr(g.get('away'))} @ {team_abbr(g.get('home'))}"
        for side, team, opp_sp, opp_name in (
                ("away", g.get("away"), g.get("home_pitcher_id"), g.get("home_pitcher")),
                ("home", g.get("home"), g.get("away_pitcher_id"), g.get("away_pitcher"))):
            try:
                lineup, confirmed = get_confirmed_lineup(g.get("game_pk"), side)
                bats = [p for p in (lineup or []) if not p.get("is_pitcher")]
                if not confirmed or not bats:
                    last, _ld, ok = get_last_starting_lineup(team)
                    bats = [p for p in (last or []) if not p.get("is_pitcher")] if ok else []
                prows, _v, _n = mv.mlb_lineup_props(bats, opp_sp, opp_name)
            except Exception:  # noqa: BLE001 — one game's feed costs that game only
                continue
            careers = _mlb_careers(tuple(sorted(str(r["_id"]) for r in prows if r.get("_id"))))
            for r in prows:
                items = ms.needs(careers.get(str(r.get("_id"))), None, "mlb")
                for it in items:
                    ch = None
                    if it["stat"] in (r.get("_pmfs") or {}):
                        ch, _raw, _b = bf.chance_at(r, it["stat"], it["need"] - 0.5, "Over",
                                                    mp.MARKETS, cal)
                    out.append(_row(r.get("Batter"), team_abbr(team), label, it, ch))
    return out, [], None


@st.cache_data(ttl=900, show_spinner=False)
def _nba(_d):
    from engines import nba_model as nm
    from engines import nba_view as nv
    games, model, pget = nv.load()
    cal = nv.calibration(model)
    out = []
    for g in games or []:
        if g.get("status") == "final":
            continue
        label = f"{g.get('away_abbr')} @ {g.get('home_abbr')}"
        for side in ("away", "home"):
            abbr = g.get(f"{side}_abbr")
            for p in g.get(f"{side}_props") or []:
                items = p.get("milestones") or []
                if not items:
                    continue
                row = {"_pmfs": nm.player_pmfs(p.get("mu"), (model or {}).get("sizes"))}
                for it in items:
                    ch = None
                    if it["stat"] in row["_pmfs"]:
                        ch, _raw, _b = bf.chance_at(row, it["stat"], it["need"] - 0.5, "Over",
                                                    (), cal)
                    out.append(_row(p.get("name"), abbr, label, it, ch))
    return out, pget("milestones_happened") or [], None


SOURCES = {"NHL": _nhl, "NFL": _nfl, "NBA": _nba, "MLB": _mlb}
_here = ss.get("lc_sport_seg") or ss.get("lc_sport")
sport = st.segmented_control("Sport", list(SOURCES),
                             default=_here if _here in SOURCES else "NHL", key="ms_sport")
sport = sport or (_here if _here in SOURCES else "NHL")

with st.spinner("Checking who is close tonight…"):
    try:
        rows, happened, note = SOURCES[sport](_day)
    except Exception as exc:  # noqa: BLE001 — a missing feed costs this sport, never the page
        rows, happened, note = [], [], f"{sport} data unavailable right now ({type(exc).__name__})."

rows = sorted(rows, key=lambda r: (r["chance"] is None, -(r["chance"] or 0), r["need"]))
if sport in ("NHL", "NFL", "NBA"):
    _li.render_note(sport.lower())

with card("ms_watch"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                f'Within reach tonight</div>', unsafe_allow_html=True)
    if note:
        st.info(note)
    elif not rows:
        st.info(f"No {sport} player is within one game of a milestone on the current slate "
                f"(or the nightly build has not filled careers in yet — the first nights "
                f"fetch a few hundred players each).")
    else:
        df = pd.DataFrame([{
            "Player": r["player"], "Milestone": r["what"],
            "Has": f"{r['have']:,}", "Needs": f"{r['need']:,}",
            "Chance tonight": ("if he plays" if r["stat"] == "gp" else
                               "—" if r["chance"] is None else f"{100 * r['chance']:.1f}%"),
            "Worth it at": (mm.fmt_american(mm.fair_american(r["chance"]))
                            if r["chance"] and 0 < r["chance"] < 1 else "—"),
            "Team": r["team"], "Game": r["game"]} for r in rows])

        def _paint(frame):
            out = pd.DataFrame("", index=frame.index, columns=frame.columns)
            for i in frame.index:
                c = rows[i]["chance"]
                if c is not None:
                    out.at[i, "Chance tonight"] = mv.chance_css(c)
                if rows[i]["scope"] == "career":
                    out.at[i, "Milestone"] = f"color: {COLOR['gold']}; font-weight: 700;"
            return out

        st.dataframe(mv.painted(df, _paint), hide_index=True, width="stretch",
                     key=f"ms_tab_{sport}")
        st.caption("Gold = a career mark; plain = a season mark. Chance tonight = what calls "
                   "like it actually hit on games the model had not seen, for the exact number "
                   "he needs (2 goals is the 2+ goal chance). Career = every season before this "
                   "one plus this season's box scores, updated every night. Injured players are "
                   "not listed.")

with card("ms_done"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                f'Reached lately</div>', unsafe_allow_html=True)
    if sport == "MLB":
        st.caption("MLB milestones reached show up here once the regular season is back.")
    elif not happened:
        st.caption("No milestones reached in the last few days among the players on file.")
    else:
        st.dataframe(pd.DataFrame([{"Date": h.get("date"), "Player": h.get("name") or "—",
                                    "Reached": h.get("what"),
                                    "Kind": "Career" if h.get("scope") == "career" else "Season"}
                                   for h in happened[:40]]),
                     hide_index=True, width="stretch", key=f"ms_done_{sport}")

footer()
