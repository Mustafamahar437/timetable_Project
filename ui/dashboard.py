"""
ui/dashboard.py
===============
Home page: an interactive 3D map of the compiler phases. Each phase shows its
live status from the real compiler results held in session state.
"""

from __future__ import annotations
import streamlit as st

from ui import theme

_PHASES = [
    ("TCS Rules", "Input script", "#0aa346", "#22c55e",
     "The scheduling policy written in the Timetable Constraint Script language.",
     ["RULE NO_ROOM_CLASH; RULE NO_TEACHER_CLASH;", "Room, teacher, duration and preference rules", "Written in the Rule editor or loaded from sample_rules"]),
    ("Lexical Analysis", "Tokenization", "#0d4fc4", "#3b82f6",
     "Splits the script into tokens using the Lark scanner and tracks line and column for every token.",
     ["Keywords, identifiers, numbers, times", "Reports illegal characters", "Token table and distribution chart"]),
    ("Syntax Analysis", "Parsing", "#a0125f", "#ec4899",
     "Checks the tokens against the EBNF grammar and builds the parse tree.",
     ["Context-free grammar in EBNF", "Concrete syntax tree", "Reports missing semicolons and bad rule shapes"]),
    ("Semantic Analysis", "Validation", "#b34510", "#f97316",
     "Validates every name against the SQLite database and checks capacity and contradictions.",
     ["Unknown teachers, rooms, courses are rejected", "Room capacity versus enrolment", "Conflicting rules are detected"]),
    ("Intermediate Code", "IR generation", "#7a3ad4", "#a78bfa",
     "Lowers the validated rules to architecture-neutral JSON instructions.",
     ["Decouples the language from the solver", "Inspectable in the IR view"]),
    ("Constraint Generation", "Code generation", "#0e7490", "#22d3ee",
     "Turns the IR into hard feasibility invariants and soft preference objectives.",
     ["Hard: no clashes, capacity, availability", "Soft: preferred time and day"]),
    ("CP-SAT Solver", "Optimisation", "#b0132a", "#ef4444",
     "Google OR-Tools CP-SAT searches for a clash-free timetable that best satisfies the preferences.",
     ["Variables: session x day x slot x room", "Returns an optimal schedule or an infeasibility report"]),
    ("Timetable", "Output", "#15803d", "#34d399",
     "The final weekly timetable, shown as a grid and as an interactive 3D planner, with CSV and PDF export.",
     ["Faculty and room views", "Export to CSV or PDF"]),
]


def _st(done: bool, failed: bool = False) -> str:
    return "bad" if failed else ("ok" if done else "idle")


def render(session_state, db_manager):
    s = session_state
    sem, sol = s.get("semantic_result"), s.get("solver_result")
    states = [
        _st(bool(s.get("source_code"))),
        _st(bool(s.get("tokens"))),
        _st(bool(s.get("parse_tree"))),
        _st(bool(sem and sem.valid), bool(sem and not sem.valid)),
        _st(bool(s.get("ir_instructions"))),
        _st(bool(s.get("constraint_set"))),
        _st(bool(sol and sol.success), bool(sol and not sol.success)),
        _st(bool(sol and sol.success and sol.timetable)),
    ]
    phases = [
        {"n": n, "s": sub, "c": c, "pc": pc, "d": d, "k": k, "st": st_}
        for (n, sub, c, pc, d, k), st_ in zip(_PHASES, states)
    ]
    theme.pipeline_scene(phases)

    theme.stat_cards([
        ("", "Faculty", len(db_manager.get_teachers())),
        ("", "Courses", len(db_manager.get_courses())),
        ("", "Rooms and labs", len(db_manager.get_rooms())),
        ("", "Student groups", len(db_manager.get_student_groups())),
    ])

    st.markdown("#### Quick start")
    st.markdown(
        "1. **University data**: review faculty, courses and rooms.\n"
        "2. **Rule editor**: write or upload a `.tcs` file and run the pipeline.\n"
        "3. Open each phase page to inspect its output, then export the timetable."
    )
