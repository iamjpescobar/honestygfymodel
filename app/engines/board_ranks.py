"""Where does this bat sit on every OTHER board?

THE PROBLEM. A hitter can be #13 on HR Edge, #4 on Daily 13, and the
Player of the Day, and nothing on the Game Card says so. Finding out
means opening three pages and scanning for a name — which is fine when
browsing and useless when you are reading a slate out loud with a camera
running.

WHAT THIS RETURNS. One dict per slate:

    {batter_id: {"hr_edge": 13, "daily13": 4, "potd": 1}}

A board only appears for a bat that is ACTUALLY ON IT. A missing key
means "not on that board", which is different from "ranked last" and has
to stay different — a bat at #40 on HR Edge and a bat the board never
rated are not the same claim, and collapsing them is the same
missing-is-not-zero rule the rest of the site runs on.

RANKS ARE FULL-BOARD, NOT TOP-N. The published card is the top five, but
the question is "where is he", and #13 is a real answer. Reading the
board's own ordering rather than its published slice also means the
number here can never disagree with the number on that page.

CHEAP BY CONSTRUCTION. Every board is already built and cached for the
slate; this reads their existing output and builds an index. It adds no
new computation, which is why it can sit on a table that renders twenty
rows.
"""
import streamlit as st

# The order tokens render in. Not alphabetical — this is the order the
# boards matter in for a home-run read, so a row's most important badge
# is always leftmost.
BOARD_ORDER = ("hr_edge", "daily13", "potd")

BOARD_LABELS = {
    "hr_edge": "HR",
    "daily13": "H",      # "hits", not "D13" — the token has to be short
    "potd": "POTD",
}

# Ranks past this are not shown. A bat sitting 60th on a 300-bat board
# is not "on the board" in any sense a reader cares about, and a token
# for it would be noise crowding out the ones that mean something.
MAX_RANK = 25


@st.cache_data(ttl=300, max_entries=8, show_spinner=False)
def board_ranks(allow_build=False):
    """{batter_id: {board: rank}} for tonight. Never raises, never blocks.

    **allow_build=False BY DEFAULT, AND THAT IS THE WHOLE POINT.**

    The first version of this called get_hr_edge_board() and
    get_daily_13() directly, on the claim that both were "already built
    and cached for the slate". That is only true if the reader visited
    those pages first. Landing on a Game Card cold, this rebuilt the
    entire HR Edge board — ~270 rated bats — and scanned the league for
    Daily 13, before a single row of the lineup table could draw. Both
    boards cache with show_spinner=False, so the page just sat blank.

    A convenience column must never be able to block the page it
    decorates. So by default this reads only what the nightly already
    wrote to disk, which costs a file read. A caller that genuinely
    wants the live boards — the boards' own pages, where the build is
    the point — passes allow_build=True.

    A board that cannot be read is simply absent from the index rather
    than taking the whole lookup down.
    """
    index = {}

    # ---- the cheap path: today's published picks, off disk ----------
    #
    # calibration_picks writes the top five per board every slate. That
    # is fewer ranks than a live build gives, but it is the SAME list
    # the site published, it costs one file read, and it cannot hang.
    try:
        import json
        from pathlib import Path
        from datetime import datetime
        from zoneinfo import ZoneInfo
        _today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
        _rec = json.loads((Path(__file__).resolve().parents[2]
                           / "data" / "calibration.json").read_text("utf-8"))
        for _board, _key in (("hr_edge", "hr_edge"), ("daily13", "daily13"),
                             ("potd", "potd")):
            _day = (_rec.get(_key) or {}).get(_today) or {}
            for i, pick in enumerate(_day.get("picks", []), start=1):
                if pick.get("id") is None:
                    continue
                index.setdefault(str(pick["id"]), {})[_board] = i
    except Exception:
        pass

    if not allow_build:
        return index

    def _add(board, rows, id_key="id"):
        for i, r in enumerate(rows, start=1):
            if i > MAX_RANK:
                break
            pid = r.get(id_key)
            if pid is None:
                continue
            index.setdefault(str(pid), {})[board] = i

    try:
        from engines.hr_edge_board import get_hr_edge_board, cap_per_game
        rows, _meta = get_hr_edge_board()
        # THE CAPPED BOARD, because that is what the page shows. Ranking
        # against the uncapped list would put a bat at #6 here and #4 on
        # the board itself, and the reader has no way to tell which is
        # right.
        kept, _overflow = cap_per_game(rows)
        _add("hr_edge", kept)
    except Exception:
        pass

    try:
        from engines.daily_13 import get_daily_13
        rows, _meta = get_daily_13()
        _add("daily13", rows)
    except Exception:
        pass

    try:
        from engines.player_of_the_day import get_mlb_player_of_the_day
        potd = get_mlb_player_of_the_day()
        pick = potd[0] if isinstance(potd, (list, tuple)) and potd else potd
        if isinstance(pick, dict) and pick.get("id") is not None:
            index.setdefault(str(pick["id"]), {})["potd"] = 1
    except Exception:
        pass

    return index


def tokens_for(batter_id, index=None):
    """[(label, rank, board), ...] for one bat, in BOARD_ORDER."""
    if batter_id is None:
        return []
    idx = index if index is not None else board_ranks()
    got = idx.get(str(batter_id)) or {}
    return [(BOARD_LABELS[b], got[b], b) for b in BOARD_ORDER if b in got]


def token_text(batter_id, index=None):
    """'HR13 · H4 · POTD' for a table cell, or '' when he is on none.

    Empty string rather than a dash: this column is mostly blank by
    design — only a handful of bats on a slate are on any board — and a
    column of dashes reads as missing data instead of as a clean no.
    """
    out = []
    for label, rank, board in tokens_for(batter_id, index):
        out.append(label if board == "potd" else f"{label}{rank}")
    return " \u00b7 ".join(out)
