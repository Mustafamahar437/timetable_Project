"""
ui/pages/rule_editor.py
=======================
Rule Editor and Compiler Execution Control Page.
"""

from __future__ import annotations
import os
import streamlit as st
from ui import theme

from compiler.lexer import Lexer, LexicalError
from compiler.parser import Parser
from compiler.semantic import SemanticAnalyzer
from compiler.ir_generator import IRGenerator
from compiler.code_generator import CodeGenerator
from compiler.solver import TimetableSolver
from compiler.error_reporter import ErrorReporter


SAMPLE_FILES = {
    "Valid Rules (Clash-Free Sample)": "sample_rules/valid_rules.tcs",
    "Lexical Errors Demo (Invalid Tokens)": "sample_rules/invalid_tokens.tcs",
    "Syntax Errors Demo (Grammar Errors)": "sample_rules/syntax_errors.tcs",
    "Semantic Errors Demo (Invalid References)": "sample_rules/semantic_errors.tcs",
}


def render(session_state, db_manager):
    theme.page_header("✏️ Timetable Rule Editor & Compiler Pipeline", "Write scheduling rules in Domain-Specific Language (TCS), or load sample benchmark scripts.")

    col_preset, col_upload = st.columns([2, 1])

    with col_preset:
        preset_choice = st.selectbox("Load Sample Rule Benchmark:", ["-- Select Preset --"] + list(SAMPLE_FILES.keys()))
        if preset_choice != "-- Select Preset --":
            path = SAMPLE_FILES[preset_choice]
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    session_state.source_code = f.read()
                st.success(f"Loaded '{preset_choice}'")

    with col_upload:
        uploaded_file = st.file_uploader("Upload .tcs Script File", type=["tcs", "txt"])
        if uploaded_file is not None:
            session_state.source_code = uploaded_file.read().decode("utf-8")
            st.success("Uploaded file content loaded.")

    if "source_code" not in session_state or not session_state.source_code:
        # Default starting rule code
        valid_path = "sample_rules/valid_rules.tcs"
        if os.path.exists(valid_path):
            with open(valid_path, "r", encoding="utf-8") as f:
                session_state.source_code = f.read()
        else:
            session_state.source_code = "RULE NO_ROOM_CLASH;\nRULE NO_TEACHER_CLASH;\nRULE Ahmed NOT_AVAILABLE Monday 9AM;\nRULE CS101 ROOM CR1;\nRULE CS101 TEACHER Ahmed;\n"

    # Editor text area
    code_input = st.text_area(
        "TCS Source Code:",
        value=session_state.source_code,
        height=320,
        help="Rules must follow the TCS grammar (e.g., RULE CS101 ROOM CR1;)",
    )
    session_state.source_code = code_input

    st.markdown("---")
    st.subheader("⚡ Compiler Pipeline Execution")

    c_run_all, c_lex, c_parse, c_sem, c_ir, c_solv = st.columns([3, 1, 1, 1, 1, 1])

    # 1. Full Pipeline Execution
    if c_run_all.button("🚀 Run Full Compilation Pipeline", type="primary", width="stretch"):
        run_full_pipeline(session_state, db_manager)

    # 2. Step-by-step phase executions
    if c_lex.button("1. Lexer", width="stretch"):
        execute_lexer(session_state)

    if c_parse.button("2. Parser", width="stretch"):
        execute_parser(session_state)

    if c_sem.button("3. Semantic", width="stretch"):
        execute_semantic(session_state, db_manager)

    if c_ir.button("4. IR Gen", width="stretch"):
        execute_ir(session_state)

    if c_solv.button("5. Solve", width="stretch"):
        execute_solver(session_state, db_manager)

    # Status indicators
    st.markdown("### 📊 Current Pipeline State")
    p1 = "✅ Done" if session_state.get("tokens") else "⏳ Not run"
    p2 = "✅ Done" if session_state.get("parse_tree") else "⏳ Not run"
    p3 = "✅ Done" if session_state.get("semantic_result") and session_state.semantic_result.valid else ("❌ Errors" if session_state.get("semantic_result") else "⏳ Not run")
    p4 = "✅ Done" if session_state.get("ir_instructions") else "⏳ Not run"
    p5 = "✅ Done" if session_state.get("constraint_set") else "⏳ Not run"
    p6 = f"✅ {session_state.solver_result.status}" if session_state.get("solver_result") and session_state.solver_result.success else ("❌ Infeasible/Error" if session_state.get("solver_result") else "⏳ Not run")

    sc1, sc2, sc3, sc4, sc5, sc6 = st.columns(6)
    sc1.metric("1. Lexer", p1)
    sc2.metric("2. Parser", p2)
    sc3.metric("3. Semantic", p3)
    sc4.metric("4. IR Gen", p4)
    sc5.metric("5. Code Gen", p5)
    sc6.metric("6. Solver", p6)


