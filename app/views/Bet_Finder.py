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
from engines import model_math as mm
from engines import model_view as mv

EASTERN = ZoneInfo("America/New_York")

page_header("Bet Finder", "Type your book's prices — get BET or SKIP", eyebrow="EVERY SPORT",
            align="left")

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
    f'tiny edge; SKIP means the book is not paying enough.</div>',
    unsafe_allow_html=True)

_stk = mv.staking_controls("bet_finder")
ss = st.session_state
ss.setdefault("bf_card", {})


# ----------------------------------------------------------------------
# Sources — the same rows the sport's Model page prices
# ----------------------------------------------------------------------
def _nhl_games():
    from engines.slate_guard import load_slate, payload_field
    games, _d, _cur = load_slate("nhl")
    model = payload_field("nhl", "model") or {}
    out = []
    for g in games or []:
        if g.get("game_type") == "preseason" or g.get("status") == "final":
            continue
        out.append({"label": f"{g.get('away_abbr')} @ {g.get('home_abbr')}  "
                             f"{g.get('time_et') or ''}".strip(),
                    "g": g, "model": model})
    return out


def _nhl_groups(item):
    from engines import nhl_model as nm
    g, model = item["g"], item["model"]
    pv = model.get("props_validation") or {}
    sog_disp = (model.get("skater_priors") or {}).get("sog_dispersion")
    shot_disp = (model.get("shots") or {}).get("dispersion")
    sk, gk = [], []
    for side in ("away", "home"):
        abbr = g.get(f"{side}_abbr") or g.get(side)
        for p in g.get(f"{side}_props") or []:
            sk.append({"_name": f"{p.get('name')} ({abbr})", "_why": p.get("why"),
                       "_pmfs": nm.skater_pmfs(p.get("mu"), sog_disp)})
        for gp in g.get(f"{side}_goalie_props") or []:
            pm = nm.saves_pmf(gp.get("exp_sa"), shot_disp, gp.get("sv_pct"))
            if pm:
                gk.append({"_name": f"{gp.get('name')} ({abbr})", "_pmfs": {"sv": pm}})
    groups = [{"label": "Skaters", "rows": sk, "stats": nm.STATS, "markets": nm.MARKETS,
               "cal": mv.calibration_map(pv, nm.MARKETS)}]
    if gk:
        groups.append({"label": "Goalies (saves)", "rows": gk, "stats": nm.SAVE_STATS,
                       "markets": nm.SAVE_MARKETS,
                       "cal": mv.calibration_map(model.get("saves_validation") or {},
                                                 nm.SAVE_MARKETS)})
    away, home = g.get("away_abbr") or g.get("away"), g.get("home_abbr") or g.get("home")
    return groups, bf.game_line_items(g.get("model"), g.get("odds"), away, home)


def _nfl_games():
    from engines.nfl_week import load_week
    payload, _state = load_week()
    payload = payload or {}
    out = []
    for g in payload.get("games") or []:
        if g.get("status") == "final":
            continue
        out.append({"label": f"{g.get('away_abbr')} @ {g.get('home_abbr')}  "
                             f"{g.get('kickoff_label') or g.get('kick_date_et') or ''}".strip(),
                    "g": g, "league": payload.get("league") or {}, "dvp": payload.get("dvp")})
    return out


def _nfl_groups(item):
    g, league = item["g"], item["league"]
    rows = [r for r in mv.nfl_game_prop_rows(g, league, item.get("dvp"))
            if str(r.get("Status")).lower() != "out" and r.get("_pmfs")]
    stats = tuple((s, lab, (0.5,)) for s, lab, *_ in mv.NFL_STATS)
    away, home = g.get("away_abbr") or g.get("away"), g.get("home_abbr") or g.get("home")
    return ([{"label": "Players", "rows": rows, "stats": stats, "markets": (),
              "cal": mv.nfl_calibration(league), "per_player_line": True}],
            bf.game_line_items(g.get("model"), g.get("odds"), away, home))


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


SOURCES = {"NHL": (_nhl_games, _nhl_groups), "MLB": (_mlb_games, _mlb_groups),
           "NFL": (_nfl_games, _nfl_groups)}


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
    return f"color: {fg}; font-weight: 800;" + (f" background-color: {bg};" if bg else "")


