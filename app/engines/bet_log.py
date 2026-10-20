"""
Bet log (10-20) — every bet you actually place, at the price you
actually got, and whether it hit. The one test no backtest can run: does
the model beat YOUR book, on the bets YOU pick?

WHAT A BET IS
-------------
{"id", "placed", "sport", "kind": "single" | "parlay" | "sgp", "desc",
 "legs": [str], "chance": our chance 0-1, "price": American, "stake": $,
 "tier": the call when you placed it, "result": None | "won" | "lost" |
 "push", "close": the book's price at game time (optional), "settled"}

WHAT IT MEASURES (summary)
--------------------------
  record, staked, profit, ROI — plain money;
  expected wins vs actual — the sum of our chances on the graded bets
      against how many hit (are our chances honest on YOUR bets?);
  model vs book — the same bets scored twice on squared error: our
      chance, and the book's break-even chance at your price
      (mm.paired_verdict). "beats" there is the model beating your book;
  closing line — when you type the price at game time: how many points
      of chance you beat the close by (the sharpest single sign of a good
      bettor — it shows up long before the profit does).
Missing is never zero: an open bet counts nowhere; a bet with no close
is left out of the closing-line number, not scored as 0.

WHERE IT LIVES
--------------
The site runs on a server whose disk is wiped on every deploy, so the
log is a JSON file in a GitHub repo, written through GitHub's contents
API with a token the server holds (env BETLOG_TOKEN; BETLOG_REPO, default
this repo; one file per signed-in user, data/bets/<user>.json). The
commit message carries [skip render] [skip ci] so a bet never redeploys
the site or runs the nightly. No token -> the page keeps the log for the
session and offers it as a download / upload.

requests only inside GitHubStore; no streamlit.
"""
import base64
import hashlib
import json
import os
import re
from datetime import datetime

from engines import model_math as mm

RESULTS = ("won", "lost", "push")
KINDS = ("single", "parlay", "sgp")
MIN_VERDICT_N = 30
DEFAULT_REPO = "iamjpescobar/honestygfymodel"
API = "https://api.github.com"


def decimal(price):
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if -100 < p < 100:
        return None
    return 1.0 + (p / 100.0 if p > 0 else 100.0 / -p)


def break_even(price):
    d = decimal(price)
    return None if d is None else 1.0 / d


def new_bet(sport, kind, desc, chance, price, stake, tier=None, legs=None, now=None):
    """One bet as the log keeps it; None if the price is not a real one."""
    if decimal(price) is None:
        return None
    placed = (now or datetime.now()).strftime("%Y-%m-%d %H:%M")
    bid = hashlib.sha1(f"{placed}|{sport}|{desc}|{price}".encode()).hexdigest()[:10]
    return {"id": bid, "placed": placed, "sport": sport,
            "kind": kind if kind in KINDS else "single", "desc": desc,
            "legs": list(legs or []), "chance": None if chance is None else float(chance),
            "price": int(round(float(price))), "stake": float(stake or 0.0),
            "tier": tier, "result": None, "close": None, "settled": None}


def settle(bet, result, close=None, now=None):
    """A copy of the bet graded (result None re-opens it)."""
    b = dict(bet)
    b["result"] = result if result in RESULTS else None
    b["settled"] = (now or datetime.now()).strftime("%Y-%m-%d %H:%M") if b["result"] else None
    if close is not None:
        b["close"] = int(round(float(close))) if decimal(close) else None
    return b


def profit(bet):
    """$ won or lost; None while open."""
    r = bet.get("result")
    if r == "won":
        return bet["stake"] * (decimal(bet["price"]) - 1.0)
    if r == "lost":
        return -bet["stake"]
    if r == "push":
        return 0.0
    return None


def clv(bet):
    """Points of chance you beat the closing price by (positive = you got
    a better price than the close); None without a close."""
    a, c = break_even(bet.get("price")), break_even(bet.get("close"))
    if a is None or c is None:
        return None
    return c - a


