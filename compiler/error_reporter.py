"""
error_reporter.py — Error Reporter Module
Smart University Timetable Constraint Compiler

COMPILER CONCEPT:
-----------------
In a multi-phase compiler pipeline, errors can originate from four distinct
phases:
  1. Lexical Analysis  — invalid characters, unrecognised tokens
  2. Syntax Analysis   — malformed rule structure, missing semicolons
  3. Semantic Analysis — undefined entities, contradicting constraints
  4. Solving / Code-Gen— infeasible schedules, constraint conflicts

The ErrorReporter module acts as the compiler's "diagnostic engine": it
normalises raw error objects from every phase into a uniform dict schema,
enriches each entry with a human-readable *suggestion*, and aggregates them
into a single Markdown report suitable for display in a Streamlit UI or for
writing to a log file.

Uniform error dict schema
--------------------------
  {
    "phase"      : str,   # "Lexical" | "Syntax" | "Semantic" | "Solver"
    "line"       : int,   # 1-based source line, or 0 if not applicable
    "column"     : int,   # 1-based column, or 0 if not applicable
    "message"    : str,   # concise error description
    "rule_text"  : str,   # offending source snippet (best-effort)
    "suggestion" : str,   # actionable fix hint
    "severity"   : str,   # "error" | "warning" | "info"
  }
"""

from __future__ import annotations

import re
import textwrap
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

# ---------------------------------------------------------------------------
# Constants / helpers
# ---------------------------------------------------------------------------

VALID_DAYS = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday"}
VALID_TIMES = {"8AM", "9AM", "10AM", "11AM", "12PM", "1PM", "2PM", "3PM", "4PM", "5PM"}

PHASES = {
    "lexical":  "Lexical",
    "syntax":   "Syntax",
    "semantic": "Semantic",
    "solver":   "Solver",
}

# ---------------------------------------------------------------------------
# Suggestion knowledge-base
# ---------------------------------------------------------------------------

