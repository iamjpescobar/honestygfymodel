#!/usr/bin/env python3
"""Say LIKELY when the starter is inferred, START when it is reported.

Edits accumulate per file; the script verifies what landed ON DISK.
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
buf = {}
applied = []


def edit(relpath, old, new, label):
    s = buf.get(relpath)
    if s is None:
        s = (ROOT / relpath).read_text()
    if old not in s:
        sys.exit(f"ANCHOR NOT FOUND ({label}) - nothing written.")
    if s.count(old) != 1:
        sys.exit(f"ANCHOR NOT UNIQUE ({label}) - nothing written.")
    buf[relpath] = s.replace(old, new, 1)
    applied.append(label)


P = "app/engines/wnba_props.py"
V = "app/views/WNBA.py"

# ----------------------------------------------------------------------
# 1. Split "announced" out so a caller can tell which answer it got.
#    Also merges the accidental double docstring.
# ----------------------------------------------------------------------
edit(P, '''def likely_starters(players, today=None):
    """See below — announced lineups override the minutes inference."""
    """Set of pids most likely to start for this team tonight.

    Returns an EMPTY SET when minutes can't be read for anyone, so callers
    treat it as "unknown" and show everyone rather than hiding a whole
    roster behind a failed inference.
    """
    # ANNOUNCED lineups win. When ESPN has posted who's starting, use it
    # rather than guessing from minutes — the inference exists only for
    # the hours before that's published.
    announced = {p.get("pid") or p.get("id")
                 for p in players or [] if p.get("today_starter") is True}
    if announced:
        return announced''', '''def announced_starters(players):
    """Pids ESPN has actually POSTED as starting tonight, else empty set.

    Split out of likely_starters so a caller can tell a REPORTED lineup
    from an INFERRED one. The set that function returns looks identical
    either way, which is how the Role column ended up printing "START"
    over a minutes guess.

    Expect this to be empty for the WNBA. The roster probe established
    that ESPN does not publish today_starter for this league, so the
    announced branch is dead in practice. It stays because the field
    exists and may begin arriving, and because a UI that says LIKELY
    needs a defined way to say START on the day it does.

    Both this and likely_starters read the flag through here, so the two
    can never drift about what counts as announced.
    """
    return {p.get("pid") or p.get("id")
            for p in players or [] if p.get("today_starter") is True}


def likely_starters(players, today=None):
    """Set of pids most likely to start for this team tonight.

    Announced lineups override the minutes inference. Returns an EMPTY
    SET when minutes can't be read for anyone, so callers treat it as
    "unknown" and show everyone rather than hiding a whole roster behind
    a failed inference.

    A caller that LABELS this result must ask announced_starters() which
    kind of answer it got. The pids alone cannot tell you, and printing
    a guess with the confidence of a fact is the one thing this app is
    built not to do.
    """
    # ANNOUNCED lineups win. When ESPN has posted who's starting, use it
    # rather than guessing from minutes — the inference exists only for
    # the hours before that's published.
    announced = announced_starters(players)
    if announced:
        return announced''', "wnba_props: announced_starters + merged docstring")

# ----------------------------------------------------------------------
# 2. The view asks which kind of answer it got.
# ----------------------------------------------------------------------
edit(V, '''from engines.wnba_props import (availability as _availability,
                                likely_starters as _likely_starters,
                                league_reference_date as _ref_date)''',
     '''from engines.wnba_props import (announced_starters as _announced_starters,
                                availability as _availability,
                                likely_starters as _likely_starters,
                                league_reference_date as _ref_date)''',
     "WNBA.py: import announced_starters")

edit(V, '''                            _starters = _likely_starters(plist, today=_REF)''',
     '''                            _starters = _likely_starters(plist, today=_REF)
                            # Same set either way, so ask separately which
                            # one this is. Drives START vs LIKELY below.
                            _announced = bool(_announced_starters(plist))''',
     "WNBA.py: capture provenance")

# ----------------------------------------------------------------------
# 3. The label tells the truth.
# ----------------------------------------------------------------------
edit(V, '''                                    "Role": ("OUT" if not _ok
                                             else "START" if _is_starter
                                             else ("BENCH" if _starters else "")),''',
     '''                                    # START is a REPORTED lineup. LIKELY is
                                    # this app's own inference from recent
                                    # minutes, and for the WNBA it is always
                                    # the inference — ESPN publishes no
                                    # starter flag for this league, so the
                                    # announced branch never fires today.
                                    #
                                    # It said START regardless. Every badge
                                    # on the site was a guess wearing the
                                    # word for a fact, on the one page whose
                                    # argument is that it keeps those apart.
                                    # The inference is useful and stays; it
                                    # just says what it is now, and upgrades
                                    # itself the day ESPN starts posting
                                    # lineups.
                                    "Role": ("OUT" if not _ok
                                             else ("START" if _announced
                                                   else "LIKELY") if _is_starter
                                             else ("BENCH" if _starters else "")),''',
     "WNBA.py: START vs LIKELY")

edit(V, '''                            _order = {"START": 0, "": 1, "BENCH": 1, "OUT": 2}''',
     '''                            _order = {"START": 0, "LIKELY": 0,
                                      "": 1, "BENCH": 1, "OUT": 2}''',
     "WNBA.py: sort LIKELY with START")

for relpath, content in buf.items():
    (ROOT / relpath).write_text(content)
for label in applied:
    print(f"patched: {label}")

_p = (ROOT / P).read_text()
_v = (ROOT / V).read_text()
checks = {
    "announced_starters defined": "def announced_starters(players):" in _p,
    "likely_starters uses it": "announced = announced_starters(players)" in _p,
    "double docstring gone": '"""See below — announced lineups' not in _p,
    "view imports it": "announced_starters as _announced_starters" in _v,
    "provenance captured": "_announced = bool(_announced_starters(plist))" in _v,
    "LIKELY label present": '"LIKELY") if _is_starter' in _v,
    "sort keeps START first": '_order = {"START": 0, "LIKELY": 0,' in _v,
}
print()
for name, ok in checks.items():
    print(f"  {'OK  ' if ok else 'FAIL'} {name}")
print("done" if all(checks.values()) else "INCOMPLETE - tell Claude")
