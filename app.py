import streamlit as st, requests as r, pandas as pd, numpy as np
from datetime import datetime
from pybaseball import statcast_pitcher, playerid_lookup

st.set_page_config(layout="wide")
st.markdown("<style>.block-container{padding:1rem 0.4rem!important;}.stDataFrame div[data-testid='stTable']{font-size:11px!important;}</style>", unsafe_allow_html=True)
st.title("Los Cappers Lab 🧪")
st.markdown("### 💥 The Advanced S.L.A.M. Index Analytics Hub\n---")

TIDS = {"Philadelphia Phillies": 143, "Kansas City Royals": 118, "Houston Astros": 117, "Washington Nationals": 120}

@st.cache_data(ttl=60)
def get_games():
    try:
        res = r.get(f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={datetime.today().strftime('%Y-%m-%d')}&hydrate=probablePitcher").json()
        gl = res.get('dates', [{}])[0].get('games', [])
        return [{"id":g['gamePk'],"away":g['teams']['away']['team']['name'],"home":g['teams']['home']['team']['name'],
                 "away_p":g['teams']['away'].get('probablePitcher',{}).get('fullName','Cristopher Sanchez'),
                 "home_p":g['teams']['home'].get('probablePitcher',{}).get('fullName','Noah Cameron')} for g in gl]
    except:
        return [{"id":1,"away":"Philadelphia Phillies","home":"Kansas City Royals","away_p":"Cristopher Sanchez","home_p":"Noah Cameron"}]

@st.cache_data(ttl=300)
def get_roster(tname):
    tid = TIDS.get(tname, 118)
    try:
        ro = r.get(f"https://statsapi.mlb.com/api/v1/teams/{tid}/roster?rosterType=active").json().get('roster', [])
        return [{"name":p['person']['fullName'],"hand":"LHB" if p['person'].get('batSide',{}).get('code')=='L' else "RHB"} for p in ro if p.get('position',{}).get('code')!='1']
    except:
        return [{"name":"Jac Caglianone","hand":"LHB"},{"name":"Salvador Perez","hand":"RHB"},{"name":"Michael Massey","hand":"LHB"}]

def hl_slam(row):
    s = [''] * len(row)
    try:
        if float(row['💥 SLAM Index']) >= 70.0: s = ['background-color:#0f401b;color:#a3ffb4;font-weight:bold;']*len(row)
        elif float(row['💥 SLAM Index']) < 45.0: s = ['background-color:#3d1414;color:#ffb3b3;']*len(row)
    except: pass
    return s

games = get_games()
if games:
    g_opts = [f"{g['away']} ({g['away_p']}) @ {g['home']} ({g['home_p']})" for g in games]
    sel_g = games[st.selectbox("Select Matchup:", range(len(g_opts)), format_func=lambda x:g_opts[x])]
    pitcher = st.radio("Target Pitcher:", [sel_g['away_p'], sel_g['home_p']])
    opp_team = sel_g['home'] if pitcher == sel_g['away_p'] else sel_g['away']
    
    st.write(f"## 📋 Pro-Report: {pitcher}")
    p_throws = "R"
    try:
        fn = pitcher.split(" ")
        id_df = playerid_lookup(fn[-1], fn[0])
        if not id_df.empty:
            p_data = statcast_pitcher('2026-04-01', '2026-10-01', id_df.iloc[0]['key_mlbam'])
            if p_data is not None and not p_data.empty: p_throws = p_data['p_throws'].iloc[0]
    except: pass

    st.markdown(f
