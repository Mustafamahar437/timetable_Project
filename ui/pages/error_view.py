"""
ui/pages/error_view.py
======================
Phase 7: Comprehensive Compiler Error Reporting and Diagnostics Page.
"""

from __future__ import annotations
import streamlit as st
from ui import theme
import pandas as pd
from compiler.error_reporter import ErrorReporter


def render(session_state):
    theme.page_header("🚨 Phase 7: Compiler Error Diagnostics & Reports", "Real-time diagnostics across all compiler phases: Lexical, Syntax, Semantic, and Constraint Solver.")

    all_errors = session_state.get("compiler_errors", [])

    if not all_errors:
        st.success("🎉 No Compiler Errors Detected! Your rules compiled and executed cleanly.")
        return

    st.error(f"⚠️ Compiler encountered **{len(all_errors)} error(s)**:")

    reporter = ErrorReporter()
    grouped = {}
    for err in all_errors:
        p = err.get("phase", "Compiler")
        grouped.setdefault(p, []).append(err)

    # Render error cards grouped by phase
    for phase_name, errs in grouped.items():
        st.subheader(f"{phase_name} Phase Diagnostics ({len(errs)})")
        for idx, err in enumerate(errs, 1):
            line_str = f"Line {err.get('line', '?')}" if err.get("line") else "Global"
            col_str = f", Col {err.get('column')}" if err.get("column") else ""
            with st.expander(f"❌ [{phase_name}] {line_str}{col_str}: {err.get('message')}", expanded=True):
                if err.get("rule_text"):
                    st.code(err.get("rule_text"), language="text")
                st.write(f"**Diagnostic Details:** {err.get('message')}")
                if err.get("suggestion"):
                    st.info(f"💡 **Correction Suggestion:** {err.get('suggestion')}")

    # Generate full downloadable markdown report
    st.markdown("---")
    st.subheader("📄 Download Diagnostic Report")
    report_md = reporter.generate_report({
        "lexical": grouped.get("Lexical", []),
        "syntax": grouped.get("Syntax", []),
        "semantic": grouped.get("Semantic", []),
        "solver": grouped.get("Solver", []),
    })
    st.download_button(
        label="📥 Download Diagnostic Report (Markdown)",
        data=report_md.encode("utf-8"),
        file_name="compiler_error_report.md",
        mime="text/markdown",
        width="stretch"
    )
