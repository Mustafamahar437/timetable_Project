"""
compiler/parser.py
==================
Parser module for the Smart University Timetable Constraint Compiler.

This module implements a Lark-based EBNF parser for the Timetable Constraint
Script (TCS) DSL. It sits in the classic compiler pipeline between the lexer
and the semantic analyser:

    Source (.tcs)
        └─► Lexer  (tokenise)
                └─► Parser  (build Concrete Syntax Tree)   <── THIS MODULE
                        └─► Semantic Analyser
                                └─► IR Generator
                                        └─► Code Generator
                                                └─► Solver

Compiler Concepts Implemented
------------------------------
* Context-Free Grammar (CFG) written in Lark's EBNF dialect.
* Top-down Earley / LALR(1) parsing via Lark.
* Parse-tree construction: Lark produces a ``lark.Tree`` whose nodes
  correspond directly to grammar rules.
* Syntax-error recovery: a best-effort pass collects as many errors as
  possible instead of stopping at the first bad rule.
* Pretty-printing and dict-serialisation of the CST for Streamlit display.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional, Union

# ---------------------------------------------------------------------------
# Lark import guard – give a clear message if the dependency is missing.
# ---------------------------------------------------------------------------
try:
    import lark
    from lark import Lark, Tree, Token
    from lark.exceptions import UnexpectedCharacters, UnexpectedToken, UnexpectedEOF
except ImportError as _lark_err:  # pragma: no cover
    raise ImportError(
        "The 'lark' package is required for the parser. "
        "Install it with: pip install lark>=1.1.9"
    ) from _lark_err


# ===========================================================================
# Grammar Definition
# ===========================================================================

# The grammar is written in Lark's EBNF / ABNF dialect.
#
# Key design decisions
# --------------------
# 1.  Every RULE statement is a separate alternative so that error messages
#     point to the exact rule type that is malformed.
# 2.  Terminals are defined with explicit string literals (case-sensitive) so
#     that the lexer can do maximum-munch matching and we do not accidentally
#     accept partial keywords.
# 3.  The grammar is intentionally *permissive* at the token level (IDENTIFIER
#     also matches bare names like teacher/course/room IDs) and strict at the
#     structural level (each rule form has a unique shape).
# 4.  We use Lark's built-in NEWLINE terminal to track line numbers.

TCS_GRAMMAR = r"""
// =========================================================================
// Timetable Constraint Script (TCS) – Lark EBNF Grammar
// =========================================================================

// Entry point
start: statement* -> program

// A statement is a RULE declaration followed by a mandatory semicolon.
statement: rule_decl SEMICOLON

// -------------------------------------------------------------------------
// Rule variants
// -------------------------------------------------------------------------
rule_decl : RULE_KW NO_ROOM_CLASH_KW                              -> global_no_room_clash
          | RULE_KW NO_TEACHER_CLASH_KW                           -> global_no_teacher_clash
          | RULE_KW identifier NOT_AVAILABLE_KW day time          -> teacher_unavailable
          | RULE_KW identifier ROOM_KW identifier                 -> course_room
          | RULE_KW identifier TEACHER_KW identifier              -> course_teacher
          | RULE_KW identifier DURATION_KW DURATION_VALUE         -> course_duration
          | RULE_KW identifier STUDENTS_KW INTEGER                -> course_students
          | RULE_KW identifier DAYS_PER_WEEK_KW INTEGER           -> course_days_per_week
          | RULE_KW identifier CAPACITY_KW INTEGER                -> room_capacity
          | RULE_KW identifier PREFERRED_TIME_KW time             -> course_preferred_time
          | RULE_KW identifier PREFERRED_DAY_KW day               -> course_preferred_day
          | RULE_KW identifier NO_CLASH_KW                        -> group_no_clash

// -------------------------------------------------------------------------
// Shared sub-expressions
// -------------------------------------------------------------------------
identifier : ID_TOKEN

day : MONDAY | TUESDAY | WEDNESDAY | THURSDAY | FRIDAY

time : TIME_8AM  | TIME_9AM  | TIME_10AM | TIME_11AM | TIME_12PM
     | TIME_1PM  | TIME_2PM  | TIME_3PM  | TIME_4PM  | TIME_5PM

