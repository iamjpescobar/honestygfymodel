"""Long Shots — every well-measured long shot on the slate, +300 to +2000.

engines/long_shots says what qualifies and why. The reader finds any
name his book pays MORE than "Worth it at", types the price, and gets
BET / CHECK / SKIP through the site's one guard (the same call the Bet
Finder makes); BETs go on the same Tonight's card. Fits nothing.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, page_header
from engines import availability as av
from engines import live_injuries as _li
from engines import bet_finder as bf
from engines import long_shots as ls
from engines import model_math as mm
from engines import model_view as mv

EASTERN = ZoneInfo("America/New_York")

page_header("Long Shots", "+300 to +2000 — the prices worth hunting", eyebrow="EVERY SPORT",
            align="left")
st.markdown(
    f'<div style="font-size:var(--lc-text-body); line-height:1.6; color:{COLOR["text"]};">'
    f'Every player tonight whose <b>tested</b> chance puts him between <b>+300 and +2000</b>, '
    f'with the price he is <b>worth</b>. Books price depth players lazily &mdash; the public bets '
    f'the stars &mdash; so the value at this end of the board is any name your book pays '
    f'<b>more</b> for than <span style="color:{COLOR["gold"]}; font-weight:800;">Worth it at</span>. '
    f'Type that price and the page answers BET, CHECK or SKIP.<br>'
    f'<span style="color:{COLOR["text_muted"]};">Only chances the model has been graded on are '
    f'listed: the market is tested and the call sits where it has 30+ graded calls behind it. '
    f'Even a good +1200 hits about 1 time in 8 &mdash; the money is in taking prices like it '
    f'every time they show up, at small stakes.</span></div>',
    unsafe_allow_html=True)

_stk = mv.staking_controls("long_shots")
ss = st.session_state
ss.setdefault("bf_card", {})


# ----------------------------------------------------------------------
# Sources
# ----------------------------------------------------------------------
@st.cache_data(ttl=900, show_spinner=False)
def _nhl(_day):
    from engines.slate_guard import load_slate, payload_field
    from engines import nhl_model as nm
    games, _d, _cur = _li.load_slate_live("nhl")
    model = payload_field("nhl", "model") or {}
    cal = mv.calibration_map(model.get("props_validation") or {}, nm.MARKETS)
    rows = []
    for g in games or []:
        if g.get("game_type") == "preseason" or g.get("status") == "final":
            continue
        label = f"{g.get('away_abbr')} @ {g.get('home_abbr')}"
        rows += ls.rows_from_markets(ls.nhl_players(g, model), nm.MARKETS, cal, label, "NHL")
    return rows


@st.cache_data(ttl=900, show_spinner=False)
def _mlb(_day):
    from engines.weather_engine import get_todays_games_with_weather
    from engines.roster import get_confirmed_lineup, get_last_starting_lineup
    from engines.team_abbreviations import team_abbr
    from engines import mlb_props as mp
    games, _err = get_todays_games_with_weather(_day)
    cal = mv.mlb_calibration()
    rows = []
    for g in games or []:
        label = f"{team_abbr(g.get('away'))} @ {team_abbr(g.get('home'))}"
        for side, team, other, opp_sp, opp_name in (
                ("away", g.get("away"), g.get("home"), g.get("home_pitcher_id"), g.get("home_pitcher")),
                ("home", g.get("home"), g.get("away"), g.get("away_pitcher_id"), g.get("away_pitcher"))):
            try:
                lineup, confirmed = get_confirmed_lineup(g.get("game_pk"), side)
                bats = [p for p in (lineup or []) if not p.get("is_pitcher")]
                if not confirmed or not bats:
                    last, _ld, ok = get_last_starting_lineup(team)
                    bats = [p for p in (last or []) if not p.get("is_pitcher")] if ok else []
                prows, _v, _n = mv.mlb_lineup_props(bats, opp_sp, opp_name)
            except Exception:  # noqa: BLE001 — one game's feed costs that game only
                continue
            players = [{"_name": f"{r.get('Batter')} ({team_abbr(team)})",
                        "_probs": r.get("_probs") or {}, "_why": r.get("_why"),
                        "team": team_abbr(team), "opp": team_abbr(other),
                        "_signals": (f"vs {opp_name}" if opp_name else "")
                                    + ("" if confirmed else " · lineup not posted yet")}
                       for r in prows if r.get("_probs")]
            rows += ls.rows_from_markets(players, mp.MARKETS, cal, label, "MLB")
    return rows


@st.cache_data(ttl=900, show_spinner=False)
def _nfl(_day):
    from engines.nfl_week import load_week
    from engines import edge_boards as eb
    wk, _state = _li.load_week_live()
    wk = wk or {}
    league = wk.get("league") or {}
    bins = ((league.get("prop_validation") or {}).get("td") or {}).get("calibration")
    rows = []
    for r in eb.nfl_td_rows(wk.get("games") or [], league, wk.get("dvp")):
        x = ls.row_from_chance(f"{r.get('player')} ({r.get('team')})", "Anytime TD",
                               r.get("chance"), r.get("raw"), bins,
                               f"{r.get('team')} vs {r.get('opp')}", "NFL",
                               r.get("team"), r.get("opp"),
                               signals=" · ".join(b for b in (
                                   (f"\u26a0 {av.maybe_label(r.get('status'))}"
                                    if av.maybe_label(r.get("status")) else ""),
                                   (f"{r['opp']} soft vs his position"
                                    if ((r.get("card_td") or {}).get("tier") == "soft") else ""),
                               ) if b), why=None)
        if x:
            rows.append(x)
    return rows


@st.cache_data(ttl=900, show_spinner=False)
def _nba(_day):
    from engines import nba_view as nv
    games, model, _pget = nv.load()
    return nv.long_shots(games, model)


SOURCES = {"NHL": _nhl, "MLB": _mlb, "NFL": _nfl, "NBA": _nba}
# Where on the long-shot ladder to look. Opens on +600..+2000 — the
# Caulfield zone, where a book's lazy price is worth the most.
PRICE_BANDS = {"+300 to +2000 (all)": (300, 2000), "+600 to +2000": (600, 2000),
               "+1000 to +2000": (1000, 2000), "+300 to +599": (300, 599)}

_here = ss.get("lc_sport_seg") or ss.get("lc_sport")
sport = st.segmented_control("Sport", list(SOURCES),
                             default=_here if _here in SOURCES else "NHL", key="ls_sport")
sport = sport or (_here if _here in SOURCES else "NHL")
_day = datetime.now(EASTERN).strftime("%Y-%m-%d")
with st.spinner("Finding tonight's long shots…"):
    try:
        rows = ls.rank(SOURCES[sport](_day))
    except Exception as exc:  # noqa: BLE001 — a missing feed costs this sport, never the page
        rows = []
        st.caption(f"{sport} data unavailable right now ({type(exc).__name__}).")
if sport in ("NHL", "NFL", "NBA"):
    _li.render_note(sport.lower())



if not rows:
    st.info(f"No well-measured {sport} long shots on the current slate (or the nightly build "
            f"is not in yet).")
else:
    c0, c1, c2 = st.columns(3)
    psel = c0.selectbox("Price range (worth it at)", list(PRICE_BANDS), index=1,
                        key=f"ls_band_{sport}")
    lo_px, hi_px = PRICE_BANDS[psel]
    markets = ["All markets"] + sorted({r["market"] for r in rows})
    msel = c1.selectbox("Market", markets, key=f"ls_mkt_{sport}")
    games = ["All games"] + sorted({r["game"] for r in rows})
    gsel = c2.selectbox("Game", games, key=f"ls_game_{sport}")
    show = [r for r in rows if (msel == "All markets" or r["market"] == msel)
            and (gsel == "All games" or r["game"] == gsel)
            and lo_px <= (r["worth"] or 0) <= hi_px][:60]

    if not show:
        st.info("No long shots in that price range for this filter \u2014 widen the range.")
    else:
        with card("ls_board"):
            st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                        f'{len(show)} long shot{"s" if len(show) != 1 else ""} '
                        f'— type your book\'s price</div>', unsafe_allow_html=True)
            base = pd.DataFrame([{
                "Player": r["player"], "Bet": r["market"],
                "Worth it at": mm.fmt_american(r["worth"]),
                "Chance": f"{100 * r['chance']:.1f}%",
                "Your price": None,
                "Why it's live": r["signals"] or "—",
                "Game": r["game"]} for r in show])
            ed_key = f"ls_ed_{sport}_{msel}_{gsel}"
            edited = st.data_editor(
                base, key=ed_key, hide_index=True, width="stretch",
                disabled=["Player", "Bet", "Worth it at", "Chance", "Why it's live", "Game"],
                column_config={"Your price": st.column_config.NumberColumn(
                    help="Your book's price for this bet, e.g. +1200. Leave blank to skip.",
                    step=5, format="%d")})

            res = []
            for i, r in enumerate(show):
                j = bf.judge(r["chance"], edited.at[i, "Your price"], _stk, None, r["support"])
                if j:
                    res.append(dict(r, name=r["player"], line=0.0, side=r["market"],
                                    line_label="", price=bf.valid_price(edited.at[i, "Your price"]),
                                    **j))
            res.sort(key=lambda x: (bf.CALL_ORDER[x["tier"]], -x["edge"]))
            if res:
                n_bet = sum(1 for x in res if x["call"] == "BET")
                st.markdown(f"**{n_bet} BET{'s' if n_bet != 1 else ''}** out of {len(res)} "
                            f"price{'s' if len(res) != 1 else ''} typed")
                df = pd.DataFrame([{
                    "Call": bf.TIER_LABEL[x["tier"]], "Player": x["player"], "Bet": x["market"],
                    "Your price": mm.fmt_american(x["price"]), "Chance": f"{100 * x['chance']:.1f}%",
                    "Worth it at": mm.fmt_american(x["worth"]),
                    "Edge": f"{100 * x['edge']:+.1f} pts",
                    "Stake": f"${x['stake']:.2f}" if x.get("stake") else "—"} for x in res])

                def _paint(frame):
                    out = pd.DataFrame("", index=frame.index, columns=frame.columns)
                    for k in frame.index:
                        t = res[k]["tier"]
                        lab, fg, bg = mv.TIER_STYLE[t]
                        out.at[k, "Call"] = (f"color: {COLOR['error']}; font-weight: 700;" if t == "none"
                                             else f"color: {fg}; font-weight: 800;"
                                             + (f" background-color: {bg};" if bg else ""))
                    return out
                st.dataframe(mv.painted(df, _paint), hide_index=True, width="stretch",
                             key=f"ls_res_{ed_key}")
                notes = [f"<b>{x['player']}</b> — {x['guard']}" for x in res if x.get("guard")]
                if notes:
                    st.markdown(f'<div style="font-size:var(--lc-text-small); line-height:1.6; '
                                f'color:{COLOR["warn"]};">' + "<br>".join(notes) + "</div>",
                                unsafe_allow_html=True)
                if n_bet and st.button("Add these BETs to tonight's card", key=f"ls_add_{ed_key}"):
                    k = 0
                    for x in res:
                        if x["call"] == "BET":
                            ss["bf_card"][bf.card_key(sport, x["game"], x["player"], x["market"],
                                                      0.0, "")] = dict(
                                x, sport=sport, what=x["market"], line_label="")
                            k += 1
                    st.success(f"Added {k} to tonight's card — it lives on the Bet Finder page.")
                mv.parlay_add_ui([{"player": x["player"], "game": x["game"], "what": x["market"],
                                   "chance": x["chance"], "price": x["price"],
                                   "support": x.get("support"), "tier": x["tier"]}
                                  for x in res], sport, f"ls_{ed_key}")
            st.caption("Chance = what calls like this actually hit on games the model had not seen. "
                       "Worth it at = the break-even price; your book must pay MORE. A gap of 10+ "
                       "points to your book's price is CHECK, not a bet: at a long price that usually "
                       "means the book knows about a scratch, a demotion or a goalie change.")

        sel = st.selectbox("Why this one?", range(len(show)),
                           format_func=lambda i: f"{show[i]['player']} · {show[i]['market']}",
                           key=f"ls_why_{sport}")
        if show[sel].get("why"):
            st.markdown(f'<div style="font-size:var(--lc-text-small); line-height:1.6;">'
                        f'{show[sel]["why"]}</div>', unsafe_allow_html=True)

footer()
