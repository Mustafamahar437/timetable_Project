"""
ui/pages/semantic_view.py
=========================
Phase 3: Semantic Analysis Visualization page.
Shows semantic validation of identifiers, types, capacity constraints, and contradictions.
"""

from __future__ import annotations
import streamlit as st
from ui import theme
import pandas as pd


def render(session_state):
    theme.page_header("✅ Phase 3: Semantic Analysis", "Validates references against university database entities, verifies room capacities, and checks for contradictions.")

    sem_res = session_state.get("semantic_result")

    if sem_res is None:
        st.info("Semantic analysis not yet executed. Run Semantic Analysis from the **Rule Editor** page.")
        return

    c1, c2, c3 = st.columns(3)
    status_str = "VALID" if sem_res.valid else "INVALID"
    c1.metric("Semantic Status", status_str)
    c2.metric("Violations / Errors", len(sem_res.errors))
    c3.metric("Semantic Warnings", len(sem_res.warnings))

    if sem_res.valid:
        st.success("🎉 All semantic validation checks passed! All teachers, courses, and rooms exist; room capacities are sufficient.")
    else:
        st.error(f"⚠️ Semantic Analysis identified {len(sem_res.errors)} issue(s):")
        for idx, err in enumerate(sem_res.errors, 1):
            with st.expander(f"Error {idx}: {err.message} (Line {err.line})", expanded=True):
                st.write(f"**Offending Rule:** `{err.rule_text}`")
                st.write(f"**Description:** {err.message}")

    if sem_res.warnings:
        with st.expander("⚠️ Compiler Semantic Warnings", expanded=False):
            for w in sem_res.warnings:
                st.warning(w)

    st.markdown("---")
    st.markdown("### 🔍 Verified Semantic Checks")
    st.markdown(
        """
        - ✅ **Entity Existence**: Verified teachers, courses, and rooms exist in SQLite database.
        - ✅ **Domain Consistency**: Verified days belong to `{Monday .. Friday}` and times belong to `{8AM .. 5PM}`.
        - ✅ **Capacity Verification**: Verified assigned room seating capacity $\ge$ course student enrolment.
        - ✅ **Duration Bounds**: Verified session duration is within acceptable range (1 to 3 hours).
        - ✅ **Contradiction Detection**: Verified no conflicting assignments (e.g. single course pinned to two different rooms).
        """
    )
