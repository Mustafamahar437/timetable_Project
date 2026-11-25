"""
ui/pages/lexical_view.py
========================
Phase 1: Lexical Analysis Visualization page.
Displays tokens, lines, columns, type distribution, and token statistics.
"""

from __future__ import annotations
import streamlit as st
from ui import theme
import pandas as pd
import plotly.express as px


def render(session_state):
    theme.page_header("🔤 Phase 1: Lexical Analysis", "Examine the generated token stream produced by the Lark-based lexical analyzer.")

    tokens_dict = session_state.get("tokens_dict", [])

    if not tokens_dict:
        st.info("No tokens generated yet. Go to **Rule Editor** and click **Run Pipeline** or **1. Lexer**.")
        return

    st.success(f"Successfully tokenized: **{len(tokens_dict)} total tokens** recognized.")

    df = pd.DataFrame(tokens_dict)

    # Metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Tokens", len(df))
    c2.metric("Distinct Types", df["type"].nunique() if "type" in df else 0)
    c3.metric("Total Lines Scanned", df["line"].max() if "line" in df else 0)
    keywords_cnt = df[df["type"] == "KEYWORD"].shape[0] if "type" in df else 0
    c4.metric("Keywords", keywords_cnt)

    # Chart & Table
    tab_table, tab_chart = st.tabs(["📋 Token Stream Table", "📊 Token Type Distribution"])

    with tab_table:
        st.dataframe(df, width="stretch", height=450)

    with tab_chart:
        if "type" in df and not df.empty:
            type_counts = df["type"].value_counts().reset_index()
            type_counts.columns = ["Token Type", "Count"]
            fig = px.bar(
                type_counts,
                x="Token Type",
                y="Count",
                color="Token Type",
                title="Lexical Token Breakdown",
                text="Count"
            )
            st.plotly_chart(fig, width="stretch")
