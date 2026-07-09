from styles.kc_theme import inject_kc_theme
inject_kc_theme()

import streamlit as st
import pandas as pd

from engines.statcast_engine import (
    get_pitcher_id,
    get_pitcher_statcast,
    build_pitch_arsenal
)

st.set_page_config(layout="wide", page_title="Pitcher Splits Dashboard")

st.title("🎯 Pitcher Split Dashboard")
st.markdown("### Platoon Performance vs RHB / LHB")
st.markdown("---")

# --- INPUT ---
pitcher_name = st.text_input("Enter Pitcher Name:", "Dean Kremer")

if st.button("Load Pitcher Splits"):
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
        st.subheader("🔥 vs RHB")
        if split_R:
            st.metric("wOBA", split_R["wOBA"])
            st.metric("xSLG", split_R["xSLG"])
            st.metric("K%", f"{split_R['K%']}%")
            st.metric("BB%", f"{split_R['BB%']}%")
            st.caption(f"Sample Size: {split_R['sample']} pitches")
        else:
            st.info("No RHB data available.")

    with c2:
        st.subheader("🔥 vs LHB")
        if split_L:
            st.metric("wOBA", split_L["wOBA"])
            st.metric("xSLG", split_L["xSLG"])
            st.metric("K%", f"{split_L['K%']}%")
            st.metric("BB%", f"{split_L['BB%']}%")
            st.caption(f"Sample Size: {split_L['sample']} pitches")
        else:
            st.info("No LHB data available.")

    st.markdown("---")

    # --- PITCH MIX SPLITS ---
    st.subheader("🎛 Pitch Usage vs RHB / LHB")

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
        st.markdown("#### ⚔️ Pitch Mix vs RHB")
        st.dataframe(mix_R, use_container_width=True)

    with c4:
        st.markdown("#### ⚔️ Pitch Mix vs LHB")
        st.dataframe(mix_L, use_container_width=True)
