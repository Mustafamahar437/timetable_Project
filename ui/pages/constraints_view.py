"""
ui/pages/constraints_view.py
============================
Phase 5: Generated Constraints View page.
Displays Hard and Soft constraints prepared for the Google OR-Tools CP-SAT solver.
"""

from __future__ import annotations
import streamlit as st
from ui import theme
import pandas as pd


def render(session_state):
    theme.page_header("⚙️ Phase 5: Generated Solver Constraints", "Examine the mathematical constraints translated from the IR for the Google OR-Tools CP-SAT solver.")

    cs = session_state.get("constraint_set")

    if cs is None:
        st.info("No constraints generated yet. Run Code Generation or Solve from the **Rule Editor** page.")
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("🔒 Hard Constraints", len(cs.hard_constraints))
    c2.metric("💡 Soft Constraints", len(cs.soft_constraints))
    c3.metric("Solver Config Keys", len(cs.solver_config))

    tab_hard, tab_soft, tab_config = st.tabs([
        "🔒 Hard Constraints (Must Satisfy)", 
        "💡 Soft Constraints (Penalized)", 
        "🛠️ Solver Configuration & Domains"
    ])

    with tab_hard:
        st.subheader("Hard Feasibility Invariants")
        if cs.hard_constraints:
            df_hard = pd.DataFrame(cs.hard_constraints)
            st.dataframe(df_hard, width="stretch", height=400)
        else:
            st.info("No hard constraints emitted.")

    with tab_soft:
        st.subheader("Soft Optimization Constraints")
        if cs.soft_constraints:
            df_soft = pd.DataFrame(cs.soft_constraints)
            st.dataframe(df_soft, width="stretch", height=400)
        else:
            st.info("No soft constraints defined.")

    with tab_config:
        st.subheader("Solver Domain Bounds & Search Parameters")
        st.json(cs.solver_config)
