"""NPB player names in English — fetched, never transliterated.

Kanji readings are ambiguous for personal names in a way they aren't for
ordinary words: the same characters read differently for different
people, and no rule resolves it. Generating a reading would produce a
confident, wrong, real-looking name. So the mapping is FETCHED from
npb.jp's own English leaderboards, and when those aren't available names
stay Japanese — which is at least correct.
"""
import sys, types

req = types.ModuleType("requests"); sys.modules["requests"] = req
sys.path.insert(0, ".")
import npb_precompute as npb

JP = ('<tr><td>1</td><td>田中 将大(神)</td><td>2.10</td></tr>'
      '<tr><td>2</td><td>山本 由伸(オ)</td><td>1.90</td></tr>')
EN = ('<tr><td>1</td><td>Masahiro Tanaka</td><td>2.10</td></tr>'
      '<tr><td>2</td><td>Yoshinobu Yamamoto</td><td>1.90</td></tr>')

rows_jp, rows_en = npb._leader_names(JP), npb._leader_names(EN)
assert rows_jp == ["田中 将大", "山本 由伸"], rows_jp
print("PASS: leaderboard names parsed, trailing (team) marker stripped")
assert rows_en == ["Masahiro Tanaka", "Yoshinobu Yamamoto"]
print("PASS: English leaderboard parsed in the same row order")

pages = {"jp": JP, "en": EN}
npb._get_html = lambda url: pages["en"] if "/eng/" in url else pages["jp"]
m = npb.build_name_map(2026)
assert m["田中 将大"] == "Masahiro Tanaka", m
print(f"PASS: {len(m)} names mapped by position across the two pages")

assert npb.en_name("田中 将大", m) == "Masahiro Tanaka"
assert npb.en_name("佐藤 太郎", m) == "佐藤 太郎", "unmapped names must pass through"
assert npb.en_name("", m) == ""
assert npb.en_name(None, m) is None
print("PASS: unmapped name kept in Japanese rather than guessed")

# --- row-count mismatch must NOT pair rows ----------------------------
# Positional pairing is only valid if both pages list the same players in
# the same order. A different count proves they don't.
short_en = '<tr><td>1</td><td>Masahiro Tanaka</td><td>2.10</td></tr>'
pages["en"] = short_en
m2 = npb.build_name_map(2026)
assert m2 == {}, f"mismatched row counts must not produce a mapping, got {m2}"
print("PASS: row-count mismatch skips the page rather than mispairing names")

# --- unreachable English pages -> Japanese, not a crash ---------------
def boom(url):
    if "/eng/" in url:
        raise RuntimeError("404")
    return JP
npb._get_html = boom
assert npb.build_name_map(2026) == {}
print("PASS: unreachable English pages -> empty map, names stay Japanese")

# --- no transliteration anywhere --------------------------------------
# Check IMPORTS, not prose — the module comment explains at length why
# this isn't transliteration, and matching the word failed against
# correct code. (Third time this exact test mistake has come up.)
import ast
tree = ast.parse(open("npb_precompute.py").read())
imported = {(a.asname or a.name).split(".")[0]
            for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
            for a in n.names}
for banned in ("pykakasi", "unidecode", "romkan", "cutlet", "jaconv"):
    assert banned not in imported, f"{banned} imported — readings must be fetched"
src = open("npb_precompute.py").read()
assert "SEASON_YEAR" in src, "English and Japanese pages must request the same year"
print("PASS: no transliteration library; readings come from the league itself")

# --- the view prefers English ------------------------------------------
v = open("app/views/NPB.py").read()
assert 'sp.get("name_en")' in v and '_sp_en' in v
i_en, i_jp = v.index('sp.get("name_en")'), v.index('g.get(f"{side}_starter", "")')
assert i_en < i_jp, "English name should be tried before the Japanese fallback"
print("PASS: NPB view shows the English name when one exists")
