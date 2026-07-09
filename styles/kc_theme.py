def inject_kc_theme():
    import streamlit as st

    st.markdown(
        """
        <style>
        body {
            background-color: #050812;
            color: #e5e5e5;
        }

        .main-header {
            text-align: center;
            font-size: 32px;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin-bottom: 0.5rem;
        }
        .sub-header {
            text-align: center;
            font-size: 16px;
            color: #a0a0ff;
            margin-bottom: 1.5rem;
        }

        div[data-testid="stDataFrame"] table {
            background-color: #0b0f1a;
            border-collapse: collapse;
        }
        div[data-testid="stDataFrame"] table td,
        div[data-testid="stDataFrame"] table th {
            padding: 4px 6px;
            border-bottom: 1px solid #1b2233;
            font-size: 12px;
        }

        .arsenal-card {
            background: #0b0f1a;
            border-radius: 12px;
            padding: 16px 18px;
            box-shadow: 0 0 18px rgba(125, 60, 255, 0.35);
            border: 1px solid #1f2640;
            margin-bottom: 20px;
        }
        .arsenal-title {
            font-weight: 700;
            font-size: 18px;
            margin-bottom: 8px;
            color: #e5e5ff;
        }
        .arsenal-subtitle {
            font-size: 13px;
            color: #b0b0d0;
            margin-bottom: 10px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
