"""
app.py
======
Main Streamlit Application for the Smart University Timetable Constraint Compiler.
Features a responsive multi-page dashboard, database auto-initialization,
and complete compiler pipeline control.
"""

from __future__ import annotations

import sys
try:
    import pandas as pd
except Exception:
    import compat.pandas_shim as pd
    sys.modules["pandas"] = pd

import streamlit as st
from database.models import DatabaseManager
from database.seed_data import seed_database

# Import UI pages
from ui import dashboard, theme
from ui.pages import (
    data_management,
    rule_editor,
    lexical_view,
    syntax_view,
    semantic_view,
    ir_view,
    constraints_view,
    timetable_view,
    error_view,
)


def main():
    st.set_page_config(
        page_title="Smart Timetable Compiler",
        page_icon="🎓",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Initialize Database and Seed Data if not already done
    db_manager = DatabaseManager("timetable.db")
    if "db_initialized" not in st.session_state:
        db_manager.initialize_db()
        # Seed if teachers table is empty
        if len(db_manager.get_teachers()) == 0:
            seed_database(db_manager)
        st.session_state.db_initialized = True

    # Initialize session state stores
    if "source_code" not in st.session_state:
        st.session_state.source_code = ""
    if "tokens" not in st.session_state:
        st.session_state.tokens = []
    if "parse_tree" not in st.session_state:
        st.session_state.parse_tree = None
    if "semantic_result" not in st.session_state:
        st.session_state.semantic_result = None
    if "ir_instructions" not in st.session_state:
        st.session_state.ir_instructions = []
    if "constraint_set" not in st.session_state:
        st.session_state.constraint_set = None
    if "solver_result" not in st.session_state:
        st.session_state.solver_result = None
    if "compiler_errors" not in st.session_state:
        st.session_state.compiler_errors = []

    # Global 3D design system
    theme.inject_css()

    # Sidebar Navigation
    st.sidebar.html(
        '<div class="brand"><div class="brand-logo">🎓</div>'
        '<div><div class="brand-t">Timetable Compiler</div>'
        '<div class="brand-s">Compiler Construction</div></div></div>'
    )

    page = st.sidebar.radio(
        "Navigation Menu",
        [
            "🏠 Dashboard",
            "📊 University Data",
            "✏️ Rule Editor",
            "🔤 1. Lexical Analysis",
            "🌳 2. Syntax Analysis",
            "✅ 3. Semantic Analysis",
            "📋 4. Intermediate Representation",
            "⚙️ 5. Generated Constraints",
            "📅 6. Generated Timetable",
            "🚨 7. Compiler Error Reports",
        ],
        index=0,
    )

    st.sidebar.markdown("---")
    st.sidebar.caption("Smart University Timetable Constraint Compiler v1.0.0")

    # Route to pages
    if page == "🏠 Dashboard":
        dashboard.render(st.session_state, db_manager)
    elif page == "📊 University Data":
        data_management.render(db_manager, st.session_state)
    elif page == "✏️ Rule Editor":
        rule_editor.render(st.session_state, db_manager)
    elif page == "🔤 1. Lexical Analysis":
        lexical_view.render(st.session_state)
    elif page == "🌳 2. Syntax Analysis":
        syntax_view.render(st.session_state)
    elif page == "✅ 3. Semantic Analysis":
        semantic_view.render(st.session_state)
    elif page == "📋 4. Intermediate Representation":
        ir_view.render(st.session_state)
    elif page == "⚙️ 5. Generated Constraints":
        constraints_view.render(st.session_state)
    elif page == "📅 6. Generated Timetable":
        timetable_view.render(st.session_state, db_manager)
    elif page == "🚨 7. Compiler Error Reports":
        error_view.render(st.session_state)


if __name__ == "__main__":
    main()
