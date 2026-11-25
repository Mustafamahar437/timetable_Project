"""
ir_generator.py — Intermediate Representation (IR) Generator
=============================================================
Smart University Timetable Constraint Compiler
Phase 3 of the compiler pipeline: Parse Tree → IR Instructions

Compiler Pipeline:
  Source (.tcs) → Lexer → Parser → Semantic Analyzer → [IR Generator] → Code Generator → Solver

Role of the IR Generator
-------------------------
The IR Generator walks the Lark parse tree produced by parser.py and emits a
flat, structured list of *IR instructions* — an architecture-neutral, solver-
neutral representation of every timetabling constraint declared in the source
file.

Using an IR (rather than going directly from the parse tree to OR-Tools code)
gives us several compiler benefits:

  1. **Separation of concerns** — the Code Generator can focus purely on
     translating IR → solver constraints without touching parse-tree logic.
  2. **Optimisation passes** — future passes (dead-rule elimination, constant
     folding, duplicate detection) operate on a clean data structure.
  3. **Multiple back-ends** — the same IR can target OR-Tools, Z3, or even a
     plain JSON export / human-readable schedule table.
  4. **Debugging / introspection** — Streamlit's IR tab can render the flat
     list in a table, making it easy to spot mis-compiled rules.

IR Instruction Types (mirrors the DSL rule types 1-to-1)
---------------------------------------------------------
  GLOBAL_CONSTRAINT      — NO_ROOM_CLASH | NO_TEACHER_CLASH
  TEACHER_UNAVAILABLE    — teacher blocked on (day, time)
  COURSE_ROOM            — course pinned to a room
  COURSE_TEACHER         — course assigned to a teacher
  COURSE_DURATION        — session length in hours
  COURSE_STUDENTS        — enrolment count (used for capacity checking)
  COURSE_DAYS_PER_WEEK   — how many sessions per week
  ROOM_CAPACITY          — room's max occupancy
  COURSE_PREFERRED_TIME  — soft preferred start time
  COURSE_PREFERRED_DAY   — soft preferred day
  GROUP_NO_CLASH         — student group must not have overlapping sessions
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Lark is used by the parser; we walk its Tree / Token nodes here.
# We import defensively so the module can still be *imported* even when lark
# is not installed (the caller will get a runtime error only when generate()
# is actually called).
# ---------------------------------------------------------------------------
try:
    from lark import Token, Tree
    from lark.visitors import Visitor_Recursive
    _LARK_AVAILABLE = True
except ImportError:  # pragma: no cover
    _LARK_AVAILABLE = False
    # Provide stubs so type annotations below don't crash at import time.
    class Tree:  # type: ignore
        pass
    class Token:  # type: ignore
        pass
    class Visitor_Recursive:  # type: ignore
        pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IR Instruction dataclass
# ---------------------------------------------------------------------------

@dataclass
class IRInstruction:
    """
    A single, flat IR instruction.

    ``type`` identifies the kind of constraint (e.g. ``"COURSE_ROOM"``).
    All additional constraint-specific fields are stored in ``fields``.

    Example
    -------
    >>> IRInstruction(type="COURSE_ROOM", fields={"course": "CS101", "room": "R1"})
    IRInstruction(type='COURSE_ROOM', fields={'course': 'CS101', 'room': 'R1'})
    """

    type: str
    fields: Dict[str, Any] = field(default_factory=dict)

    @property
    def params(self) -> Dict[str, Any]:
        """Alias for fields to support both .fields and .params access."""
        return self.fields

    @params.setter
    def params(self, value: Dict[str, Any]) -> None:
        self.fields = value

    # ------------------------------------------------------------------
    # Convenience accessors — keep code-generator code readable.
    # ------------------------------------------------------------------
    def __getattr__(self, name: str) -> Any:
        """Allow dot-access into ``fields`` (e.g. ``instr.course``)."""
        try:
            return self.fields[name]
        except KeyError:
            raise AttributeError(
                f"IRInstruction has no attribute '{name}' "
                f"(type={self.type!r}, fields={self.fields!r})"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable dict (flattened, type included)."""
        return {"type": self.type, **self.fields}

    def __repr__(self) -> str:
        kv = ", ".join(f"{k}={v!r}" for k, v in self.fields.items())
        return f"IRInstruction(type={self.type!r}, {kv})"


# ---------------------------------------------------------------------------
# IR Result container
# ---------------------------------------------------------------------------