// =========================================================================
// TERMINALS
// =========================================================================

// Keywords (all upper-case in source)
RULE_KW            : "RULE"
NO_ROOM_CLASH_KW   : "NO_ROOM_CLASH"
NO_TEACHER_CLASH_KW: "NO_TEACHER_CLASH"
NOT_AVAILABLE_KW   : "NOT_AVAILABLE"
ROOM_KW            : "ROOM"
TEACHER_KW         : "TEACHER"
DURATION_KW        : "DURATION"
STUDENTS_KW        : "STUDENTS"
DAYS_PER_WEEK_KW   : "DAYS_PER_WEEK"
CAPACITY_KW        : "CAPACITY"
PREFERRED_TIME_KW  : "PREFERRED_TIME"
PREFERRED_DAY_KW   : "PREFERRED_DAY"
NO_CLASH_KW        : "NO_CLASH"
SEMICOLON          : ";"

// Day tokens
MONDAY    : "Monday"
TUESDAY   : "Tuesday"
WEDNESDAY : "Wednesday"
THURSDAY  : "Thursday"
FRIDAY    : "Friday"

// Time tokens (AM/PM slots)
TIME_8AM  : "8AM"
TIME_9AM  : "9AM"
TIME_10AM : "10AM"
TIME_11AM : "11AM"
TIME_12PM : "12PM"
TIME_1PM  : "1PM"
TIME_2PM  : "2PM"
TIME_3PM  : "3PM"
TIME_4PM  : "4PM"
TIME_5PM  : "5PM"

// Duration: an integer immediately followed by HOUR (e.g. 1HOUR, 2HOUR)
// We capture the whole token so there is no ambiguity with plain integers.
DURATION_VALUE : /[1-9][0-9]*HOUR/

// Plain non-negative integer (used for STUDENTS, DAYS_PER_WEEK, CAPACITY)
INTEGER : /[0-9]+/

// Identifier: letters, digits, underscores, hyphens  (e.g. CS101, Dr_Ali)
ID_TOKEN : /[A-Za-z_][A-Za-z0-9_\-]*/

