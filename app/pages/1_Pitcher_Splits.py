import streamlit as st
import pandas as pd

from styles.kc_theme import inject_kc_theme, page_header, card_open, card_close, footer
from styles.table_style import plain_dark_table
from auth import render_account_sidebar
from engines.statcast_engine import (
    get_pitcher_id,
    get_pitcher_statcast,
    build_pitch_arsenal
)

inject_kc_theme()
render_account_sidebar()

page_header("Pitcher Split Dashboard", "Platoon performance vs RHB / LHB")

# --- INPUT ---
st.markdown(card_open("Pitcher Lookup"), unsafe_allow_html=True)
pitcher_name = st.text_input("Pitcher name", "Dean Kremer")
load = st.button("Load Pitcher Splits", type="primary")
st.markdown(card_close(), unsafe_allow_html=True)

if load:
    pid = get_pitcher_id(pitcher_name)
    if not pid:
        st.error("Pitcher not found.")
        st.stop()

    data = get_pitcher_statcast(pid)

    if data.empty:
        st.error("No Statcast data available.")
        st.stop()

    # --- SPLIT CALCULATIONS ---
    def calc_split(df, side):
        sub = df[df["stand"] == side]
        if sub.empty:
            return None

        return {
            "wOBA": round(sub["woba_value"].mean(), 3),
            "xSLG": round(sub["estimated_slg"].mean(), 3),
            "K%": round((sub["events"] == "strikeout").mean() * 100, 1),
            "BB%": round((sub["events"] == "walk").mean() * 100, 1),
            "sample": len(sub)
        }

    split_R = calc_split(data, "R")
    split_L = calc_split(data, "L")

    # --- DISPLAY SPLITS ---
    c1, c2 = st.columns(2)

    with c1:
        st.markdown(card_open("vs RHB"), unsafe_allow_html=True)
        if split_R:
            st.metric("wOBA", split_R["wOBA"])
            st.metric("xSLG", split_R["xSLG"])
            st.metric("K%", f"{split_R['K%']}%")
            st.metric("BB%", f"{split_R['BB%']}%")
            st.caption(f"Sample size: {split_R['sample']} pitches")
        else:
            st.info("No RHB data available.")
        st.markdown(card_close(), unsafe_allow_html=True)

    with c2:
        st.markdown(card_open("vs LHB"), unsafe_allow_html=True)
        if split_L:
            st.metric("wOBA", split_L["wOBA"])
            st.metric("xSLG", split_L["xSLG"])
            st.metric("K%", f"{split_L['K%']}%")
            st.metric("BB%", f"{split_L['BB%']}%")
            st.caption(f"Sample size: {split_L['sample']} pitches")
        else:
            st.info("No LHB data available.")
        st.markdown(card_close(), unsafe_allow_html=True)

    # --- PITCH MIX SPLITS ---
    def pitch_mix(df, side):
        sub = df[df["stand"] == side]
        if sub.empty:
            return pd.DataFrame()

        counts = sub["pitch_name"].value_counts()
        freqs = (counts / counts.sum() * 100).round(1)

        return pd.DataFrame({
            "Pitch": counts.index,
            "Usage %": freqs.values,
            "Count": counts.values
        })

    mix_R = pitch_mix(data, "R")
    mix_L = pitch_mix(data, "L")

    c3, c4 = st.columns(2)

    with c3:
        st.markdown(card_open("Pitch Mix vs RHB"), unsafe_allow_html=True)
        st.dataframe(plain_dark_table(mix_R), width="stretch")
        st.markdown(card_close(), unsafe_allow_html=True)

    with c4:
        st.markdown(card_open("Pitch Mix vs LHB"), unsafe_allow_html=True)
        st.dataframe(plain_dark_table(mix_L), width="stretch")
        st.markdown(card_close(), unsafe_allow_html=True)

footer()
