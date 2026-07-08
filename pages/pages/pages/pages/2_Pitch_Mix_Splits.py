import streamlit as st
import pandas as pd

from engines.statcast_engine import (
    get_pitcher_id,
    get_pitcher_statcast
)

st.set_page_config(layout="wide", page_title="Pitch Mix Splits")

st.title("🎛 Pitch Mix vs RHB / LHB")
st.markdown("### Side-by-side pitch usage comparison")
st.markdown("---")

# --- INPUT ---
pitcher_name = st.text_input("Enter Pitcher Name:", "Dean Kremer")

if st.button("Load Pitch Mix Splits"):
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
        st.subheader("⚔️ Pitch Mix vs RHB")
        st.dataframe(mix_R, use_container_width=True)

    with c2:
        st.subheader("⚔️ Pitch Mix vs LHB")
        st.dataframe(mix_L, use_container_width=True)

    st.markdown("---")

    # --- OPTIONAL: Arsenal Bias Summary ---
    st.subheader("🎯 Arsenal Bias Summary")

    def bias_summary(mix_R, mix_L):
        if mix_R.empty or mix_L.empty:
            return pd.DataFrame()

        merged = mix_R.merge(mix_L, on="Pitch", suffixes=(" vs RHB", " vs LHB"))
        merged["Bias"] = merged["Usage % vs RHB"] - merged["Usage % vs LHB"]
        return merged.sort_values("Bias", ascending=False)

    bias_df = bias_summary(mix_R, mix_L)
    st.dataframe(bias_df, use_container_width=True)