def _results_table(res, key, line_col=True):
    """The judged list: every typed price, BETs first."""
    if not res:
        return
    df = pd.DataFrame([{
        "Call": bf.TIER_LABEL[r["tier"]], "Player": r["name"],
        **({"Line": r.get("line_label")} if line_col else {}),
        "Your price": _amer(r["price"]), "Our chance": _pct(r["chance"]),
        "Worth it at": _amer(r["worth"]), "Edge": f"{100 * r['edge']:+.1f} pts",
        "Stake": (f"${r['stake']:.2f}" if r.get("stake") else "—"),
        "Needs": _pct(r["break_even"])} for r in res])

    def _paint(frame):
        out = pd.DataFrame("", index=frame.index, columns=frame.columns)
        for i in frame.index:
            out.at[i, "Call"] = _call_css(res[i]["tier"])
            out.at[i, "Our chance"] = mv.chance_css(res[i]["chance"])
        return out
    st.dataframe(mv.painted(df, _paint), hide_index=True, width="stretch", key=key)


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
            if per_player:
                line = None
                st.caption("Lines differ by player for this stat — each row starts at the "
                           "line nearest a coin flip for him. Change it to your book's line.")
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

            def _start_line(r):
                if line is not None:
                    return line
                return float(mv.balanced_line((r.get("_pmfs") or {}).get(stat)))

            base = pd.DataFrame([{"Player": r["_name"], "Line": _start_line(r),
                                  "Your price": None} for r in players])
            ed_key = f"bf_ed_{sport}_{gi}_{gname}_{stat}_{side}_{line}"
            edited = st.data_editor(
                base, key=ed_key, hide_index=True, width="stretch",
                disabled=["Player"] + ([] if per_player else ["Line"]),
                column_config={
                    "Line": st.column_config.NumberColumn(step=0.5, format="%.1f"),
                    "Your price": st.column_config.NumberColumn(
                        help="Your book's American price, e.g. +700 or -150. Leave blank to skip.",
                        step=5, format="%d"),
                })

            res, ref = [], []
            for i, r in enumerate(players):
                ln = float(edited.at[i, "Line"]) if per_player else line
                ch, raw, basis = bf.chance_at(r, stat, ln, side, grp["markets"], grp["cal"])
                if ch is None or not 0 < ch < 1:
                    continue
                row = {"name": r["_name"], "chance": ch, "raw": raw, "basis": basis,
                       "worth": mm.fair_american(ch), "line": ln, "side": side,
                       "line_label": f"{side[0]}{ln:g}"}
                ref.append(row)
                j = bf.judge(ch, edited.at[i, "Your price"], _stk)
                if j:
                    res.append(dict(row, price=bf.valid_price(edited.at[i, "Your price"]), **j))
            res.sort(key=lambda x: (bf.CALL_ORDER[x["tier"]], -x["edge"]))

            if res:
                n_bet = sum(1 for x in res if x["call"] == "BET")
                st.markdown(f"**{n_bet} BET{'s' if n_bet != 1 else ''}** out of "
                            f"{len(res)} price{'s' if len(res) != 1 else ''} typed")
                _results_table(res, key=f"bf_res_{ed_key}")
                if n_bet and st.button("Add these BETs to tonight's card",
                                       key=f"bf_add_{ed_key}"):
                    k = _add_to_card(res, sport, game_label, labels[stat])
                    st.success(f"Added {k} to tonight's card (bottom of the page).")
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
                j = bf.judge(it["chance"], edl.at[i, "Your price"], _stk)
                if j:
                    lres.append(dict(it, price=bf.valid_price(edl.at[i, "Your price"]),
                                     line=0.0, side=it["name"], **j))
            lres.sort(key=lambda x: (bf.CALL_ORDER[x["tier"]], -x["edge"]))
            if lres:
                _results_table(lres, key=f"bf_lres_{lk}", line_col=False)
                if any(x["call"] == "BET" for x in lres) and st.button(
                        "Add these BETs to tonight's card", key=f"bf_ladd_{lk}"):
                    k = _add_to_card(lres, sport, game_label, "game line")
                    st.success(f"Added {k} to tonight's card.")
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

footer()
