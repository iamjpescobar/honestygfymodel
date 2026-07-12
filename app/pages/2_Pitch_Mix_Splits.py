import streamlit as st
import pandas as pd

from styles.kc_theme import inject_kc_theme, page_header, card_open, card_close, footer
from styles.table_style import plain_dark_table
from auth import render_account_sidebar
from engines.statcast_engine import (
    get_pitcher_id,
    get_pitcher_statcast
)

inject_kc_theme()
render_account_sidebar()

page_header("Pitch Mix vs RHB / LHB", "Side-by-side pitch usage comparison")

# --- INPUT ---
st.markdown(card_open("Pitcher Lookup"), unsafe_allow_html=True)
pitcher_name = st.text_input("Pitcher name", "Dean Kremer")
load = st.button("Load Pitch Mix Splits", type="primary")
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

    # --- SPLIT FUNCTION ---
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

    # --- DISPLAY ---
    c1, c2 = st.columns(2)

    with c1:
        st.markdown(card_open("Pitch Mix vs RHB"), unsafe_allow_html=True)
        st.dataframe(plain_dark_table(mix_R), width="stretch")
        st.markdown(card_close(), unsafe_allow_html=True)

    with c2:
        st.markdown(card_open("Pitch Mix vs LHB"), unsafe_allow_html=True)
        st.dataframe(plain_dark_table(mix_L), width="stretch")
        st.markdown(card_close(), unsafe_allow_html=True)

    # --- ARSENAL BIAS SUMMARY ---
    def bias_summary(mix_R, mix_L):
        if mix_R.empty or mix_L.empty:
            return pd.DataFrame()

        merged = mix_R.merge(mix_L, on="Pitch", suffixes=(" vs RHB", " vs LHB"))
        merged["Bias"] = merged["Usage % vs RHB"] - merged["Usage % vs LHB"]
        return merged.sort_values("Bias", ascending=False)

    bias_df = bias_summary(mix_R, mix_L)
    st.markdown(card_open("Arsenal Bias Summary", "Positive bias = used more against RHB"), unsafe_allow_html=True)
    st.dataframe(plain_dark_table(bias_df), width="stretch")
    st.markdown(card_close(), unsafe_allow_html=True)

footer()
