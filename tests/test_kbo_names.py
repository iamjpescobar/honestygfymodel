"""KBO starter name matching across two differently-formatted sources.

The schedule page and the pitching leaderboard write the same pitcher
three different ways, and an exact dict lookup matched none of them:

    schedule            leaderboard
    James Naile         NAILE James        (word order + case)
    Koo Chang-mo        KOO Chang Mo       (hyphen vs space)
    Choi Min-seok       CHOI Min Seok      (both at once)

So every KBO starter reported "not on the season pitching leaderboard
yet" while sitting on the leaderboard rendered directly above it, and no
strikeout projection was produced for any real game.
"""
import sys, types

st = types.ModuleType("streamlit")
def _c(**kw):
    def d(f): return f
    return d
st.cache_data = _c; sys.modules["streamlit"] = st
sys.path.insert(0, "app")

from engines.kbo_k_projection import _name_key, _find_pitcher

BOARD = {
    "NAILE James":   {"era": "3.81", "strikeouts": "94"},
    "KOO Chang Mo":  {"era": "3.87", "strikeouts": "90"},
    "CHOI Min Seok": {"era": "2.49", "strikeouts": "93"},
    "OLLER Adam":    {"era": "3.36", "strikeouts": "116"},
}

# --- the three real mismatches from the live page ---------------------
for sched, era in (("James Naile", "3.81"),
                   ("Koo Chang-mo", "3.87"),
                   ("Choi Min-seok", "2.49"),
                   ("Adam Oller", "3.36")):
    hit = _find_pitcher(BOARD, sched)
    assert hit and hit["era"] == era, f"{sched!r} did not match (got {hit})"
print("PASS: reversed order, hyphens and case all match the leaderboard")

# --- exact keys still work (cheapest path) ----------------------------
assert _find_pitcher(BOARD, "NAILE James")["era"] == "3.81"
print("PASS: an exact key still matches directly")

# --- a pitcher genuinely absent stays absent --------------------------
assert _find_pitcher(BOARD, "Chris Paddack") is None
assert _find_pitcher(BOARD, "") is None
assert _find_pitcher(BOARD, None) is None
print("PASS: a genuinely absent starter still returns None")

# --- ambiguity is a MISS, not a coin flip -----------------------------
# Two men whose names differ only by word order can't be told apart this
# way; attaching one's ERA to the other is worse than showing nothing.
AMBIG = {"KIM Min Su": {"era": "2.00"}, "SU Min Kim": {"era": "6.00"}}
assert _find_pitcher(AMBIG, "Min Su Kim") is None, \
    "an ambiguous normalised match must return None, not the first hit"
print("PASS: ambiguous match returns nothing rather than guessing")

# --- the key itself ---------------------------------------------------
assert _name_key("Koo Chang-mo") == _name_key("KOO Chang Mo")
assert _name_key("James Naile") == _name_key("NAILE James")
assert _name_key("Choi Min-seok") == _name_key("CHOI  Min   Seok")
assert _name_key("") == () and _name_key(None) == ()
print("PASS: name key is order-, case- and punctuation-insensitive")

# --- the run-total lookup uses the same rule --------------------------
kbo_view = open("app/views/KBO.py").read()
assert "from engines.kbo_k_projection import _name_key" in kbo_view, \
    "the run-total starter lookup must share the normalisation"
assert "len(hits) != 1" in kbo_view, "it must also treat ambiguity as a miss"
print("PASS: run-total starter ERA lookup shares the same matching rule")