def summary(bets, where=None):
    """The numbers the page shows, for every bet passing `where`."""
    bs = [b for b in bets or [] if where is None or where(b)]
    graded = [b for b in bs if b.get("result") in RESULTS]
    decided = [b for b in graded if b["result"] != "push"]
    staked = sum(b["stake"] for b in graded)
    pnl = sum(profit(b) for b in graded)
    with_ch = [b for b in decided if b.get("chance") is not None]
    out = {"n": len(bs), "open": len(bs) - len(graded), "graded": len(graded),
           "won": sum(1 for b in graded if b["result"] == "won"),
           "lost": sum(1 for b in graded if b["result"] == "lost"),
           "push": sum(1 for b in graded if b["result"] == "push"),
           "staked": round(staked, 2), "profit": round(pnl, 2),
           "roi": round(pnl / staked, 4) if staked else None,
           "expected_wins": round(sum(b["chance"] for b in with_ch), 2) if with_ch else None,
           "wins_with_chance": sum(1 for b in with_ch if b["result"] == "won"),
           "n_with_chance": len(with_ch)}
    # the model against the book, on the same bets (squared error)
    ml = [(b["chance"] - (1 if b["result"] == "won" else 0)) ** 2 for b in with_ch]
    bl = [(break_even(b["price"]) - (1 if b["result"] == "won" else 0)) ** 2 for b in with_ch]
    out["vs_book"] = mm.paired_verdict(ml, bl) if len(ml) >= 2 else None
    out["vs_book_ready"] = len(ml) >= MIN_VERDICT_N
    cl = [clv(b) for b in bs]
    cl = [x for x in cl if x is not None]
    out["clv_n"] = len(cl)
    out["clv"] = round(sum(cl) / len(cl), 4) if cl else None
    out["clv_beat"] = sum(1 for x in cl if x > 0)
    return out


def by(bets, key):
    """{value: summary} split by a field (sport, kind, tier)."""
    vals = sorted({str(b.get(key)) for b in bets or []})
    return {v: summary(bets, lambda b, v=v: str(b.get(key)) == v) for v in vals}


def upsert(bets, bet):
    """The list with this bet added or replaced (by id), newest first."""
    rest = [b for b in bets or [] if b.get("id") != bet.get("id")]
    return sorted([bet] + rest, key=lambda b: b.get("placed") or "", reverse=True)


def remove(bets, bid):
    return [b for b in bets or [] if b.get("id") != bid]


def parse(text):
    """Bets from an uploaded JSON file (list, or {"bets": list}); [] if not."""
    try:
        x = json.loads(text)
    except (TypeError, ValueError):
        return []
    x = x.get("bets") if isinstance(x, dict) else x
    return [b for b in x or [] if isinstance(b, dict) and b.get("id") and b.get("price")]


def dump(bets):
    return json.dumps({"bets": bets}, indent=1)


def user_slug(username):
    s = re.sub(r"[^a-z0-9_-]+", "-", str(username or "guest").lower()).strip("-")
    return s or "guest"


class GitHubStore:
    """The log as one JSON file in a GitHub repo (contents API)."""

    def __init__(self, token, repo, path, _http=None):
        self.token, self.repo, self.path = token, repo, path
        self._http = _http

    def _req(self):
        if self._http is None:
            import requests
            self._http = requests
        return self._http

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json"}

    def load(self):
        """(bets, sha). sha None = no file yet. Raises on a real failure."""
        r = self._req().get(f"{API}/repos/{self.repo}/contents/{self.path}",
                            headers=self._headers(), timeout=15)
        if r.status_code == 404:
            return [], None
        r.raise_for_status()
        js = r.json()
        return parse(base64.b64decode(js.get("content") or "").decode("utf-8")), js.get("sha")

    def save(self, bets, sha, what="update"):
        """New sha. A 409 / 422 means someone wrote first: reload, retry."""
        body = {"message": f"bet log: {what} [skip render] [skip ci]",
                "content": base64.b64encode(dump(bets).encode("utf-8")).decode("ascii")}
        if sha:
            body["sha"] = sha
        r = self._req().put(f"{API}/repos/{self.repo}/contents/{self.path}",
                            headers=self._headers(), json=body, timeout=15)
        r.raise_for_status()
        return (r.json().get("content") or {}).get("sha")


def store_for(username, env=None):
    """The user's GitHub store, or None when the server holds no token."""
    env = os.environ if env is None else env
    tok = env.get("BETLOG_TOKEN")
    if not tok:
        return None
    return GitHubStore(tok, env.get("BETLOG_REPO") or DEFAULT_REPO,
                       f"data/bets/{user_slug(username)}.json")
