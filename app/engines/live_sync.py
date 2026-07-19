"""
"Sync latest" — the explicit make-it-live-NOW control, shared by every
page that depends on live or nightly data.

Two levels, chosen per page:

- Cache sync (always): clears every st.cache_data entry so schedules,
  lineups, weather, projections, and boards refetch from their sources
  on the spot. st.cache_data is shared across sessions, so one press
  refreshes for everyone — that's the point.

- Data-package sync (include_data_package=True): FIRST re-downloads
  tonight's published nightly data build (the same tarball
  fetch_data.py pulls at deploy time) and extracts it in place, THEN
  clears caches. This is what surfaces players added by the latest
  pipeline run WITHOUT waiting for a redeploy — the reason some WNBA
  players were missing: the running site was serving the data file
  from its last deploy, not the last pipeline run. Used by the pages
  whose data lives in the package (WNBA, KBO, NPB, Daily 13).

The download is best-effort and honest: if it fails, the page says so
and still clears caches; if the build hasn't changed, it says that too
instead of pretending something updated.
"""
import json
import os
import sys

import streamlit as st

_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _manifest_stamp():
    try:
        with open(os.path.join(_APP_DIR, "data", "statcast", "manifest.json")) as f:
            return json.load(f).get("generated_at_utc")
    except Exception:
        return None


def sync_latest_button(key: str, include_data_package: bool = False,
                       label: str = "\u27f3 Sync latest") -> None:
    help_txt = (
        "Re-pulls tonight's published data build (rosters, game logs) and clears every "
        "cached value, so this page rebuilds from the freshest data that exists."
        if include_data_package else
        "Clears every cached value so schedules, lineups, weather, and boards refetch "
        "from their live sources right now."
    )
    if st.button(label, key=key, help=help_txt):
        if include_data_package:
            before = _manifest_stamp()
            with st.spinner("Pulling tonight's latest data build\u2026"):
                try:
                    if _APP_DIR not in sys.path:
                        sys.path.insert(0, _APP_DIR)
                    import fetch_data
                    fetch_data.main()
                except Exception as e:
                    st.warning(f"Couldn't re-pull the data build ({e}) \u2014 cleared caches only.")
            after = _manifest_stamp()
            if after and after != before:
                st.toast(f"New data build loaded (built {after}).")
            elif after:
                st.toast("Already on the latest data build \u2014 caches cleared anyway.")
        st.cache_data.clear()
        st.rerun()
