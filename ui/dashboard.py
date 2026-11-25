"""
ui/dashboard.py
===============
Dashboard overview page: 3D KPI cards and a live pipeline-status visual.
Pipeline statuses are derived from real compiler results in session state.
"""

from __future__ import annotations
import streamlit as st

from ui import theme


def _status(done: bool, failed: bool = False) -> tuple[str, str]:
    if failed:
        return "bad", "Failed"
    return ("ok", "Passed") if done else ("idle", "Not run")


def render(session_state, db_manager):
    theme.page_header(
        "Smart University Timetable Constraint Compiler",
        "Write scheduling policies in the TCS domain-specific language. They are lexed, parsed, "
        "semantically validated, lowered to IR, compiled to CP-SAT constraints and solved into a clash-free timetable.",
        tag="Compiler Construction · Semester Project",
    )

    left, right = st.columns([3, 1.4], gap="medium")
    with left:
        theme.hero_3d()
    with right:
        theme.stat_cards([
            ("", "Faculty", len(db_manager.get_teachers())),
            ("", "Courses", len(db_manager.get_courses())),
            ("", "Rooms and labs", len(db_manager.get_rooms())),
            ("", "Student groups", len(db_manager.get_student_groups())),
        ])

    st.subheader("Live compiler pipeline")
    sem = session_state.get("semantic_result")
    sol = session_state.get("solver_result")
    s = session_state
    states = [
        ("Lexical analysis", "Tokens via Lark", *_status(bool(s.get("tokens")))),
        ("Syntax analysis", "EBNF grammar → parse tree", *_status(bool(s.get("parse_tree")))),
        ("Semantic analysis", "Symbol tables & DB checks",
         *_status(bool(sem and sem.valid), bool(sem and not sem.valid))),
        ("Intermediate rep.", "Target-independent IR", *_status(bool(s.get("ir_instructions")))),
        ("Code generation", "CP-SAT constraints", *_status(bool(s.get("constraint_set")))),
        ("Solver", "Google OR-Tools",
         *_status(bool(sol and sol.success), bool(sol and not sol.success))),
    ]
    theme.pipeline_3d(states)

    with st.container(border=True):
        st.markdown("#### Quick start")
        st.markdown(
            "1. **University data** – review faculty, courses and rooms.\n"
            "2. **Rule editor** – write or upload a `.tcs` file.\n"
            "3. Press **Run full compilation pipeline**, or step through each phase.\n"
            "4. Inspect the phase pages, then export the timetable as CSV or PDF."
        )