# Each entry: (phase, regex_pattern_on_message) -> suggestion string
_SUGGESTION_DB: List[tuple[str, str, str]] = [
    # ── Lexical ─────────────────────────────────────────────────────────────
    ("lexical", r"unexpected character",
     "Check for stray punctuation or non-ASCII characters. TCS files accept "
     "only ASCII letters, digits, underscores, semicolons, and newlines."),

    ("lexical", r"unterminated string",
     "String literals are not part of the TCS language. Remove any quotation "
     "marks from your source file."),

    ("lexical", r"invalid token|unrecognised token",
     "The token is not part of the TCS grammar. Valid keywords are: RULE, "
     "NOT_AVAILABLE, ROOM, TEACHER, DURATION, STUDENTS, DAYS_PER_WEEK, "
     "CAPACITY, NO_ROOM_CLASH, NO_TEACHER_CLASH, PREFERRED_TIME, "
     "PREFERRED_DAY, NO_CLASH."),

    ("lexical", r"invalid time",
     f"Valid time tokens are: {', '.join(sorted(VALID_TIMES))}. "
     "Ensure the format is <digit>AM or <digit>PM (e.g. 9AM, 2PM)."),

    ("lexical", r"invalid day",
     f"Valid day tokens are: {', '.join(sorted(VALID_DAYS))}. "
     "Capitalise the first letter (e.g. Monday, not monday)."),

    ("lexical", r"hour suffix|nhour",
     "Duration values must use the HOUR suffix directly attached to a number, "
     "e.g. 2HOUR.  Do not add a space between the digit and HOUR."),

    # ── Syntax ───────────────────────────────────────────────────────────────
    ("syntax", r"missing semicolon|expected.*semicolon|no semicolon",
     "Every RULE statement must end with a semicolon (;). "
     "Example: RULE CS101 ROOM R201;"),

    ("syntax", r"expected.*rule|unexpected.*end",
     "Each statement must start with the keyword RULE. "
     "Check for stray text or incomplete lines above this one."),

    ("syntax", r"unknown rule type|unrecognised rule",
     "The rule keyword after the entity name is not recognised. "
     "Allowed types: NOT_AVAILABLE, ROOM, TEACHER, DURATION, STUDENTS, "
     "DAYS_PER_WEEK, CAPACITY, NO_ROOM_CLASH, NO_TEACHER_CLASH, "
     "PREFERRED_TIME, PREFERRED_DAY, NO_CLASH."),

    ("syntax", r"expected number",
     "A numeric value is required here. Use a plain integer (e.g. 30, 2)."),

    ("syntax", r"expected identifier",
     "An identifier (course ID, teacher name, room ID, or group ID) is "
     "required here. Identifiers must start with a letter and contain only "
     "letters, digits, and underscores."),

    ("syntax", r"expected day",
     f"A day name is required here. Valid days: {', '.join(sorted(VALID_DAYS))}."),

    ("syntax", r"expected time",
     f"A time token is required here. Valid times: {', '.join(sorted(VALID_TIMES))}."),

    # ── Semantic ─────────────────────────────────────────────────────────────
    ("semantic", r"teacher.*not found|unknown teacher",
     "The teacher referenced in this rule does not exist in the database. "
     "Add the teacher via the Data Manager tab, or correct the spelling."),

    ("semantic", r"course.*not found|unknown course",
     "The course referenced in this rule does not exist in the database. "
     "Register the course via the Data Manager tab, or check the course ID."),

    ("semantic", r"room.*not found|unknown room",
     "The room referenced in this rule does not exist in the database. "
     "Add the room via the Data Manager tab, or verify the room ID."),

    ("semantic", r"capacity.*insufficient|room.*too small|students.*exceed",
     "The room's seating capacity is less than the number of students enrolled "
     "in the course. Either assign a larger room or reduce the student count."),

    ("semantic", r"contradictory|conflict.*rule|duplicate rule",
     "Two or more rules contradict each other (e.g., assigning the same "
     "teacher to two overlapping courses). Remove or adjust one of the rules."),

    ("semantic", r"teacher.*unavailable.*clash|unavailable.*conflict",
     "A TEACHER rule assigns a teacher to a slot that is blocked by a "
     "NOT_AVAILABLE rule for the same teacher. Remove the conflict."),

    ("semantic", r"duration.*out of range|duration.*invalid",
     "Course duration must be between 1 and 3 hours. "
     "Example: RULE CS101 DURATION 2HOUR;"),

    ("semantic", r"days_per_week.*invalid|invalid.*days per week",
     "DAYS_PER_WEEK must be between 1 and 5 (Mon–Fri). "
     "Example: RULE CS101 DAYS_PER_WEEK 3;"),

    ("semantic", r"invalid day",
     f"Day must be one of: {', '.join(sorted(VALID_DAYS))}."),

    ("semantic", r"invalid time",
     f"Time must be one of: {', '.join(sorted(VALID_TIMES))}."),

    # ── Solver ────────────────────────────────────────────────────────────────
    ("solver", r"infeasible|no solution",
     "The constraint set has no valid timetable. Common causes: a teacher is "
     "unavailable for all slots assigned to their courses, a room has "
     "insufficient capacity, or DAYS_PER_WEEK requirements cannot be met. "
     "Relax one or more hard constraints and try again."),

    ("solver", r"timeout",
     "The solver exceeded its time limit without finding an optimal solution. "
     "Consider reducing the number of courses/rooms, loosening soft "
     "constraints, or increasing the timeout via solver settings."),

    ("solver", r"teacher.*double.booked|teacher.*clash",
     "A teacher has been scheduled for two courses at the same day/time. "
     "Add a NOT_AVAILABLE rule or remove the conflicting TEACHER assignments."),

    ("solver", r"room.*double.booked|room.*clash",
     "A room has been double-booked. Assign courses to different rooms or "
     "time slots so each room is used at most once per slot."),
]


def _lookup_suggestion(phase: str, message: str) -> str:
    """Return the best-matching suggestion for a given phase + message pair.

    Iterates over the knowledge-base in order and returns the first match.
    Falls back to a generic hint when no pattern matches.
    """
    phase_lower = phase.lower()
    message_lower = message.lower()
    for kb_phase, pattern, suggestion in _SUGGESTION_DB:
        if kb_phase == phase_lower and re.search(pattern, message_lower):
            return suggestion
    # Generic fallback
    return (
        "Review the TCS language specification and ensure the rule follows "
        "the correct syntax, references valid entities, and does not conflict "
        "with other rules."
    )


