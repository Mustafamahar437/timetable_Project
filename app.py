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

    # Top navigation (grouped)
    def page(fn, title, icon, path, default=False):
        return st.Page(fn, title=title, icon=icon, url_path=path, default=default)

    ss = st.session_state
    nav = st.navigation(
        {
            "Home": [
                page(lambda: dashboard.render(ss, db_manager), "Dashboard", ":material/home:", "dashboard", True),
            ],
            "Setup": [
                page(lambda: data_management.render(db_manager, ss), "University data", ":material/database:", "data"),
                page(lambda: rule_editor.render(ss, db_manager), "Rule editor", ":material/edit_note:", "editor"),
            ],
            "Compiler phases": [
                page(lambda: lexical_view.render(ss), "1. Lexical analysis", ":material/text_fields:", "lexical"),
                page(lambda: syntax_view.render(ss), "2. Syntax analysis", ":material/account_tree:", "syntax"),
                page(lambda: semantic_view.render(ss), "3. Semantic analysis", ":material/rule:", "semantic"),
                page(lambda: ir_view.render(ss), "4. Intermediate code", ":material/data_object:", "ir"),
                page(lambda: constraints_view.render(ss), "5. Constraints", ":material/tune:", "constraints"),
            ],
            "Output": [
                page(lambda: timetable_view.render(ss, db_manager), "6. Timetable", ":material/calendar_month:", "timetable"),
                page(lambda: error_view.render(ss), "7. Error reports", ":material/error:", "errors"),
            ],
        },
        position="top",
    )
    nav.run()

if __name__ == "__main__":
    main()