// Whitespace and comments are silently discarded.
%ignore /[ \t\r\n]+/
%ignore /\/\/[^\n]*/
%ignore /\/\*(.|\n)*?\*\//
"""

# Priority list controls Lark terminal disambiguation.  Longer / more specific
# terminals must have higher priority than the catch-all ID_TOKEN.
# Lark resolves ambiguity by: (1) explicit priority, (2) longer match wins,
# (3) earlier definition in the grammar wins.
# Because keywords are string literals they automatically get priority > regex
# terminals in Lark's contextual lexer, so the grammar above is already correct.


# ===========================================================================
# Data Classes
# ===========================================================================

@dataclass
class SyntaxError_:
    """
    Represents a single syntax error detected during parsing.

    Attributes
    ----------
    message : str
        Human-readable description of the problem.
    line : int
        1-based source line where the error was detected (0 if unknown).
    column : int
        1-based source column (0 if unknown).
    expected : List[str]
        Tokens the parser expected at the error site (may be empty).
    offending_token : str
        The actual token / text that caused the error (may be empty).
    suggestion : str
        A hint to help the user fix the issue.
    """
    message: str
    line: int = 0
    column: int = 0
    expected: List[str] = field(default_factory=list)
    offending_token: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "expected": self.expected,
            "offending_token": self.offending_token,
            "suggestion": self.suggestion,
        }

    def __str__(self) -> str:
        location = f"line {self.line}, col {self.column}" if self.line else "unknown location"
        base = f"[SyntaxError @ {location}] {self.message}"
        if self.offending_token:
            base += f"  (got: '{self.offending_token}')"
        if self.suggestion:
            base += f"\n  Hint: {self.suggestion}"
        return base


@dataclass
class ParseResult:
    """
    Result object returned by :py:meth:`Parser.parse`.

    Attributes
    ----------
    success : bool
        ``True`` when the entire source parsed without errors.
    tree : lark.Tree or None
        The concrete syntax tree produced by Lark, or ``None`` on hard failure.
    errors : List[SyntaxError_]
        All syntax errors collected during parsing.
    source : str
        The original source text that was parsed.
    statement_count : int
        Number of top-level RULE statements recognised.
    """
    success: bool
    tree: Optional[Tree]
    errors: List[SyntaxError_] = field(default_factory=list)
    source: str = ""
    statement_count: int = 0

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def get_tree_as_dict(self) -> dict:
        """
        Return a JSON-serialisable dict representation of the parse tree.

        Suitable for embedding in a Streamlit ``st.json`` widget.
        """
        return {
            "success": self.success,
            "statement_count": self.statement_count,
            "errors": [e.to_dict() for e in self.errors],
            "tree": _tree_to_dict(self.tree) if self.tree else None,
        }

    def format_tree_pretty(self) -> str:
        """
        Return a human-readable pretty-print of the parse tree.

        Uses Lark's built-in ``pretty()`` method when available, with a
        compact fallback for edge cases.
        """
        if self.tree is None:
            if self.errors:
                return "\n".join(str(e) for e in self.errors)
            return "(empty tree)"
        try:
            return self.tree.pretty()
        except Exception:
            return _tree_to_str(self.tree, indent=0)


# ===========================================================================
# Internal helpers
# ===========================================================================

def _tree_to_dict(node: Union[Tree, Token, None]) -> Union[dict, str, None]:
    """Recursively convert a Lark Tree/Token to a plain dict."""
    if node is None:
        return None
    if isinstance(node, Token):
        return {"token": node.type, "value": str(node)}
    if isinstance(node, Tree):
        return {
            "rule": node.data,
            "children": [_tree_to_dict(child) for child in node.children],
        }
    return str(node)


def _tree_to_str(node: Union[Tree, Token, None], indent: int) -> str:
    """Fallback pretty-printer that does not rely on ``Tree.pretty()``."""
    pad = "  " * indent
    if node is None:
        return f"{pad}(None)"
    if isinstance(node, Token):
        return f"{pad}{node.type}: {node!r}"
    if isinstance(node, Tree):
        lines = [f"{pad}{node.data}"]
        for child in node.children:
            lines.append(_tree_to_str(child, indent + 1))
        return "\n".join(lines)
    return f"{pad}{node!r}"


def _prettify_expected(expected: set) -> List[str]:
    """
    Convert Lark's set of expected terminal names to user-friendly strings.
    """
    mapping = {
        "RULE_KW":             "RULE",
        "SEMICOLON":           ";",
        "NO_ROOM_CLASH_KW":    "NO_ROOM_CLASH",
        "NO_TEACHER_CLASH_KW": "NO_TEACHER_CLASH",
        "NOT_AVAILABLE_KW":    "NOT_AVAILABLE",
        "ROOM_KW":             "ROOM",
        "TEACHER_KW":          "TEACHER",
        "DURATION_KW":         "DURATION",
        "STUDENTS_KW":         "STUDENTS",
        "DAYS_PER_WEEK_KW":    "DAYS_PER_WEEK",
        "CAPACITY_KW":         "CAPACITY",
        "PREFERRED_TIME_KW":   "PREFERRED_TIME",
        "PREFERRED_DAY_KW":    "PREFERRED_DAY",
        "NO_CLASH_KW":         "NO_CLASH",
        "ID_TOKEN":            "<identifier>",
        "INTEGER":             "<integer>",
        "DURATION_VALUE":      "<n>HOUR  (e.g. 2HOUR)",
        "$END":                "<end of file>",
    }
    result = []
    for tok in sorted(expected):
        result.append(mapping.get(tok, tok))
    return result


def _make_suggestion(message: str, offending: str, expected: List[str]) -> str:
    """
    Heuristically generate a helpful fix suggestion based on the error context.
    """
    msg_lower = message.lower()

    # Missing semicolon is the most common mistake.
    if "semicolon" in msg_lower or ";" in str(expected):
        return "Did you forget a semicolon ';' at the end of the RULE statement?"

    if offending and re.match(r"[0-9]+hour", offending, re.IGNORECASE):
        return "Duration must be written without a space: e.g. '2HOUR' not '2 HOUR'."

    if offending and re.match(r"[0-9]+(am|pm)", offending, re.IGNORECASE):
        return (
            "Time tokens must be upper-case: e.g. '9AM', '1PM'. "
            "Valid slots: 8AM–5PM."
        )

    if "<identifier>" in expected or "ID_TOKEN" in str(expected):
        return (
            "An identifier (teacher name, course ID, room ID, or group ID) "
            "was expected here. Identifiers must start with a letter or underscore."
        )

    if "RULE" in str(expected):
        return (
            "Each statement must begin with the keyword RULE. "
            "Check for stray text or an unsupported rule type."
        )

    day_names = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday"}
    if offending in day_names or any(d in msg_lower for d in ("day", "monday", "friday")):
        return f"Valid days are: {', '.join(sorted(day_names))}."

    times = {"8AM", "9AM", "10AM", "11AM", "12PM", "1PM", "2PM", "3PM", "4PM", "5PM"}
    if offending in times or "am" in msg_lower or "pm" in msg_lower:
        return f"Valid times are: {', '.join(sorted(times))}."

    return "Review the TCS language specification for the correct syntax."


# ===========================================================================
# Pre-processing helpers
# ===========================================================================

def _preprocess_source(source: str) -> str:
    """
    Light pre-processing applied before Lark sees the source.

    Currently:
    * Strips a leading UTF-8 BOM if present.
    * Normalises Windows (CRLF) and old Mac (CR) line endings to LF.
    * Removes trailing whitespace from each line.

    Does NOT modify token content.
    """
    source = source.lstrip("\ufeff")          # BOM
    source = source.replace("\r\n", "\n").replace("\r", "\n")
    return source


def _split_into_rule_statements(source: str) -> List[str]:
    """
    Split the source into individual RULE statement strings (separated by ';').

    Used by the fault-tolerant parsing mode to attempt recovery after errors.
    Returns a list of stripped statement strings (without the trailing ';').
    Empty strings are excluded.
    """
    # Split on ';' keeping the delimiter so we can account for line numbers.
    parts = re.split(r";", source)
    return [p.strip() for p in parts if p.strip()]


# ===========================================================================
# Parser Class
# ===========================================================================

class Parser:
    """
    Lark-based parser for the Timetable Constraint Script (TCS) DSL.

    The parser operates in two passes:

    1. **Whole-program parse** – tries to parse the entire source in one shot
       using Lark's LALR(1) algorithm (fast, O(n) time).  If successful, the
       resulting :py:class:`ParseResult` contains the full CST.

    2. **Fault-tolerant pass** (activated on failure) – splits the source on
       semicolons and parses each statement individually.  This collects
       *multiple* error messages instead of stopping at the first bad token,
       which improves the user experience in an interactive IDE.

    Attributes
    ----------
    _lark : lark.Lark
        The compiled Lark parser object (cached after first construction).
    _lark_earley : lark.Lark
        Earley-based parser used for single-statement recovery (more lenient).
    """

    # Shared Lark instances – built once per process (class-level cache).
    _lark_instance: Optional[Lark] = None
    _lark_earley_instance: Optional[Lark] = None

    def __init__(self) -> None:
        # Ensure the shared instances are built.
        if Parser._lark_instance is None:
            Parser._lark_instance = Lark(
                TCS_GRAMMAR,
                parser="lalr",
                propagate_positions=True,
            )
        if Parser._lark_earley_instance is None:
            Parser._lark_earley_instance = Lark(
                TCS_GRAMMAR,
                parser="earley",
                propagate_positions=True,
                ambiguity="resolve",
            )
        self._lark: Lark = Parser._lark_instance
        self._lark_earley: Lark = Parser._lark_earley_instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, source: str) -> ParseResult:
        """
        Parse a TCS source string and return a :py:class:`ParseResult`.

        Parameters
        ----------
        source : str
            The raw TCS source text (content of a ``.tcs`` file).

        Returns
        -------
        ParseResult
            Contains the CST on success, or a list of :py:class:`SyntaxError_`
            objects on failure (tree may still be partially populated on
            partial recovery).

        Notes
        -----
        * Accepts bare source strings or strings that have already been
          pre-processed.
        * Does **not** accept a token list – the grammar is processed
          directly from the source text so that Lark's internal lexer
          produces richer positional information.
        """
        source = _preprocess_source(source)

        # --- Phase 1: whole-program LALR parse ---
        try:
            tree = self._lark.parse(source)
            stmt_count = sum(
                1 for child in tree.children if isinstance(child, Tree)
            )
            return ParseResult(
                success=True,
                tree=tree,
                errors=[],
                source=source,
                statement_count=stmt_count,
            )
        except (UnexpectedCharacters, UnexpectedToken, UnexpectedEOF) as exc:
            # Build an error from the first (hard) failure, then fall through
            # to fault-tolerant pass for more errors.
            errors = [self._lark_exc_to_syntax_error(exc)]
        except Exception as exc:  # noqa: BLE001
            errors = [
                SyntaxError_(
                    message=f"Unexpected parser error: {exc}",
                    suggestion="Please report this as a compiler bug.",
                )
            ]

        # --- Phase 2: fault-tolerant statement-by-statement parse ---
        ft_errors, partial_tree = self._fault_tolerant_parse(source)

        # Merge: keep the first hard error, then add any additional ones from
        # the fault-tolerant pass that are at different locations.
        seen_lines = {errors[0].line} if errors else set()
        for e in ft_errors:
            if e.line not in seen_lines:
                errors.append(e)
                seen_lines.add(e.line)

        return ParseResult(
            success=False,
            tree=partial_tree,
            errors=errors,
            source=source,
            statement_count=0,
        )

    # ------------------------------------------------------------------
    # Pretty-print / serialisation convenience (delegated from ParseResult)
    # ------------------------------------------------------------------

    def parse_to_dict(self, source: str) -> dict:
        """Parse *source* and immediately return the dict representation."""
        return self.parse(source).get_tree_as_dict()

    def parse_to_pretty(self, source: str) -> str:
        """Parse *source* and immediately return a pretty-printed tree."""
        return self.parse(source).format_tree_pretty()

    def format_tree_pretty(self, tree: Optional[Tree] = None) -> str:
        """Pretty-print a parse tree."""
        if tree is None:
            return ""
        if hasattr(tree, "pretty"):
            return tree.pretty()
        return str(tree)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _lark_exc_to_syntax_error(
        self,
        exc: Union[UnexpectedCharacters, UnexpectedToken, UnexpectedEOF],
    ) -> SyntaxError_:
        """
        Convert a Lark parse exception into our :py:class:`SyntaxError_`.

        Lark provides rich information about expected tokens which we surface
        as user-friendly suggestions.
        """
        line: int = getattr(exc, "line", 0) or 0
        column: int = getattr(exc, "column", 0) or 0

        # --- Collect expected tokens ---
        raw_expected: set = set()
        if hasattr(exc, "expected"):
            raw_expected = set(exc.expected) if exc.expected else set()
        elif hasattr(exc, "accepts"):
            raw_expected = set(exc.accepts) if exc.accepts else set()

        expected_pretty = _prettify_expected(raw_expected)

        # --- Collect the offending token text ---
        offending = ""
        if isinstance(exc, UnexpectedToken) and exc.token is not None:
            offending = str(exc.token)
        elif isinstance(exc, UnexpectedCharacters):
            offending = getattr(exc, "char", "") or ""

        # --- Build a readable message ---
        if isinstance(exc, UnexpectedEOF):
            message = "Unexpected end of file."
            if expected_pretty:
                message += f" Expected one of: {', '.join(expected_pretty)}."
        elif isinstance(exc, UnexpectedToken):
            message = f"Unexpected token '{offending}'."
            if expected_pretty:
                message += f" Expected: {', '.join(expected_pretty)}."
        elif isinstance(exc, UnexpectedCharacters):
            message = f"Unexpected character '{offending}' at line {line}, col {column}."
        else:
            message = str(exc)

        suggestion = _make_suggestion(message, offending, expected_pretty)

        return SyntaxError_(
            message=message,
            line=line,
            column=column,
            expected=expected_pretty,
            offending_token=offending,
            suggestion=suggestion,
        )

    def _fault_tolerant_parse(
        self, source: str
    ) -> tuple[List[SyntaxError_], Optional[Tree]]:
        """
        Attempt to parse each RULE statement individually.

        Strategy
        --------
        * Split the source on ``;`` boundaries while tracking cumulative line
          numbers so error positions are reported relative to the full file.
        * Parse ``RULE … ;`` with the LALR parser; fall back to Earley on
          failure (Earley can partially match incomplete input).
        * Collect errors from statements that fail both parsers.
        * Reconstruct a partial ``Tree`` from the successfully parsed
          statements so that subsequent compiler phases have *something* to
          work with even on a file with errors.

        Returns
        -------
        (errors, partial_tree)
        """
        errors: List[SyntaxError_] = []
        good_children: List[Tree] = []

        # Split preserving line numbers by tracking newlines.
        line_offset = 1
        raw_parts = re.split(r"(;)", source)  # keep the delimiter

        buffer = ""
        for segment in raw_parts:
            buffer += segment
            if ";" in segment:
                stmt_src = buffer.strip()
                buffer = ""
                if not stmt_src or stmt_src == ";":
                    # Count lines in this segment for offset tracking.
                    line_offset += segment.count("\n")
                    continue

                # Ensure the statement ends with ';' for the grammar.
                if not stmt_src.endswith(";"):
                    stmt_src += ";"

                # Try LALR first.
                try:
                    sub_tree = self._lark.parse(stmt_src)
                    good_children.extend(sub_tree.children)
                except (UnexpectedCharacters, UnexpectedToken, UnexpectedEOF) as exc:
                    # Try Earley as a fallback (more permissive).
                    try:
                        sub_tree = self._lark_earley.parse(stmt_src)
                        good_children.extend(sub_tree.children)
                    except Exception:
                        err = self._lark_exc_to_syntax_error(exc)
                        # Adjust line number to be file-relative.
                        err.line = max(1, err.line + line_offset - 1)
                        errors.append(err)
                except Exception:
                    errors.append(
                        SyntaxError_(
                            message=f"Could not parse statement: {stmt_src[:60]}",
                            line=line_offset,
                            suggestion="Check the syntax of this RULE statement.",
                        )
                    )

                line_offset += segment.count("\n") + (buffer.count("\n") if buffer else 0)

        # Build a partial tree from successfully parsed statements.
        partial_tree: Optional[Tree] = None
        if good_children:
            partial_tree = Tree("program", good_children)

        return errors, partial_tree

    # ------------------------------------------------------------------
    # Diagnostic helpers (useful for unit tests and the REPL)
    # ------------------------------------------------------------------

    def validate_statement(self, rule_text: str) -> ParseResult:
        """
        Validate a *single* RULE statement (without a trailing semicolon).

        Convenience wrapper that appends the missing semicolon so callers do
        not have to remember it.

        Parameters
        ----------
        rule_text : str
            A single RULE statement, with or without the trailing ``';'``.

        Returns
        -------
        ParseResult
        """
        rule_text = rule_text.strip()
        if not rule_text.endswith(";"):
            rule_text += ";"
        return self.parse(rule_text)

    def list_rule_types(self) -> List[str]:
        """
        Return the list of rule-type names supported by this grammar.

        Useful for IDE auto-complete and error-reporter suggestions.
        """
        return [
            "NO_ROOM_CLASH",
            "NO_TEACHER_CLASH",
            "<identifier> NOT_AVAILABLE <day> <time>",
            "<identifier> ROOM <room_id>",
            "<identifier> TEACHER <teacher_name>",
            "<identifier> DURATION <n>HOUR",
            "<identifier> STUDENTS <n>",
            "<identifier> DAYS_PER_WEEK <n>",
            "<room_id> CAPACITY <n>",
            "<identifier> PREFERRED_TIME <time>",
            "<identifier> PREFERRED_DAY <day>",
            "<group_id> NO_CLASH",
        ]

    def grammar_text(self) -> str:
        """Return the raw Lark grammar string (for display / documentation)."""
        return TCS_GRAMMAR


# ===========================================================================
# Tree visitor utilities
# ===========================================================================

class TCSTreeVisitor:
    """
    Simple recursive visitor for the TCS parse tree.

    Sub-class this and override ``visit_<rule_name>`` methods to process
    specific node types.  The base class visits every node depth-first and
    calls ``visit_default`` for unhandled nodes.

    Example
    -------
    ::

        class RuleCounter(TCSTreeVisitor):
            def __init__(self):
                self.count = 0
            def visit_teacher_unavailable(self, node):
                self.count += 1

        counter = RuleCounter()
        counter.visit(parse_result.tree)
        print(counter.count)
    """

    def visit(self, tree: Optional[Tree]) -> None:
        """Entry point – start visiting from the root *tree*."""
        if tree is None:
            return
        self._dispatch(tree)

    def _dispatch(self, node: Union[Tree, Token]) -> None:
        if isinstance(node, Token):
            self.visit_token(node)
            return
        if not isinstance(node, Tree):
            return
        method_name = f"visit_{node.data}"
        handler = getattr(self, method_name, self.visit_default)
        handler(node)
        for child in node.children:
            self._dispatch(child)

    # Override these in sub-classes:
    def visit_default(self, node: Tree) -> None:  # noqa: B027
        """Called for tree nodes that have no specific handler."""

    def visit_token(self, token: Token) -> None:  # noqa: B027
        """Called for every terminal token."""


class RuleExtractor(TCSTreeVisitor):
    """
    Convenience visitor that extracts all rule declarations from a parse tree
    and returns them as a list of plain dicts.

    Each dict has at minimum a ``"rule_type"`` key plus whatever fields are
    relevant for that rule type.

    Usage
    -----
    ::

        extractor = RuleExtractor()
        extractor.visit(parse_result.tree)
        rules = extractor.rules   # List[dict]
    """

    def __init__(self) -> None:
        self.rules: List[dict] = []

    # ---- global constraints ----

    def visit_global_no_room_clash(self, node: Tree) -> None:
        self.rules.append({"rule_type": "NO_ROOM_CLASH"})

    def visit_global_no_teacher_clash(self, node: Tree) -> None:
        self.rules.append({"rule_type": "NO_TEACHER_CLASH"})

    # ---- teacher/course/room constraints ----

    def visit_teacher_unavailable(self, node: Tree) -> None:
        tokens = _collect_tokens(node)
        self.rules.append({
            "rule_type": "NOT_AVAILABLE",
            "teacher": _get_identifier(tokens),
            "day": _get_day(tokens),
            "time": _get_time(tokens),
        })

    def visit_course_room(self, node: Tree) -> None:
        ids = _collect_ids(node)
        self.rules.append({
            "rule_type": "ROOM",
            "course": ids[0] if len(ids) > 0 else "",
            "room": ids[1] if len(ids) > 1 else "",
        })

    def visit_course_teacher(self, node: Tree) -> None:
        ids = _collect_ids(node)
        self.rules.append({
            "rule_type": "TEACHER",
            "course": ids[0] if len(ids) > 0 else "",
            "teacher": ids[1] if len(ids) > 1 else "",
        })

    def visit_course_duration(self, node: Tree) -> None:
        tokens = _collect_tokens(node)
        dur_tok = next(
            (str(t) for t in tokens if t.type == "DURATION_VALUE"), "1HOUR"
        )
        hours = int(re.match(r"([0-9]+)HOUR", dur_tok).group(1))
        ids = _collect_ids(node)
        self.rules.append({
            "rule_type": "DURATION",
            "course": ids[0] if ids else "",
            "hours": hours,
        })

    def visit_course_students(self, node: Tree) -> None:
        ids = _collect_ids(node)
        tokens = _collect_tokens(node)
        num = _get_integer(tokens)
        self.rules.append({
            "rule_type": "STUDENTS",
            "course": ids[0] if ids else "",
            "count": num,
        })

    def visit_course_days_per_week(self, node: Tree) -> None:
        ids = _collect_ids(node)
        tokens = _collect_tokens(node)
        num = _get_integer(tokens)
        self.rules.append({
            "rule_type": "DAYS_PER_WEEK",
            "course": ids[0] if ids else "",
            "days": num,
        })

    def visit_room_capacity(self, node: Tree) -> None:
        ids = _collect_ids(node)
        tokens = _collect_tokens(node)
        num = _get_integer(tokens)
        self.rules.append({
            "rule_type": "CAPACITY",
            "room": ids[0] if ids else "",
            "capacity": num,
        })

    def visit_course_preferred_time(self, node: Tree) -> None:
        ids = _collect_ids(node)
        tokens = _collect_tokens(node)
        self.rules.append({
            "rule_type": "PREFERRED_TIME",
            "course": ids[0] if ids else "",
            "time": _get_time(tokens),
        })

    def visit_course_preferred_day(self, node: Tree) -> None:
        ids = _collect_ids(node)
        tokens = _collect_tokens(node)
        self.rules.append({
            "rule_type": "PREFERRED_DAY",
            "course": ids[0] if ids else "",
            "day": _get_day(tokens),
        })

    def visit_group_no_clash(self, node: Tree) -> None:
        ids = _collect_ids(node)
        self.rules.append({
            "rule_type": "NO_CLASH",
            "group": ids[0] if ids else "",
        })


# ---------------------------------------------------------------------------
# Helpers used by RuleExtractor
# ---------------------------------------------------------------------------

def _collect_tokens(node: Tree) -> List[Token]:
    """Flatten all Token objects under *node* (depth-first)."""
    tokens: List[Token] = []

    def _walk(n: Union[Tree, Token]) -> None:
        if isinstance(n, Token):
            tokens.append(n)
        elif isinstance(n, Tree):
            for child in n.children:
                _walk(child)

    _walk(node)
    return tokens


def _collect_ids(node: Tree) -> List[str]:
    """Return string values of all ID_TOKEN terminals under *node*."""
    return [str(t) for t in _collect_tokens(node) if t.type == "ID_TOKEN"]


def _get_identifier(tokens: List[Token]) -> str:
    ids = [str(t) for t in tokens if t.type == "ID_TOKEN"]
    return ids[0] if ids else ""


def _get_day(tokens: List[Token]) -> str:
    day_types = {"MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"}
    for t in tokens:
        if t.type in day_types:
            return str(t)
    return ""


def _get_time(tokens: List[Token]) -> str:
    time_types = {
        "TIME_8AM", "TIME_9AM", "TIME_10AM", "TIME_11AM", "TIME_12PM",
        "TIME_1PM", "TIME_2PM", "TIME_3PM", "TIME_4PM", "TIME_5PM",
    }
    for t in tokens:
        if t.type in time_types:
            return str(t)
    return ""


def _get_integer(tokens: List[Token]) -> int:
    for t in tokens:
        if t.type == "INTEGER":
            try:
                return int(str(t))
            except ValueError:
                pass
    return 0


# ===========================================================================
# Module-level convenience function
# ===========================================================================

def parse_source(source: str) -> ParseResult:
    """
    Module-level shortcut: create a :py:class:`Parser` and call
    :py:meth:`~Parser.parse`.

    Parameters
    ----------
    source : str
        Raw TCS source text.

    Returns
    -------
    ParseResult
    """
    return Parser().parse(source)


def extract_rules(source: str) -> List[dict]:
    """
    Parse *source* and return all recognised rules as a list of dicts.

    Returns an empty list if parsing fails entirely.
    """
    result = parse_source(source)
    if result.tree is None:
        return []
    extractor = RuleExtractor()
    extractor.visit(result.tree)
    return extractor.rules


# ===========================================================================
# CLI entry-point (python -m compiler.parser <file.tcs>)
# ===========================================================================

def _main() -> None:  # pragma: no cover
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m compiler.parser <file.tcs>")
        sys.exit(1)

    path = sys.argv[1]
    try:
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
    except OSError as exc:
        print(f"Error reading file: {exc}")
        sys.exit(1)

    result = parse_source(source)

    if result.success:
        print(f"✓ Parse succeeded — {result.statement_count} statement(s).\n")
        print(result.format_tree_pretty())
    else:
        print(f"✗ Parse failed — {len(result.errors)} error(s).\n")
        for err in result.errors:
            print(err)
        if result.tree:
            print("\nPartial tree (from recovered statements):")
            print(result.format_tree_pretty())

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    _main()