def _safe_int(value: Any, default: int = 0) -> int:
    """Coerce *value* to int, returning *default* on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_str(value: Any, default: str = "") -> str:
    """Coerce *value* to str, returning *default* on None."""
    if value is None:
        return default
    return str(value)


# ---------------------------------------------------------------------------
# Public API — ErrorReporter
# ---------------------------------------------------------------------------


class ErrorReporter:
    """Central diagnostic engine for the TCS compiler pipeline.

    Usage
    -----
    ::

        reporter = ErrorReporter()

        # Collect errors from each phase as they occur:
        lex_dicts  = reporter.format_lexical_errors(lexer_errors)
        syn_dicts  = reporter.format_syntax_errors(parser_result.errors)
        sem_dicts  = reporter.format_semantic_errors(semantic_result.errors)
        sol_dicts  = reporter.format_solver_errors(solver_result)

        # Produce a Markdown report:
        report_md  = reporter.generate_report({
            "lexical":  lex_dicts,
            "syntax":   syn_dicts,
            "semantic": sem_dicts,
            "solver":   sol_dicts,
        })

    Compiler concept — Error Recovery
    ----------------------------------
    A production compiler attempts to continue past the first error so the
    programmer sees all mistakes at once (e.g. gcc's behaviour).  This module
    supports that by accepting *lists* of errors from each phase and formatting
    all of them, rather than stopping at the first one.
    """

    # ------------------------------------------------------------------ #
    # Lexical error formatting                                             #
    # ------------------------------------------------------------------ #

    def format_lexical_errors(self, errors: List[Any]) -> List[dict]:
        """Normalise a list of lexical errors into uniform error dicts.

        Parameters
        ----------
        errors:
            A heterogeneous list that may contain:
            - ``LexicalError`` / ``lark.exceptions.UnexpectedCharacters`` /
              ``lark.exceptions.UnexpectedToken`` instances
            - Plain ``str`` messages
            - ``dict`` objects already partially formed
            - Any ``Exception`` subclass with a ``message`` attribute

        Returns
        -------
        List[dict]
            Each dict conforms to the unified error schema.
        """
        result: List[dict] = []
        for err in errors:
            entry = self._normalise_error(err, phase="Lexical")
            result.append(entry)
        return result

    # ------------------------------------------------------------------ #
    # Syntax error formatting                                              #
    # ------------------------------------------------------------------ #

    def format_syntax_errors(self, errors: List[Any]) -> List[dict]:
        """Normalise a list of syntax / parse errors into uniform error dicts.

        Lark raises ``lark.exceptions.UnexpectedToken``,
        ``UnexpectedCharacters``, or ``UnexpectedEOF``; this method handles
        all of them, as well as plain strings and dicts.

        Parameters
        ----------
        errors:
            Raw syntax error objects from the parser phase.

        Returns
        -------
        List[dict]
            Each dict conforms to the unified error schema.
        """
        result: List[dict] = []
        for err in errors:
            entry = self._normalise_error(err, phase="Syntax")
            result.append(entry)
        return result

    # ------------------------------------------------------------------ #
    # Semantic error formatting                                            #
    # ------------------------------------------------------------------ #

    def format_semantic_errors(self, errors: List[Any]) -> List[dict]:
        """Normalise semantic errors into uniform error dicts.

        The semantic analyser may produce ``SemanticError`` dataclass
        instances (with ``message``, ``rule_text``, and ``line`` fields),
        plain strings, or dicts.

        Parameters
        ----------
        errors:
            Raw semantic error objects.

        Returns
        -------
        List[dict]
            Each dict conforms to the unified error schema.
        """
        result: List[dict] = []
        for err in errors:
            entry = self._normalise_error(err, phase="Semantic")
            result.append(entry)
        return result

    # ------------------------------------------------------------------ #
    # Solver error / warning formatting                                    #
    # ------------------------------------------------------------------ #

    def format_solver_errors(self, solver_result: Any) -> List[dict]:
        """Extract and format diagnostics from a SolverResult object.

        The solver result may expose its status and any errors via
        attributes (``status``, ``message``, ``errors``) or as a plain
        dict.  This method handles all variations.

        Parameters
        ----------
        solver_result:
            A ``SolverResult`` dataclass, a dict, a string status, or
            ``None``.

        Returns
        -------
        List[dict]
            Each dict conforms to the unified error schema.  An empty list
            is returned when the solver succeeded (status == "OPTIMAL" or
            "FEASIBLE") with no additional messages.
        """
        result: List[dict] = []

        if solver_result is None:
            return result

        # ── dict-like ────────────────────────────────────────────────────
        if isinstance(solver_result, dict):
            status  = _safe_str(solver_result.get("status", "UNKNOWN")).upper()
            message = _safe_str(solver_result.get("message", ""))
            errors  = solver_result.get("errors", [])

            if status not in ("OPTIMAL", "FEASIBLE") or message:
                entry = self._make_error_dict(
                    phase="Solver",
                    line=0,
                    column=0,
                    message=message or f"Solver finished with status: {status}",
                    rule_text="",
                    severity="error" if status == "INFEASIBLE" else "warning",
                )
                result.append(entry)

            for e in (errors or []):
                result.append(self._normalise_error(e, phase="Solver"))
            return result

        # ── string ───────────────────────────────────────────────────────
        if isinstance(solver_result, str):
            status = solver_result.upper()
            if status not in ("OPTIMAL", "FEASIBLE"):
                result.append(self._make_error_dict(
                    phase="Solver",
                    line=0,
                    column=0,
                    message=f"Solver status: {solver_result}",
                    rule_text="",
                    severity="error" if "INFEASIBLE" in status else "warning",
                ))
            return result

        # ── dataclass / object ───────────────────────────────────────────
        status  = _safe_str(getattr(solver_result, "status",  "UNKNOWN")).upper()
        message = _safe_str(getattr(solver_result, "message", ""))
        errors  = getattr(solver_result, "errors", []) or []

        if status == "INFEASIBLE":
            result.append(self._make_error_dict(
                phase="Solver",
                line=0,
                column=0,
                message=message or "No feasible timetable found with the given constraints.",
                rule_text="",
                severity="error",
            ))
        elif status == "TIMEOUT":
            result.append(self._make_error_dict(
                phase="Solver",
                line=0,
                column=0,
                message=message or "Solver timed out before finding an optimal solution.",
                rule_text="",
                severity="warning",
            ))
        elif status not in ("OPTIMAL", "FEASIBLE"):
            result.append(self._make_error_dict(
                phase="Solver",
                line=0,
                column=0,
                message=message or f"Unexpected solver status: {status}",
                rule_text="",
                severity="warning",
            ))
        elif message:
            # FEASIBLE/OPTIMAL but solver reported extra info
            result.append(self._make_error_dict(
                phase="Solver",
                line=0,
                column=0,
                message=message,
                rule_text="",
                severity="info",
            ))

        for e in errors:
            result.append(self._normalise_error(e, phase="Solver"))

        return result

    # ------------------------------------------------------------------ #
    # Full Markdown report                                                  #
    # ------------------------------------------------------------------ #

    def generate_report(self, all_errors: Dict[str, List[dict]]) -> str:
        """Aggregate all phase errors into a single Markdown diagnostic report.

        Parameters
        ----------
        all_errors:
            A dict keyed by phase name (``"lexical"``, ``"syntax"``,
            ``"semantic"``, ``"solver"``) whose values are lists of uniform
            error dicts as returned by the ``format_*`` methods.

        Returns
        -------
        str
            A Markdown string suitable for display in a Streamlit
            ``st.markdown()`` call or for writing to a ``.md`` log file.

        Compiler concept — Diagnostic report
        --------------------------------------
        Compilers like clang and rustc emit coloured, annotated diagnostic
        reports.  This method produces the textual equivalent: a structured
        Markdown document with counts, severity badges, per-phase sections,
        and an error/warning summary table, mirroring the output you would
        see from ``cargo build`` or ``clang++ -Wall``.
        """
        lines: List[str] = []
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ── Header ───────────────────────────────────────────────────────
        lines.append("# 🛠 TCS Compiler Diagnostic Report")
        lines.append(f"> Generated: **{now_str}**")
        lines.append("")

        # ── Totals ───────────────────────────────────────────────────────
        total_errors   = 0
        total_warnings = 0
        total_infos    = 0
        all_flat: List[dict] = []
        for phase_errs in all_errors.values():
            for e in phase_errs:
                all_flat.append(e)
                sev = e.get("severity", "error")
                if sev == "error":
                    total_errors += 1
                elif sev == "warning":
                    total_warnings += 1
                else:
                    total_infos += 1

        status_emoji = "✅" if total_errors == 0 else "❌"
        lines.append(
            f"## {status_emoji} Summary — "
            f"{total_errors} error(s), "
            f"{total_warnings} warning(s), "
            f"{total_infos} info(s)"
        )
        lines.append("")

        if not all_flat:
            lines.append("*No errors detected — the constraint script is valid.*")
            lines.append("")
            return "\n".join(lines)

        # ── Summary table ─────────────────────────────────────────────────
        lines.append("| # | Phase | Severity | Line | Message |")
        lines.append("|---|-------|----------|------|---------|")
        for idx, e in enumerate(all_flat, 1):
            sev   = e.get("severity", "error")
            badge = {"error": "🔴 Error", "warning": "🟡 Warning", "info": "🔵 Info"}.get(sev, sev)
            line_no = e.get("line", 0) or 0
            line_str = str(line_no) if line_no > 0 else "—"
            msg = e.get("message", "").replace("|", "\\|")[:80]
            lines.append(f"| {idx} | {e.get('phase','?')} | {badge} | {line_str} | {msg} |")
        lines.append("")

        # ── Per-phase sections ────────────────────────────────────────────
        phase_order = [
            ("lexical",  "🔡 Phase 1 — Lexical Errors"),
            ("syntax",   "📐 Phase 2 — Syntax Errors"),
            ("semantic", "🔍 Phase 3 — Semantic Errors"),
            ("solver",   "⚙️  Phase 4 — Solver Diagnostics"),
        ]

        for phase_key, phase_title in phase_order:
            errs = all_errors.get(phase_key, [])
            if not errs:
                continue

            lines.append(f"---")
            lines.append(f"## {phase_title}")
            lines.append("")

            for i, e in enumerate(errs, 1):
                sev     = e.get("severity", "error")
                sev_icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(sev, "⚪")
                line_no  = e.get("line",    0) or 0
                col_no   = e.get("column",  0) or 0
                msg      = e.get("message", "No message provided.")
                rule_txt = e.get("rule_text", "")
                suggest  = e.get("suggestion", "")

                loc_parts = []
                if line_no > 0:
                    loc_parts.append(f"line {line_no}")
                if col_no > 0:
                    loc_parts.append(f"col {col_no}")
                loc_str = ", ".join(loc_parts) if loc_parts else "unknown location"

                lines.append(f"### {sev_icon} Error {i} — {loc_str}")
                lines.append("")
                lines.append(f"**Message:** {msg}")
                lines.append("")

                if rule_txt:
                    lines.append("**Offending rule:**")
                    lines.append(f"```tcs")
                    lines.append(rule_txt.strip())
                    lines.append("```")
                    lines.append("")

                if suggest:
                    lines.append(f"**💡 Suggestion:** {suggest}")
                    lines.append("")

        # ── Compiler phase explanation footer ─────────────────────────────
        lines.append("---")
        lines.append("## 📚 Compiler Phase Reference")
        lines.append("")
        lines.append(
            "| Phase | Role | Typical Errors |\n"
            "|-------|------|----------------|\n"
            "| **Lexical** | Converts raw text into tokens | Unknown characters, bad time/day format |\n"
            "| **Syntax** | Validates token sequences against the grammar | Missing `;`, unknown rule keywords |\n"
            "| **Semantic** | Validates meaning against the DB | Unknown teacher/course/room, capacity mismatch |\n"
            "| **Solver** | Finds a feasible timetable | Infeasible constraints, timeout |"
        )
        lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Convenience aggregator                                               #
    # ------------------------------------------------------------------ #

    def collect_and_report(
        self,
        lexical_errors:  Optional[List[Any]] = None,
        syntax_errors:   Optional[List[Any]] = None,
        semantic_errors: Optional[List[Any]] = None,
        solver_result:   Optional[Any]        = None,
    ) -> tuple[Dict[str, List[dict]], str]:
        """One-shot helper: format all phases and generate the Markdown report.

        Parameters
        ----------
        lexical_errors, syntax_errors, semantic_errors:
            Raw error lists from the respective compiler phases.
        solver_result:
            The ``SolverResult`` object (or dict/str) from the solver phase.

        Returns
        -------
        tuple[dict, str]
            ``(error_dict, markdown_report)`` where ``error_dict`` maps
            phase name → list of uniform error dicts.
        """
        lex_dicts  = self.format_lexical_errors(lexical_errors   or [])
        syn_dicts  = self.format_syntax_errors(syntax_errors     or [])
        sem_dicts  = self.format_semantic_errors(semantic_errors or [])
        sol_dicts  = self.format_solver_errors(solver_result)

        all_errors = {
            "lexical":  lex_dicts,
            "syntax":   syn_dicts,
            "semantic": sem_dicts,
            "solver":   sol_dicts,
        }
        report = self.generate_report(all_errors)
        return all_errors, report

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _normalise_error(self, err: Any, phase: str) -> dict:
        """Convert an arbitrary error object into a uniform error dict.

        Handles the following types:
        - ``dict``              — already partially normalised
        - ``str``               — treated as the message
        - Lark exceptions       — ``UnexpectedCharacters``, ``UnexpectedToken``,
                                   ``UnexpectedEOF``
        - Custom dataclasses    — objects with ``message``, ``line``,
                                   ``column``, ``rule_text`` attributes
        - Generic ``Exception`` — ``str(err)`` used as message
        """
        try:
            # ── dict ─────────────────────────────────────────────────────
            if isinstance(err, dict):
                return self._make_error_dict(
                    phase      = err.get("phase", phase),
                    line       = _safe_int(err.get("line",    0)),
                    column     = _safe_int(err.get("column",  0)),
                    message    = _safe_str(err.get("message", "")),
                    rule_text  = _safe_str(err.get("rule_text", "")),
                    severity   = err.get("severity", "error"),
                )

            # ── plain string ──────────────────────────────────────────────
            if isinstance(err, str):
                return self._make_error_dict(
                    phase=phase, line=0, column=0,
                    message=err, rule_text="", severity="error",
                )

            # ── Lark UnexpectedCharacters ─────────────────────────────────
            # Attribute names vary slightly between Lark versions; we try both.
            lark_type = type(err).__name__
            if lark_type in (
                "UnexpectedCharacters", "UnexpectedToken", "UnexpectedEOF",
                "LexError", "ParseError",
            ):
                line   = _safe_int(getattr(err, "line",   0))
                column = _safe_int(getattr(err, "column", 0))

                # Build a readable message
                if lark_type == "UnexpectedCharacters":
                    char   = _safe_str(getattr(err, "char", "?"))
                    msg    = f"Unexpected character '{char}' at line {line}, col {column}."
                elif lark_type == "UnexpectedToken":
                    token  = getattr(err, "token", None)
                    tok_str = _safe_str(token) if token is not None else "?"
                    expected = getattr(err, "expected", None)
                    exp_str  = (
                        ", ".join(str(e) for e in expected)
                        if expected else "unknown"
                    )
                    msg = (
                        f"Unexpected token '{tok_str}' at line {line}, col {column}. "
                        f"Expected one of: {exp_str}."
                    )
                elif lark_type == "UnexpectedEOF":
                    expected = getattr(err, "expected", None)
                    exp_str  = (
                        ", ".join(str(e) for e in expected)
                        if expected else "unknown"
                    )
                    msg = f"Unexpected end of file. Expected: {exp_str}."
                else:
                    msg = _safe_str(err)

                return self._make_error_dict(
                    phase=phase, line=line, column=column,
                    message=msg, rule_text="", severity="error",
                )

            # ── Custom dataclass / object ─────────────────────────────────
            message   = _safe_str(getattr(err, "message",   None) or getattr(err, "msg", None) or str(err))
            line      = _safe_int(getattr(err, "line",      0))
            column    = _safe_int(getattr(err, "column",    0))
            rule_text = _safe_str(getattr(err, "rule_text", None) or getattr(err, "text", None) or "")
            severity  = _safe_str(getattr(err, "severity",  "error"))

            return self._make_error_dict(
                phase=phase, line=line, column=column,
                message=message, rule_text=rule_text, severity=severity,
            )

        except Exception as ex:  # pragma: no cover — safety net
            return self._make_error_dict(
                phase=phase, line=0, column=0,
                message=f"[ErrorReporter internal error while formatting: {ex}]",
                rule_text="", severity="error",
            )

    def _make_error_dict(
        self,
        phase:     str,
        line:      int,
        column:    int,
        message:   str,
        rule_text: str,
        severity:  str = "error",
    ) -> dict:
        """Construct a normalised error dict and populate the *suggestion* field.

        This is the single factory used by every code path so the schema is
        always consistent.
        """
        suggestion = _lookup_suggestion(phase, message)
        return {
            "phase":      phase,
            "line":       line,
            "column":     column,
            "message":    message,
            "rule_text":  rule_text,
            "suggestion": suggestion,
            "severity":   severity,
        }


# ---------------------------------------------------------------------------
# Module-level convenience functions (thin wrappers around ErrorReporter)
# ---------------------------------------------------------------------------

_default_reporter = ErrorReporter()


def format_lexical_errors(errors: List[Any]) -> List[dict]:
    """Module-level wrapper for ``ErrorReporter.format_lexical_errors``."""
    return _default_reporter.format_lexical_errors(errors)


def format_syntax_errors(errors: List[Any]) -> List[dict]:
    """Module-level wrapper for ``ErrorReporter.format_syntax_errors``."""
    return _default_reporter.format_syntax_errors(errors)


def format_semantic_errors(errors: List[Any]) -> List[dict]:
    """Module-level wrapper for ``ErrorReporter.format_semantic_errors``."""
    return _default_reporter.format_semantic_errors(errors)


def format_solver_errors(solver_result: Any) -> List[dict]:
    """Module-level wrapper for ``ErrorReporter.format_solver_errors``."""
    return _default_reporter.format_solver_errors(solver_result)


def generate_report(all_errors: Dict[str, List[dict]]) -> str:
    """Module-level wrapper for ``ErrorReporter.generate_report``."""
    return _default_reporter.generate_report(all_errors)


# ---------------------------------------------------------------------------
# Self-test (python error_reporter.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    reporter = ErrorReporter()

    # Simulate a LexicalError as a plain dict
    lex_err = {
        "message":   "Unexpected character '@' at line 3, col 12.",
        "line":      3,
        "column":    12,
        "rule_text": "RULE CS101 @ROOM R201;",
    }

    # Simulate a syntax error as a plain string
    syn_err_str = "Missing semicolon at end of statement on line 5."

    # Simulate a semantic error as an object
    class _FakeSemanticError:
        def __init__(self):
            self.message   = "Teacher 'Dr_Smith' not found in database."
            self.rule_text = "RULE Dr_Smith NOT_AVAILABLE Monday 9AM;"
            self.line      = 7
            self.column    = 0
            self.severity  = "error"

    # Simulate an INFEASIBLE solver result
    class _FakeSolverResult:
        status  = "INFEASIBLE"
        message = "No feasible timetable found with the given constraints."
        errors  = []

    lex_dicts = reporter.format_lexical_errors([lex_err])
    syn_dicts = reporter.format_syntax_errors([syn_err_str])
    sem_dicts = reporter.format_semantic_errors([_FakeSemanticError()])
    sol_dicts = reporter.format_solver_errors(_FakeSolverResult())

    report = reporter.generate_report({
        "lexical":  lex_dicts,
        "syntax":   syn_dicts,
        "semantic": sem_dicts,
        "solver":   sol_dicts,
    })

    print(report)
    print("\n--- Self-test passed ---")