@dataclass
class IRResult:
    """
    The output of :class:`IRGenerator`.

    Attributes
    ----------
    instructions : List[IRInstruction]
        Ordered list of all IR instructions produced from the parse tree.
    json_repr : str
        Pretty-printed JSON string of the full instruction list.
        Ready to serialise to disk or display in Streamlit.
    errors : List[str]
        Any non-fatal warnings / errors encountered during IR generation.
        A non-empty list does *not* mean generation failed completely; it
        means some rules may have been skipped.
    success : bool
        ``True`` when generation completed without fatal errors.
    """

    instructions: List[IRInstruction] = field(default_factory=list)
    json_repr: str = ""
    errors: List[str] = field(default_factory=list)
    success: bool = True

    # ------------------------------------------------------------------
    # Convenience helpers used by Streamlit / unit tests
    # ------------------------------------------------------------------

    def as_dicts(self) -> List[Dict[str, Any]]:
        """Return instructions as a list of plain dicts (for DataFrame)."""
        return [instr.to_dict() for instr in self.instructions]

    def by_type(self, ir_type: str) -> List[IRInstruction]:
        """Filter instructions by type."""
        return [i for i in self.instructions if i.type == ir_type]

    def summary(self) -> Dict[str, int]:
        """Return a count of each IR instruction type."""
        counts: Dict[str, int] = {}
        for instr in self.instructions:
            counts[instr.type] = counts.get(instr.type, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Valid vocabulary (mirrors the DSL spec)
# ---------------------------------------------------------------------------

VALID_DAYS = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday"}

VALID_TIMES = {
    "8AM", "9AM", "10AM", "11AM", "12PM",
    "1PM", "2PM", "3PM", "4PM", "5PM",
}

# Map DSL token types / rule keyword strings to their canonical IR type.
_RULE_KEYWORD_TO_IR: Dict[str, str] = {
    "NO_ROOM_CLASH":    "GLOBAL_CONSTRAINT",
    "NO_TEACHER_CLASH": "GLOBAL_CONSTRAINT",
    "NOT_AVAILABLE":    "TEACHER_UNAVAILABLE",
    "ROOM":             "COURSE_ROOM",
    "TEACHER":          "COURSE_TEACHER",
    "DURATION":         "COURSE_DURATION",
    "STUDENTS":         "COURSE_STUDENTS",
    "DAYS_PER_WEEK":    "COURSE_DAYS_PER_WEEK",
    "CAPACITY":         "ROOM_CAPACITY",
    "PREFERRED_TIME":   "COURSE_PREFERRED_TIME",
    "PREFERRED_DAY":    "COURSE_PREFERRED_DAY",
    "NO_CLASH":         "GROUP_NO_CLASH",
}


# ---------------------------------------------------------------------------
# Parse-tree visitor  (walks the Lark Tree produced by parser.py)
# ---------------------------------------------------------------------------

class _IRVisitor:
    """
    Recursive descent visitor over a Lark parse tree.

    Each ``visit_<rule_name>`` method handles one grammar rule and appends
    zero or more :class:`IRInstruction` objects to ``self.instructions``.

    The visitor is *not* a subclass of ``lark.Visitor`` because we need to
    support both Lark Tree objects and the dict-based fallback representation
    (for unit tests that don't want to spin up the full parser).
    """

    def __init__(self) -> None:
        self.instructions: List[IRInstruction] = []
        self.errors: List[str] = []

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def visit(self, tree: Any) -> None:
        """Visit a node — dispatches on the ``data`` attribute (Lark convention)."""
        if tree is None:
            return

        # Support both real Lark Tree objects and plain dicts (for testing).
        if isinstance(tree, dict):
            self._visit_dict(tree)
            return

        if not _LARK_AVAILABLE:
            self.errors.append(
                "lark is not installed; cannot walk a real parse tree."
            )
            return

        if not isinstance(tree, Tree):
            # Could be a Token leaf — ignore.
            return

        rule_name: str = tree.data  # e.g. "start", "rule_stmt", …

        # Dispatch: try the specific handler first; fall back to generic.
        handler = getattr(self, f"visit_{rule_name}", self._visit_generic)
        handler(tree)

    def _visit_generic(self, tree: "Tree") -> None:
        """Default handler: recurse into all children."""
        for child in tree.children:
            if isinstance(child, Tree):
                self.visit(child)

    # ------------------------------------------------------------------
    # Grammar rule handlers
    # ------------------------------------------------------------------

    def visit_start(self, tree: "Tree") -> None:
        """Root rule — just recurse."""
        self._visit_generic(tree)

    def visit_program(self, tree: "Tree") -> None:
        """Top-level program node — just recurse."""
        self._visit_generic(tree)

    def visit_rule_stmt(self, tree: "Tree") -> None:
        """
        Handle a single RULE statement.

        Grammar (from parser.py):
            rule_stmt : "RULE" rule_body ";"
        """
        # The rule body is the first meaningful child after the RULE keyword.
        # With Lark, keywords consumed by the grammar (string literals) are
        # *not* included as children when using `keep_all_tokens=False`.
        # So children[0] is typically the rule_body sub-tree.
        if not tree.children:
            self.errors.append("Empty rule_stmt node encountered.")
            return

        body = tree.children[0] if isinstance(tree.children[0], Tree) else None
        if body is None:
            # Maybe the first child is a Token (edge case with keep_all_tokens)
            # Try scanning all children for a Tree node.
            for child in tree.children:
                if isinstance(child, Tree):
                    body = child
                    break

        if body is None:
            self.errors.append(
                f"rule_stmt has no Tree child: {tree!r}"
            )
            return

        self.visit(body)

    # -- Global constraints -------------------------------------------

    def visit_no_room_clash(self, tree: "Tree") -> None:
        """RULE NO_ROOM_CLASH ;"""
        self.instructions.append(
            IRInstruction(
                type="GLOBAL_CONSTRAINT",
                fields={"constraint_name": "NO_ROOM_CLASH"},
            )
        )

    def visit_no_teacher_clash(self, tree: "Tree") -> None:
        """RULE NO_TEACHER_CLASH ;"""
        self.instructions.append(
            IRInstruction(
                type="GLOBAL_CONSTRAINT",
                fields={"constraint_name": "NO_TEACHER_CLASH"},
            )
        )

    # Aliases matching Lark CST node names
    visit_global_no_room_clash = visit_no_room_clash
    visit_global_no_teacher_clash = visit_no_teacher_clash

    # -- Teacher unavailability ---------------------------------------

    def visit_teacher_unavailable(self, tree: "Tree") -> None:
        """
        RULE <teacher_name> NOT_AVAILABLE <day> <time> ;

        Grammar:
            teacher_unavailable : IDENTIFIER "NOT_AVAILABLE" DAY TIME
        """
        tokens = _extract_tokens(tree)
        if len(tokens) < 3:
            self.errors.append(
                f"teacher_unavailable rule has too few tokens: {tokens}"
            )
            return

        teacher = str(tokens[0])
        day     = str(tokens[1])
        time    = str(tokens[2])

        if day not in VALID_DAYS:
            self.errors.append(
                f"Invalid day '{day}' in NOT_AVAILABLE rule for '{teacher}'. "
                f"Valid days: {sorted(VALID_DAYS)}"
            )

        if time not in VALID_TIMES:
            self.errors.append(
                f"Invalid time '{time}' in NOT_AVAILABLE rule for '{teacher}'. "
                f"Valid times: {sorted(VALID_TIMES)}"
            )

        self.instructions.append(
            IRInstruction(
                type="TEACHER_UNAVAILABLE",
                fields={"teacher": teacher, "day": day, "time": time},
            )
        )

    # -- Course–room assignment ---------------------------------------

    def visit_course_room(self, tree: "Tree") -> None:
        """
        RULE <course_id> ROOM <room_id> ;

        Grammar:
            course_room : IDENTIFIER "ROOM" IDENTIFIER
        """
        tokens = _extract_tokens(tree)
        if len(tokens) < 2:
            self.errors.append(
                f"course_room rule has too few tokens: {tokens}"
            )
            return

        self.instructions.append(
            IRInstruction(
                type="COURSE_ROOM",
                fields={"course": str(tokens[0]), "room": str(tokens[1])},
            )
        )

    # -- Course–teacher assignment ------------------------------------

    def visit_course_teacher(self, tree: "Tree") -> None:
        """
        RULE <course_id> TEACHER <teacher_name> ;

        Grammar:
            course_teacher : IDENTIFIER "TEACHER" IDENTIFIER
        """
        tokens = _extract_tokens(tree)
        if len(tokens) < 2:
            self.errors.append(
                f"course_teacher rule has too few tokens: {tokens}"
            )
            return

        self.instructions.append(
            IRInstruction(
                type="COURSE_TEACHER",
                fields={"course": str(tokens[0]), "teacher": str(tokens[1])},
            )
        )

    # -- Course duration ----------------------------------------------

    def visit_course_duration(self, tree: "Tree") -> None:
        """
        RULE <course_id> DURATION <n>HOUR ;

        Grammar:
            course_duration : IDENTIFIER "DURATION" NUMBER "HOUR"
        """
        tokens = _extract_tokens(tree)
        if len(tokens) < 2:
            self.errors.append(
                f"course_duration rule has too few tokens: {tokens}"
            )
            return

        course = str(tokens[0])
        raw_val = str(tokens[1]).upper().replace("HOURS", "").replace("HOUR", "").replace("H", "").strip()
        try:
            hours = int(raw_val)
        except (ValueError, TypeError):
            self.errors.append(
                f"Invalid duration value '{tokens[1]}' for course '{course}'. "
                "Expected integer."
            )
            return

        if not (1 <= hours <= 3):
            self.errors.append(
                f"Duration {hours} for course '{course}' is outside the "
                "allowed range 1–3 hours (recorded anyway)."
            )

        self.instructions.append(
            IRInstruction(
                type="COURSE_DURATION",
                fields={"course": course, "hours": hours},
            )
        )

    # -- Course student count -----------------------------------------

    def visit_course_students(self, tree: "Tree") -> None:
        """
        RULE <course_id> STUDENTS <n> ;

        Grammar:
            course_students : IDENTIFIER "STUDENTS" NUMBER
        """
        tokens = _extract_tokens(tree)
        if len(tokens) < 2:
            self.errors.append(
                f"course_students rule has too few tokens: {tokens}"
            )
            return

        course = str(tokens[0])
        try:
            count = int(tokens[1])
        except (ValueError, TypeError):
            self.errors.append(
                f"Invalid student count '{tokens[1]}' for course '{course}'."
            )
            return

        self.instructions.append(
            IRInstruction(
                type="COURSE_STUDENTS",
                fields={"course": course, "count": count},
            )
        )

    # -- Course days per week -----------------------------------------

    def visit_course_days_per_week(self, tree: "Tree") -> None:
        """
        RULE <course_id> DAYS_PER_WEEK <n> ;

        Grammar:
            course_days_per_week : IDENTIFIER "DAYS_PER_WEEK" NUMBER
        """
        tokens = _extract_tokens(tree)
        if len(tokens) < 2:
            self.errors.append(
                f"course_days_per_week rule has too few tokens: {tokens}"
            )
            return

        course = str(tokens[0])
        try:
            days = int(tokens[1])
        except (ValueError, TypeError):
            self.errors.append(
                f"Invalid days_per_week value '{tokens[1]}' for course '{course}'."
            )
            return

        if not (1 <= days <= 5):
            self.errors.append(
                f"DAYS_PER_WEEK={days} for course '{course}' is outside the "
                "allowed range 1–5 (recorded anyway)."
            )

        self.instructions.append(
            IRInstruction(
                type="COURSE_DAYS_PER_WEEK",
                fields={"course": course, "days": days},
            )
        )

    # -- Room capacity ------------------------------------------------

    def visit_room_capacity(self, tree: "Tree") -> None:
        """
        RULE <room_id> CAPACITY <n> ;

        Grammar:
            room_capacity : IDENTIFIER "CAPACITY" NUMBER
        """
        tokens = _extract_tokens(tree)
        if len(tokens) < 2:
            self.errors.append(
                f"room_capacity rule has too few tokens: {tokens}"
            )
            return

        room = str(tokens[0])
        try:
            capacity = int(tokens[1])
        except (ValueError, TypeError):
            self.errors.append(
                f"Invalid capacity value '{tokens[1]}' for room '{room}'."
            )
            return

        self.instructions.append(
            IRInstruction(
                type="ROOM_CAPACITY",
                fields={"room": room, "capacity": capacity},
            )
        )

    # -- Course preferred time ----------------------------------------

    def visit_course_preferred_time(self, tree: "Tree") -> None:
        """
        RULE <course_id> PREFERRED_TIME <time> ;

        Grammar:
            course_preferred_time : IDENTIFIER "PREFERRED_TIME" TIME
        """
        tokens = _extract_tokens(tree)
        if len(tokens) < 2:
            self.errors.append(
                f"course_preferred_time rule has too few tokens: {tokens}"
            )
            return

        course = str(tokens[0])
        time   = str(tokens[1])

        if time not in VALID_TIMES:
            self.errors.append(
                f"Invalid preferred time '{time}' for course '{course}'. "
                f"Valid times: {sorted(VALID_TIMES)}"
            )

        self.instructions.append(
            IRInstruction(
                type="COURSE_PREFERRED_TIME",
                fields={"course": course, "time": time},
            )
        )

    # -- Course preferred day -----------------------------------------

    def visit_course_preferred_day(self, tree: "Tree") -> None:
        """
        RULE <course_id> PREFERRED_DAY <day> ;

        Grammar:
            course_preferred_day : IDENTIFIER "PREFERRED_DAY" DAY
        """
        tokens = _extract_tokens(tree)
        if len(tokens) < 2:
            self.errors.append(
                f"course_preferred_day rule has too few tokens: {tokens}"
            )
            return

        course = str(tokens[0])
        day    = str(tokens[1])

        if day not in VALID_DAYS:
            self.errors.append(
                f"Invalid preferred day '{day}' for course '{course}'. "
                f"Valid days: {sorted(VALID_DAYS)}"
            )

        self.instructions.append(
            IRInstruction(
                type="COURSE_PREFERRED_DAY",
                fields={"course": course, "day": day},
            )
        )

    # -- Group no-clash -----------------------------------------------

    def visit_group_no_clash(self, tree: "Tree") -> None:
        """
        RULE <group_id> NO_CLASH ;

        Grammar:
            group_no_clash : IDENTIFIER "NO_CLASH"
        """
        tokens = _extract_tokens(tree)
        if not tokens:
            self.errors.append("group_no_clash rule has no group identifier.")
            return

        self.instructions.append(
            IRInstruction(
                type="GROUP_NO_CLASH",
                fields={"group": str(tokens[0])},
            )
        )

    # ------------------------------------------------------------------
    # Dict-based tree fallback (for unit tests / JSON parse trees)
    # ------------------------------------------------------------------

    def _visit_dict(self, node: dict) -> None:
        """
        Handle a parse-tree node represented as a plain Python dict.

        Expected shape (matches parser.get_tree_as_dict()):
          {
            "type": "rule_stmt",          # or "token"
            "data": "...",                # rule name  (for Tree nodes)
            "value": "...",               # token value (for Token nodes)
            "children": [ ... ]           # child nodes
          }
        """
        node_type = node.get("type", "")
        if node_type == "token":
            return  # Leaf — nothing to visit.

        rule_name: str = node.get("data", "")
        handler = getattr(self, f"visit_{rule_name}", None)

        if handler is not None:
            # Wrap the dict in a lightweight adapter so the same handler code
            # works for both real Lark trees and dict trees.
            adapted = _DictTreeAdapter(node)
            handler(adapted)
        else:
            # Recurse into children.
            for child in node.get("children", []):
                if isinstance(child, dict):
                    self._visit_dict(child)


# ---------------------------------------------------------------------------
# Lightweight adapter: wraps a dict parse-tree node so it quacks like a
# lark.Tree (has .data and .children attributes).
# ---------------------------------------------------------------------------

class _DictTreeAdapter:
    """Makes a plain dict look like a lark.Tree for the visitor handlers."""

    def __init__(self, d: dict) -> None:
        self.data: str = d.get("data", "")
        self._children_raw = d.get("children", [])

    @property
    def children(self) -> List[Any]:
        """Return children as _DictTreeAdapter or _DictTokenAdapter."""
        result = []
        for child in self._children_raw:
            if not isinstance(child, dict):
                result.append(child)
            elif child.get("type") == "token":
                result.append(_DictTokenAdapter(child))
            else:
                result.append(_DictTreeAdapter(child))
        return result


class _DictTokenAdapter:
    """Makes a plain dict look like a lark.Token for _extract_tokens()."""

    def __init__(self, d: dict) -> None:
        self.type:  str = d.get("token_type", "UNKNOWN")
        self.value: str = str(d.get("value", ""))

    def __str__(self) -> str:
        return self.value


# ---------------------------------------------------------------------------
# Helper: extract all leaf Token values from a tree node
# ---------------------------------------------------------------------------

_IR_SKIP_TOKENS = {
    "RULE_KW", "ROOM_KW", "TEACHER_KW", "NOT_AVAILABLE_KW",
    "DURATION_KW", "HOUR_KW", "STUDENTS_KW", "DAYS_PER_WEEK_KW",
    "CAPACITY_KW", "PREFERRED_TIME_KW", "PREFERRED_DAY_KW",
    "NO_CLASH_KW", "NO_ROOM_CLASH_KW", "NO_TEACHER_CLASH_KW",
    "SEMICOLON", "NEWLINE", "WS"
}

_IR_SKIP_VALUES = {
    "RULE", "ROOM", "TEACHER", "NOT_AVAILABLE", "DURATION",
    "HOUR", "HOURS", "STUDENTS", "DAYS_PER_WEEK", "CAPACITY",
    "PREFERRED_TIME", "PREFERRED_DAY", "NO_CLASH", "NO_ROOM_CLASH",
    "NO_TEACHER_CLASH", ";"
}


def _extract_tokens(tree: Any) -> List[Any]:
    """
    Collect all value-bearing leaf Token children of *tree*, in order.
    Punctuation and rule keywords (RULE, ROOM, etc.) are skipped.
    """
    tokens = []
    for child in tree.children:
        if hasattr(child, "type") and child.type in _IR_SKIP_TOKENS:
            continue
        if hasattr(child, "value") and str(child.value).upper() in _IR_SKIP_VALUES:
            continue
        if hasattr(child, "children"):
            tokens.extend(_extract_tokens(child))
        else:
            val = getattr(child, "value", str(child))
            if str(val).upper() not in _IR_SKIP_VALUES:
                tokens.append(val)
    return tokens


# ---------------------------------------------------------------------------
# Duplicate-elimination optimisation pass
# ---------------------------------------------------------------------------

def _deduplicate(instructions: List[IRInstruction]) -> List[IRInstruction]:
    """
    Remove exact duplicate instructions while preserving order.

    Two instructions are duplicates when both their ``type`` and ``fields``
    match.  We keep the *first* occurrence (earlier source-line wins).
    """
    seen: set = set()
    unique: List[IRInstruction] = []
    for instr in instructions:
        key = (instr.type, json.dumps(instr.fields, sort_keys=True))
        if key not in seen:
            seen.add(key)
            unique.append(instr)
        else:
            logger.debug("IR duplicate eliminated: %r", instr)
    return unique


# ---------------------------------------------------------------------------
# Main IR Generator class
# ---------------------------------------------------------------------------

class IRGenerator:
    """
    Compiler Phase 3 — Intermediate Representation Generator.

    Transforms the Lark parse tree (produced by :class:`~compiler.parser.Parser`)
    into a flat, ordered list of :class:`IRInstruction` objects.

    Usage
    -----
    ::

        from compiler.parser import Parser
        from compiler.ir_generator import IRGenerator

        parser = Parser()
        parse_result = parser.parse(source_code)

        if parse_result.success:
            ir_gen = IRGenerator()
            ir_result = ir_gen.generate(parse_result.tree)

            for instr in ir_result.instructions:
                print(instr)

    Design Notes
    ------------
    * The generator is *stateless* between calls — each call to
      :meth:`generate` creates a fresh :class:`_IRVisitor`.
    * Non-fatal errors (e.g. out-of-range values) are collected in
      ``IRResult.errors``; the generator still emits the instruction so
      downstream phases can decide what to do.
    * Fatal errors (e.g. unparseable tree) set ``IRResult.success = False``
      and return an empty instruction list.
    """

    def __init__(self, deduplicate: bool = True) -> None:
        """
        Parameters
        ----------
        deduplicate : bool
            When ``True`` (default), exact duplicate IR instructions are
            silently removed in a post-processing pass.
        """
        self._deduplicate = deduplicate

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, parse_tree: Any) -> IRResult:
        """
        Walk *parse_tree* and produce an :class:`IRResult`.

        Parameters
        ----------
        parse_tree : lark.Tree | dict | None
            The parse tree returned by ``Parser.parse().tree``.
            Also accepts the dict form returned by
            ``Parser.get_tree_as_dict()`` (for interoperability with
            Streamlit state).

        Returns
        -------
        IRResult
            Always returns a result object; never raises.
        """
        if parse_tree is None:
            logger.error("ir_generator.generate() received None parse_tree.")
            return IRResult(
                success=False,
                errors=["parse_tree is None — IR generation aborted."],
            )

        visitor = _IRVisitor()

        try:
            visitor.visit(parse_tree)
        except Exception as exc:  # pragma: no cover
            logger.exception("Unexpected error during IR generation.")
            return IRResult(
                success=False,
                errors=[
                    f"Fatal IR generation error: {type(exc).__name__}: {exc}"
                ],
            )

        instructions = visitor.instructions
        errors       = visitor.errors

        # --- Optimisation pass: remove duplicates -------------------------
        if self._deduplicate:
            before = len(instructions)
            instructions = _deduplicate(instructions)
            removed = before - len(instructions)
            if removed:
                logger.info(
                    "IR deduplication: removed %d duplicate instruction(s).",
                    removed,
                )

        # --- Build JSON representation ------------------------------------
        try:
            json_repr = json.dumps(
                [instr.to_dict() for instr in instructions],
                indent=2,
                ensure_ascii=False,
                default=str,  # handles any non-serialisable stragglers
            )
        except (TypeError, ValueError) as exc:  # pragma: no cover
            json_repr = "[]"
            errors.append(f"JSON serialisation error: {exc}")

        success = len([e for e in errors if _is_fatal(e)]) == 0

        result = IRResult(
            instructions=instructions,
            json_repr=json_repr,
            errors=errors,
            success=success,
        )

        logger.info(
            "IR generation complete: %d instruction(s), %d error(s).",
            len(instructions),
            len(errors),
        )
        return result

    # ------------------------------------------------------------------
    # Convenience: generate from raw source (skips external parser dep)
    # ------------------------------------------------------------------

    def generate_from_source(self, source: str) -> IRResult:
        """
        Parse *source* with the bundled parser and immediately generate IR.

        This is a convenience wrapper; prefer calling the parser yourself
        so you can inspect parse errors separately.

        Parameters
        ----------
        source : str
            Raw ``.tcs`` source code.
        """
        try:
            from compiler.parser import Parser  # local import to avoid circularity
        except ImportError as exc:
            return IRResult(
                success=False,
                errors=[f"Cannot import compiler.parser: {exc}"],
            )

        p = Parser()
        parse_result = p.parse(source)

        if not parse_result.success:
            error_messages = [str(e) for e in parse_result.errors]
            return IRResult(
                success=False,
                errors=["Parse failed — IR not generated."] + error_messages,
            )

        return self.generate(parse_result.tree)

    # ------------------------------------------------------------------
    # Pretty-print helpers (for REPL / debugging)
    # ------------------------------------------------------------------

    def format_instructions(self, ir_result: IRResult) -> str:
        """
        Format an :class:`IRResult` as a human-readable table string.

        ::

            #  TYPE                    FIELDS
            1  GLOBAL_CONSTRAINT       constraint_name=NO_ROOM_CLASH
            2  COURSE_ROOM             course=CS101, room=R-101
            …
        """
        lines = [
            f"{'#':<4} {'TYPE':<28} FIELDS",
            "-" * 72,
        ]
        for idx, instr in enumerate(ir_result.instructions, start=1):
            fields_str = ", ".join(
                f"{k}={v}" for k, v in instr.fields.items()
            )
            lines.append(f"{idx:<4} {instr.type:<28} {fields_str}")

        if ir_result.errors:
            lines.append("")
            lines.append("ERRORS / WARNINGS:")
            for err in ir_result.errors:
                lines.append(f"  ⚠  {err}")

        return "\n".join(lines)

    def get_summary_dict(self, ir_result: IRResult) -> Dict[str, Any]:
        """
        Return a JSON-serialisable summary suitable for Streamlit metrics.

        ::

            {
              "total_instructions": 12,
              "by_type": {"GLOBAL_CONSTRAINT": 2, "COURSE_ROOM": 4, …},
              "errors": [],
              "success": true
            }
        """
        return {
            "total_instructions": len(ir_result.instructions),
            "by_type": ir_result.summary(),
            "errors": ir_result.errors,
            "success": ir_result.success,
        }