def execute_lexer(session_state):
    lexer = Lexer()
    session_state.compiler_errors = []
    try:
        tokens = lexer.tokenize(session_state.source_code)
        session_state.tokens = tokens
        session_state.tokens_dict = lexer.get_tokens_as_dicts()
        st.success(f"Lexical Analysis passed! Generated {len(tokens)} tokens.")
        return True
    except LexicalError as le:
        session_state.tokens = []
        err = le.to_dict()
        session_state.compiler_errors = [err]
        st.error(f"Lexical Error on line {le.line}, column {le.column}: {le.message}")
        return False
    except Exception as exc:
        st.error(f"Lexer encountered unexpected error: {exc}")
        return False


def execute_parser(session_state):
    if not execute_lexer(session_state):
        return False
    parser = Parser()
    res = parser.parse(session_state.source_code)
    session_state.parse_result = res
    if res.success and res.tree is not None:
        session_state.parse_tree = res.tree
        session_state.parse_tree_repr = parser.format_tree_pretty(res.tree)
        st.success("Syntax Analysis passed! Parse tree constructed successfully.")
        return True
    else:
        reporter = ErrorReporter()
        session_state.compiler_errors = reporter.format_syntax_errors(res.errors)
        st.error(f"Syntax Analysis failed with {len(res.errors)} error(s). Check Syntax Analysis / Error Reports.")
        return False


def execute_semantic(session_state, db_manager):
    if not execute_parser(session_state):
        return False
    analyzer = SemanticAnalyzer()
    with db_manager.get_connection() as conn:
        sem_res = analyzer.analyze(session_state.parse_tree, conn)
    session_state.semantic_result = sem_res
    if sem_res.valid:
        st.success(f"Semantic Analysis passed! {sem_res.summary()}")
        return True
    else:
        reporter = ErrorReporter()
        session_state.compiler_errors = reporter.format_semantic_errors(sem_res.errors)
        st.error(f"Semantic Analysis failed with {len(sem_res.errors)} error(s). Check Semantic Analysis tab.")
        return False


def execute_ir(session_state):
    if "parse_tree" not in session_state or session_state.parse_tree is None:
        st.error("Please run Parser and Semantic Analyzer first.")
        return False
    gen = IRGenerator()
    ir_res = gen.generate(session_state.parse_tree)
    session_state.ir_instructions = ir_res.instructions
    session_state.ir_json = ir_res.json_repr
    st.success(f"Intermediate Representation generated! {len(ir_res.instructions)} IR instructions created.")
    return True


def execute_solver(session_state, db_manager):
    if "ir_instructions" not in session_state or not session_state.ir_instructions:
        if not execute_ir(session_state):
            return False
    code_gen = CodeGenerator()
    with db_manager.get_connection() as conn:
        cs = code_gen.generate_constraints(session_state.ir_instructions, conn)
        session_state.constraint_set = cs
        
        solver = TimetableSolver()
        solver_res = solver.solve(cs, conn)
        session_state.solver_result = solver_res

        if solver_res.success:
            db_manager.save_timetable([e.to_dict() for e in solver_res.timetable])
            st.success(f"Timetable solved successfully! ({solver_res.status}) - {len(solver_res.timetable)} sessions scheduled.")
            return True
        else:
            reporter = ErrorReporter()
            session_state.compiler_errors = reporter.format_solver_errors(solver_res)
            st.error(f"Solver result: {solver_res.status}. Timetable could not be satisfied.")
            return False


def run_full_pipeline(session_state, db_manager):
    st.info("Executing Complete 7-Phase Compilation Pipeline...")
    if not execute_lexer(session_state):
        return
    if not execute_parser(session_state):
        return
    if not execute_semantic(session_state, db_manager):
        return
    if not execute_ir(session_state):
        return
    execute_solver(session_state, db_manager)
