"""
ui/pages/ir_view.py
===================
Phase 4: Intermediate Representation (IR) Visualization page.
Displays architecture-neutral IR instructions, grouped breakdowns, and JSON export.
"""

from __future__ import annotations
import json
import streamlit as st
from ui import theme
import pandas as pd


def render(session_state):
    theme.page_header("📋 Phase 4: Intermediate Representation (IR)", "Inspect the architecture-neutral intermediate code generated from the validated parse tree.")

    instructions = session_state.get("ir_instructions", [])
    ir_json = session_state.get("ir_json", "[]")

    if not instructions:
        st.info("No Intermediate Representation generated yet. Run IR Generation from the **Rule Editor** page.")
        return

    st.success(f"Generated **{len(instructions)} IR Instructions**.")

    tab_table, tab_json, tab_groups = st.tabs([
        "📊 IR Instructions Table", 
        "📝 Raw IR JSON Code", 
        "🗂️ Grouped Breakdown"
    ])

    with tab_table:
        records = [instr.to_dict() for instr in instructions]
        df_ir = pd.DataFrame(records)
        st.dataframe(df_ir, width="stretch", height=450)

    with tab_json:
        st.markdown("#### Serialized IR Data Structure:")
        try:
            parsed_json = json.loads(ir_json)
            st.json(parsed_json)
        except Exception:
            st.code(ir_json, language="json")

    with tab_groups:
        st.subheader("Instructions by Category")
        type_counts = {}
        for instr in instructions:
            type_counts[instr.type] = type_counts.get(instr.type, 0) + 1
        
        col1, col2 = st.columns(2)
        with col1:
            for itype, count in type_counts.items():
                st.write(f"• **`{itype}`**: {count} instruction(s)")
        with col2:
            st.info("The Intermediate Representation separates the front-end language syntax from the back-end constraint solver.")
