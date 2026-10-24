"""Site vs DraftKings (10-24) — the site's player-prop chances graded
against DraftKings' own, market by market (engines/book_grade, the
nightly's book_props_grade.py -> data/props/scorecard.json).

Every run saves DraftKings' line and prices AND the site's chance at that
line; after the game both are scored against the box score. A market
"beats DraftKings" only when the site's chances were closer than the
book's (de-vigged) over enough lines; otherwise "no edge proven", and the
Bet Finder caps its calls at THIN.
"""
import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, page_header
from engines import book_grade as bg
from engines import model_view as mv
from engines import slate_guard as sg
from engines.live_sync import sync_latest_button

page_header("Site vs DraftKings", "Is the site sharper than the book? Market by market",
            eyebrow="RECORD", align="left")
sync_latest_button(key="sync_site_vs_book", include_data_package=True)

LABEL = {"sog": "Shots on goal", "pts": "Points", "a": "Assists", "g": "Goals", "sv": "Saves",
         "reb": "Rebounds", "ast": "Assists", "tpm": "3-pointers", "pra": "Pts + Reb + Ast",
         "pr": "Pts + Reb", "pa": "Pts + Ast", "ra": "Reb + Ast", "q1pts": "1st-quarter points",
         "pass_yds": "Passing yards", "pass_att": "Pass attempts", "pass_cmp": "Completions",
         "pass_td": "Passing TDs", "pass_int": "Interceptions", "rush_yds": "Rushing yards",
         "carries": "Carries", "rec_yds": "Receiving yards", "rec": "Receptions",
         "scrim_yds": "Rush + rec yards"}
LEAGUE = {"nba": "NBA", "nhl": "NHL", "nfl": "NFL"}


def _label(key):
    star = key.endswith("*")
    k = key.rstrip("*")
    if k[:3] in ("q1_", "h1_"):
        base = ("1st quarter " if k.startswith("q1") else "1st half ") + \
            LABEL.get(k[3:], k[3:]).lower()
    else:
        base = LABEL.get(k, k)
    return base + (" *" if star else "")


card_ = bg.load_scorecard([sg._PUBLISHED, sg._REPO])
st.markdown(
    f'<div style="font-size:var(--lc-text-body); line-height:1.6; color:{COLOR["text"]};">'
    f'Every nightly run saves <b>DraftKings&rsquo; line and prices</b> for each player prop '
    f'and, beside it, <b>the site&rsquo;s chance</b> at that same line. After the game both are '
    f'scored against the box score. <b>Site / Book</b> = how far each one&rsquo;s chances were '
    f'from what happened (Brier score &mdash; lower is sharper; the book&rsquo;s with its cut '
    f'removed). A market needs <b>{bg.MIN_GRADED}</b> graded lines before it gets a verdict.'
    f'<br><span style="color:{COLOR["text_muted"]};">Flagged = every line where the site was '
    f'3+ points away from DraftKings, betting the side the site liked, 1 unit at '
    f'DraftKings&rsquo; own price.</span></div>', unsafe_allow_html=True)

if not card_ or not any((card_.get("leagues") or {}).values()):
    st.info("Nothing graded yet. The record started 10-24: tonight's lines are graded after the "
            "games, and the first results appear after tomorrow morning's nightly run.")
    footer()
    st.stop()

st.caption(f"Graded through {card_.get('as_of')}.")
STATUS = {"beats": ("BEATS DRAFTKINGS", "strong"), "no_edge": ("NO EDGE PROVEN", "fails"),
          "grading": ("BEING GRADED", None)}
for lg, sc in (card_.get("leagues") or {}).items():
    if not sc:
        continue
    with card(f"svb_{lg}"):
        st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                    f'{LEAGUE.get(lg, lg.upper())}</div>', unsafe_allow_html=True)
        rows, tags = [], []
        for key, x in sorted(sc.items(), key=lambda kv: -(kv[1].get("n") or 0)):
            ms = bg.market_status(card_, lg, key.rstrip("*"))
            if key.endswith("*") and ms.get("key") != key:
                ms = dict(ms, status="grading" if (x.get("n") or 0) < bg.MIN_GRADED else (
                    "beats" if ((x.get("verdict") or {}).get("verdict") == "beats")
                    else "no_edge"))
            f = x.get("flagged") or {}
            lab, tag = STATUS[ms["status"]]
            tags.append(tag)
            rows.append({"Market": _label(key), "Graded": x.get("n"),
                         "Site": x.get("brier_site"), "Book": x.get("brier_book"),
                         "Verdict": lab + (f" (z={(x.get('verdict') or {}).get('z')})"
                                           if ms["status"] != "grading" else
                                           f" ({x.get('n')} of {bg.MIN_GRADED})"),
                         "Flagged": f.get("n"),
                         "Hit": (f"{100 * f['hits'] / f['n']:.0f}%" if f.get("n") else "—"),
                         "Units": f.get("units"),
                         "ROI": (f"{100 * f['roi']:+.1f}%" if f.get("roi") is not None
                                 else "—")})

        def _paint(frame):
            o_ = pd.DataFrame("", index=frame.index, columns=frame.columns)
            for k_ in frame.index:
                t = tags[k_]
                if t:
                    _n, fg_, bg_, _bd = mv.TRUST_STYLE.get(
                        "beats" if t == "strong" else "fails", mv.TRUST_STYLE[None])
                    o_.at[k_, "Verdict"] = (f"color: {fg_}; background-color: {bg_}; "
                                            f"font-weight: 700;")
            return o_
        st.dataframe(mv.painted(pd.DataFrame(rows), _paint), hide_index=True, width="stretch",
                     key=f"svb_tab_{lg}")
st.caption("* = DraftKings posted only the over at that line (their NFL main lines come with "
           "no price), so its cut is estimated at the 7% measured on their two-sided NHL / NBA "
           "markets; graded apart from the rest. A small sample swings: wait for the verdict "
           "before leaning on a market.")
footer()