# ---------------------------------------------------------------------------
# Internal utility
# ---------------------------------------------------------------------------

def _is_fatal(error_message: str) -> bool:
    """
    Heuristic: an error is *fatal* if it mentions a critical failure rather
    than just a range violation or unknown-but-recorded token.
    """
    fatal_keywords = ["Fatal", "aborted", "None", "Cannot import"]
    return any(kw in error_message for kw in fatal_keywords)


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

def generate_ir(parse_tree: Any, *, deduplicate: bool = True) -> IRResult:
    """
    Module-level shortcut: create an :class:`IRGenerator` and call generate.

    Parameters
    ----------
    parse_tree : lark.Tree | dict | None
        Parse tree from ``compiler.parser.Parser``.
    deduplicate : bool
        Remove exact duplicate instructions (default ``True``).

    Returns
    -------
    IRResult
    """
    return IRGenerator(deduplicate=deduplicate).generate(parse_tree)


# ---------------------------------------------------------------------------
# Self-test / demo (run as __main__)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    """
    Quick smoke-test: build a minimal fake parse tree as a plain dict and
    verify the IR generator handles every instruction type correctly.
    """
    import sys

    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

    # Build a dict-style parse tree that exercises every handler.
    fake_tree: dict = {
        "type": "tree",
        "data": "start",
        "children": [
            # 1. NO_ROOM_CLASH
            {
                "type": "tree", "data": "rule_stmt",
                "children": [
                    {"type": "tree", "data": "no_room_clash", "children": []}
                ],
            },
            # 2. NO_TEACHER_CLASH
            {
                "type": "tree", "data": "rule_stmt",
                "children": [
                    {"type": "tree", "data": "no_teacher_clash", "children": []}
                ],
            },
            # 3. TEACHER_UNAVAILABLE
            {
                "type": "tree", "data": "rule_stmt",
                "children": [
                    {
                        "type": "tree", "data": "teacher_unavailable",
                        "children": [
                            {"type": "token", "token_type": "IDENTIFIER", "value": "Dr_Ali"},
                            {"type": "token", "token_type": "DAY",        "value": "Monday"},
                            {"type": "token", "token_type": "TIME",       "value": "9AM"},
                        ],
                    }
                ],
            },
            # 4. COURSE_ROOM
            {
                "type": "tree", "data": "rule_stmt",
                "children": [
                    {
                        "type": "tree", "data": "course_room",
                        "children": [
                            {"type": "token", "token_type": "IDENTIFIER", "value": "CS101"},
                            {"type": "token", "token_type": "IDENTIFIER", "value": "R-101"},
                        ],
                    }
                ],
            },
            # 5. COURSE_TEACHER
            {
                "type": "tree", "data": "rule_stmt",
                "children": [
                    {
                        "type": "tree", "data": "course_teacher",
                        "children": [
                            {"type": "token", "token_type": "IDENTIFIER", "value": "CS101"},
                            {"type": "token", "token_type": "IDENTIFIER", "value": "Dr_Ali"},
                        ],
                    }
                ],
            },
            # 6. COURSE_DURATION
            {
                "type": "tree", "data": "rule_stmt",
                "children": [
                    {
                        "type": "tree", "data": "course_duration",
                        "children": [
                            {"type": "token", "token_type": "IDENTIFIER", "value": "CS101"},
                            {"type": "token", "token_type": "NUMBER",     "value": "2"},
                        ],
                    }
                ],
            },
            # 7. COURSE_STUDENTS
            {
                "type": "tree", "data": "rule_stmt",
                "children": [
                    {
                        "type": "tree", "data": "course_students",
                        "children": [
                            {"type": "token", "token_type": "IDENTIFIER", "value": "CS101"},
                            {"type": "token", "token_type": "NUMBER",     "value": "45"},
                        ],
                    }
                ],
            },
            # 8. COURSE_DAYS_PER_WEEK
            {
                "type": "tree", "data": "rule_stmt",
                "children": [
                    {
                        "type": "tree", "data": "course_days_per_week",
                        "children": [
                            {"type": "token", "token_type": "IDENTIFIER", "value": "CS101"},
                            {"type": "token", "token_type": "NUMBER",     "value": "3"},
                        ],
                    }
                ],
            },
            # 9. ROOM_CAPACITY
            {
                "type": "tree", "data": "rule_stmt",
                "children": [
                    {
                        "type": "tree", "data": "room_capacity",
                        "children": [
                            {"type": "token", "token_type": "IDENTIFIER", "value": "R-101"},
                            {"type": "token", "token_type": "NUMBER",     "value": "60"},
                        ],
                    }
                ],
            },
            # 10. COURSE_PREFERRED_TIME
            {
                "type": "tree", "data": "rule_stmt",
                "children": [
                    {
                        "type": "tree", "data": "course_preferred_time",
                        "children": [
                            {"type": "token", "token_type": "IDENTIFIER", "value": "CS101"},
                            {"type": "token", "token_type": "TIME",       "value": "10AM"},
                        ],
                    }
                ],
            },
            # 11. COURSE_PREFERRED_DAY
            {
                "type": "tree", "data": "rule_stmt",
                "children": [
                    {
                        "type": "tree", "data": "course_preferred_day",
                        "children": [
                            {"type": "token", "token_type": "IDENTIFIER", "value": "CS101"},
                            {"type": "token", "token_type": "DAY",        "value": "Wednesday"},
                        ],
                    }
                ],
            },
            # 12. GROUP_NO_CLASH
            {
                "type": "tree", "data": "rule_stmt",
                "children": [
                    {
                        "type": "tree", "data": "group_no_clash",
                        "children": [
                            {"type": "token", "token_type": "IDENTIFIER", "value": "GROUP_A"},
                        ],
                    }
                ],
            },
        ],
    }

    gen = IRGenerator(deduplicate=True)
    result = gen.generate(fake_tree)

    print("\n" + "=" * 72)
    print("IR GENERATOR SMOKE-TEST")
    print("=" * 72)
    print(gen.format_instructions(result))
    print()
    print("Summary:", gen.get_summary_dict(result))
    print()
    print("JSON (first 500 chars):", result.json_repr[:500])
    print()

    expected_types = [
        "GLOBAL_CONSTRAINT",   # NO_ROOM_CLASH
        "GLOBAL_CONSTRAINT",   # NO_TEACHER_CLASH
        "TEACHER_UNAVAILABLE",
        "COURSE_ROOM",
        "COURSE_TEACHER",
        "COURSE_DURATION",
        "COURSE_STUDENTS",
        "COURSE_DAYS_PER_WEEK",
        "ROOM_CAPACITY",
        "COURSE_PREFERRED_TIME",
        "COURSE_PREFERRED_DAY",
        "GROUP_NO_CLASH",
    ]

    actual_types = [i.type for i in result.instructions]
    assert actual_types == expected_types, (
        f"\nExpected: {expected_types}\nGot:      {actual_types}"
    )
    print("✓ All instruction types match — smoke-test PASSED.")
    sys.exit(0)
