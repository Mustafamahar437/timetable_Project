"""
compiler/semantic.py
====================
Semantic Analysis Phase — Smart University Timetable Constraint Compiler
========================================================================

Compiler Phase 3: Semantic Analysis
-------------------------------------
After lexing (tokenisation) and parsing (syntax/AST construction), semantic
analysis gives *meaning* to the parse tree.  It answers questions the grammar
cannot:

  • Does teacher "Dr_Ali" actually exist in the university database?
  • Is room "R101" a known room, and is its capacity large enough for the
    course's enrolled students?
  • Are two rules contradicting each other (e.g. the same teacher assigned to
    two courses at the same time slot)?
  • Are numeric values in legal ranges (duration 1-3 hours, etc.)?

The analyser walks the Lark parse tree produced by compiler/parser.py,
extracts each RULE statement, looks up referenced entities in the SQLite
database, and accumulates SemanticError / warning messages.

Public API
----------
    from compiler.semantic import SemanticAnalyzer, SemanticResult, SemanticError

    analyzer = SemanticAnalyzer()
    result   = analyzer.analyze(parse_tree, db_connection)
    if not result.valid:
        for err in result.errors:
            print(err)
"""

from __future__ import annotations

import logging
try:
    import sqlite3
except Exception:
    sqlite3 = None
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Lark import — the parse tree nodes we walk are lark.Tree / lark.Token
# ---------------------------------------------------------------------------
try:
    from lark import Tree, Token
except ImportError:  # pragma: no cover
    raise ImportError(
        "lark-parser is required. Install with: pip install lark"
    )

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain constants — mirror the language specification exactly
# ---------------------------------------------------------------------------

VALID_DAYS: Set[str] = {
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"
}

VALID_TIMES: Set[str] = {
    "8AM", "9AM", "10AM", "11AM", "12PM",
    "1PM", "2PM", "3PM", "4PM", "5PM",
}

# Map time strings to ordinal integers for overlap detection
TIME_ORDER: Dict[str, int] = {t: i for i, t in enumerate(
    ["8AM", "9AM", "10AM", "11AM", "12PM", "1PM", "2PM", "3PM", "4PM", "5PM"]
)}

MIN_DURATION = 1
MAX_DURATION = 3

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SemanticError:
    """
    Represents a single semantic error found during analysis.

    Attributes
    ----------
    message  : Human-readable description of the problem.
    rule_text: The original rule text (or a compact representation) that
               triggered the error.  Useful for IDE highlighting.
    line     : Source line number (1-based) where the offending rule starts.
               May be 0 when the parse tree does not carry line information.
    """
    message: str
    rule_text: str = ""
    line: int = 0

    def __str__(self) -> str:
        location = f" (line {self.line})" if self.line else ""
        rule = f" — rule: `{self.rule_text}`" if self.rule_text else ""
        return f"[SemanticError]{location} {self.message}{rule}"

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable dictionary (useful for Streamlit)."""
        return {
            "message":   self.message,
            "rule_text": self.rule_text,
            "line":      self.line,
        }


@dataclass
class SemanticResult:
    """
    Returned by :meth:`SemanticAnalyzer.analyze`.

    Attributes
    ----------
    valid    : ``True`` iff no *errors* were found (warnings are allowed).
    errors   : List of :class:`SemanticError` objects.
    warnings : List of plain-text warning strings (non-fatal issues).
    """
    valid: bool
    errors: List[SemanticError] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid":    self.valid,
            "errors":   [e.to_dict() for e in self.errors],
            "warnings": self.warnings,
        }

    def summary(self) -> str:
        status = "VALID" if self.valid else "INVALID"
        return (
            f"Semantic analysis: {status} | "
            f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        )


# ---------------------------------------------------------------------------
# Database helper
# ---------------------------------------------------------------------------

class _DBLookup:
    """
    Thin wrapper around a sqlite3 connection providing cached entity lookups.

    The semantic analyser may check the same teacher / course / room many
    times across rules.  We cache results to avoid repeated round-trips.
    """

    def __init__(self, conn: Optional[sqlite3.Connection]) -> None:
        self._conn = conn
        self._teacher_cache: Dict[str, Optional[Dict]] = {}
        self._course_cache:  Dict[str, Optional[Dict]] = {}
        self._room_cache:    Dict[str, Optional[Dict]] = {}

    # ------------------------------------------------------------------
    # Private query helper
    # ------------------------------------------------------------------

    def _query_one(self, sql: str, params: tuple) -> Optional[sqlite3.Row]:
        if self._conn is None:
            return None
        try:
            cur = self._conn.cursor()
            cur.execute(sql, params)
            return cur.fetchone()
        except sqlite3.Error as exc:
            logger.warning("DB query failed (%s): %s", sql, exc)
            return None

    # ------------------------------------------------------------------
    # Public lookup methods  (return dict or None)
    # ------------------------------------------------------------------

    def get_teacher(self, name: str) -> Optional[Dict]:
        """Return teacher row dict or None if not found."""
        if name not in self._teacher_cache:
            row = self._query_one(
                "SELECT * FROM teachers WHERE name = ? COLLATE NOCASE",
                (name,)
            )
            self._teacher_cache[name] = dict(row) if row else None
        return self._teacher_cache[name]

    def get_course(self, course_id: str) -> Optional[Dict]:
        """Return course row dict or None if not found."""
        if course_id not in self._course_cache:
            row = self._query_one(
                "SELECT * FROM courses WHERE course_id = ? COLLATE NOCASE",
                (course_id,)
            )
            self._course_cache[course_id] = dict(row) if row else None
        return self._course_cache[course_id]

    def get_room(self, room_id: str) -> Optional[Dict]:
        """Return room row dict or None if not found."""
        if room_id not in self._room_cache:
            row = self._query_one(
                "SELECT * FROM rooms WHERE room_id = ? COLLATE NOCASE",
                (room_id,)
            )
            self._room_cache[room_id] = dict(row) if row else None
        return self._room_cache[room_id]

    @property
    def connected(self) -> bool:
        return self._conn is not None


# ---------------------------------------------------------------------------
# Symbol / constraint tables used for cross-rule validation
# ---------------------------------------------------------------------------

@dataclass
class _SymbolTable:
    """Tracks all constraints declared so far for contradiction detection."""

    # course_id -> teacher_name
    course_teacher: Dict[str, str] = field(default_factory=dict)
    # course_id -> room_id
    course_room: Dict[str, str] = field(default_factory=dict)
    # course_id -> duration (hours)
    course_duration: Dict[str, int] = field(default_factory=dict)
    # course_id -> student count
    course_students: Dict[str, int] = field(default_factory=dict)
    # course_id -> days_per_week
    course_days_per_week: Dict[str, int] = field(default_factory=dict)
    # room_id -> capacity
    room_capacity: Dict[str, int] = field(default_factory=dict)
    # teacher_name -> set of (day, time) unavailability slots
    teacher_unavailable: Dict[str, Set[Tuple[str, str]]] = field(
        default_factory=dict
    )
    # course_id -> preferred time
    course_preferred_time: Dict[str, str] = field(default_factory=dict)
    # course_id -> preferred day
    course_preferred_day: Dict[str, str] = field(default_factory=dict)
    # group_ids with NO_CLASH
    no_clash_groups: Set[str] = field(default_factory=set)
    # global flags
    no_room_clash: bool = False
    no_teacher_clash: bool = False


# ---------------------------------------------------------------------------
# Main SemanticAnalyzer class
# ---------------------------------------------------------------------------

class SemanticAnalyzer:
    """
    Semantic Analysis Phase of the Timetable Constraint Compiler.

    Usage::

        from compiler.semantic import SemanticAnalyzer
        try:
    import sqlite3
except Exception:
    sqlite3 = None, lark

        conn = sqlite3.connect("university.db")
        # parse_tree is a lark.Tree returned by compiler.parser.Parser.parse()
        analyzer = SemanticAnalyzer()
        result = analyzer.analyze(parse_tree, conn)

    The analyser performs the following checks (in order):

    1. **Entity existence** — teacher / course / room names must be present in
       the database (if a DB connection is provided).
    2. **Domain value checks** — days must be Mon-Fri, times 8AM-5PM.
    3. **Numeric range checks** — duration 1-3 h, positive student counts, etc.
    4. **Capacity consistency** — room capacity ≥ course student count when
       both ROOM and STUDENTS rules exist for the same course.
    5. **Contradiction detection** — same course assigned two different teachers
       or rooms; teacher unavailable at a time they are also needed.
    6. **Duplicate rule warnings** — repeated identical rules are flagged as
       warnings rather than errors.
    """

    def __init__(self) -> None:
        self._errors: List[SemanticError] = []
        self._warnings: List[str] = []
        self._sym: _SymbolTable = _SymbolTable()
        self._db: _DBLookup = _DBLookup(None)

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def analyze(
        self,
        parse_tree: Any,
        db_connection: Optional[sqlite3.Connection] = None,
    ) -> SemanticResult:
        """
        Walk *parse_tree* (a :class:`lark.Tree`) and validate all RULE nodes.

        Parameters
        ----------
        parse_tree   : lark.Tree produced by ``compiler.parser.Parser.parse()``.
                       May also be ``None``; in that case the result is invalid.
        db_connection: An open :class:`sqlite3.Connection` to the university DB.
                       Pass ``None`` to skip DB-backed entity checks (useful
                       for unit-testing rule logic without a live database).

        Returns
        -------
        SemanticResult
        """
        # Reset state so the analyser can be reused
        self._errors = []
        self._warnings = []
        self._sym = _SymbolTable()
        self._db = _DBLookup(db_connection)

        if parse_tree is None:
            self._add_error(
                "Cannot perform semantic analysis: parse tree is None "
                "(check that parsing succeeded).",
                rule_text="<no tree>",
            )
            return self._build_result()

        # Walk every rule statement in the tree
        try:
            self._walk_tree(parse_tree)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Unexpected error during semantic analysis")
            self._add_error(
                f"Internal semantic analyser error: {exc}",
                rule_text="<internal>",
            )

        # Cross-rule consistency checks (run after all rules are collected)
        self._check_capacity_consistency()
        self._check_teacher_schedule_conflicts()

        return self._build_result()

    # ------------------------------------------------------------------
    # Tree walking
    # ------------------------------------------------------------------

    def _walk_tree(self, tree: Any) -> None:
        """
        Recursively walk the Lark parse tree and dispatch each ``rule_stmt``
        node to the appropriate validator.
        """
        if not isinstance(tree, Tree):
            return

        if tree.data in ("rule_stmt", "statement"):
            self._analyse_rule(tree)
        else:
            for child in tree.children:
                if isinstance(child, Tree):
                    self._walk_tree(child)

    def _analyse_rule(self, node: Tree) -> None:
        """
        Dispatch a single rule tree node to the right validator
        based on the rule keyword found in its children.
        """
        # Extract a flat list of token values for easy pattern matching
        tokens = self._extract_tokens(node)
        line = self._get_line(node)
        rule_text = " ".join(str(t) for t in tokens)

        if not tokens:
            self._add_error(
                "Empty rule statement encountered.",
                rule_text="<empty>",
                line=line,
            )
            return

        # Strip leading RULE keyword if present
        if tokens and tokens[0].upper() == "RULE":
            tokens = tokens[1:]

        if not tokens:
            return

        # Dispatch on rule keyword
        kw = tokens[0].upper() if tokens else ""

        # --- Global constraints ---
        if kw == "NO_ROOM_CLASH":
            self._check_global_no_room_clash(tokens, line, rule_text)
        elif kw == "NO_TEACHER_CLASH":
            self._check_global_no_teacher_clash(tokens, line, rule_text)
        # --- Teacher NOT_AVAILABLE ---
        elif len(tokens) >= 4 and tokens[1].upper() == "NOT_AVAILABLE":
            self._check_teacher_not_available(tokens, line, rule_text)
        # --- ROOM constraint ---
        elif len(tokens) >= 3 and tokens[1].upper() == "ROOM":
            self._check_course_room(tokens, line, rule_text)
        # --- TEACHER constraint ---
        elif len(tokens) >= 3 and tokens[1].upper() == "TEACHER":
            self._check_course_teacher(tokens, line, rule_text)
        # --- DURATION constraint ---
        elif len(tokens) >= 3 and tokens[1].upper() == "DURATION":
            self._check_course_duration(tokens, line, rule_text)
        # --- STUDENTS constraint ---
        elif len(tokens) >= 3 and tokens[1].upper() == "STUDENTS":
            self._check_course_students(tokens, line, rule_text)
        # --- DAYS_PER_WEEK constraint ---
        elif len(tokens) >= 3 and tokens[1].upper() == "DAYS_PER_WEEK":
            self._check_course_days_per_week(tokens, line, rule_text)
        # --- CAPACITY constraint ---
        elif len(tokens) >= 3 and tokens[1].upper() == "CAPACITY":
            self._check_room_capacity(tokens, line, rule_text)
        # --- PREFERRED_TIME ---
        elif len(tokens) >= 3 and tokens[1].upper() == "PREFERRED_TIME":
            self._check_preferred_time(tokens, line, rule_text)
        # --- PREFERRED_DAY ---
        elif len(tokens) >= 3 and tokens[1].upper() == "PREFERRED_DAY":
            self._check_preferred_day(tokens, line, rule_text)
        # --- NO_CLASH (group) ---
        elif len(tokens) >= 2 and tokens[1].upper() == "NO_CLASH":
            self._check_group_no_clash(tokens, line, rule_text)
        else:
            self._add_error(
                f"Unrecognised or malformed rule pattern: '{rule_text}'.",
                rule_text=rule_text,
                line=line,
            )

    # ------------------------------------------------------------------
    # Individual rule validators
    # ------------------------------------------------------------------

    def _check_global_no_room_clash(
        self, tokens: List[str], line: int, rule_text: str
    ) -> None:
        """RULE NO_ROOM_CLASH;"""
        if self._sym.no_room_clash:
            self._add_warning(
                f"Line {line}: Duplicate global rule 'NO_ROOM_CLASH' "
                "(previous declaration is sufficient).",
                rule_text=rule_text,
            )
        self._sym.no_room_clash = True

    def _check_global_no_teacher_clash(
        self, tokens: List[str], line: int, rule_text: str
    ) -> None:
        """RULE NO_TEACHER_CLASH;"""
        if self._sym.no_teacher_clash:
            self._add_warning(
                f"Line {line}: Duplicate global rule 'NO_TEACHER_CLASH'.",
                rule_text=rule_text,
            )
        self._sym.no_teacher_clash = True

    def _check_teacher_not_available(
        self, tokens: List[str], line: int, rule_text: str
    ) -> None:
        """RULE <teacher_name> NOT_AVAILABLE <day> <time>;"""
        if len(tokens) < 4:
            self._add_error(
                "NOT_AVAILABLE rule requires: <teacher> NOT_AVAILABLE <day> <time>.",
                rule_text=rule_text, line=line,
            )
            return

        teacher, _kw, day, time_slot = (
            tokens[0], tokens[1], tokens[2], tokens[3]
        )

        # Teacher existence
        self._require_teacher(teacher, line, rule_text)

        # Day validity
        self._require_valid_day(day, line, rule_text)

        # Time validity
        self._require_valid_time(time_slot, line, rule_text)

        # Register unavailability slot
        slots = self._sym.teacher_unavailable.setdefault(teacher, set())
        slot = (day, time_slot)
        if slot in slots:
            self._add_warning(
                f"Line {line}: Duplicate NOT_AVAILABLE entry for teacher "
                f"'{teacher}' on {day} at {time_slot}.",
                rule_text=rule_text,
            )
        slots.add(slot)

    def _check_course_room(
        self, tokens: List[str], line: int, rule_text: str
    ) -> None:
        """RULE <course_id> ROOM <room_id>;"""
        if len(tokens) < 3:
            self._add_error(
                "ROOM rule requires: <course_id> ROOM <room_id>.",
                rule_text=rule_text, line=line,
            )
            return

        course_id, _kw, room_id = tokens[0], tokens[1], tokens[2]

        self._require_course(course_id, line, rule_text)
        self._require_room(room_id, line, rule_text)

        # Contradiction: same course assigned two different rooms
        if course_id in self._sym.course_room:
            prev_room = self._sym.course_room[course_id]
            if prev_room != room_id:
                self._add_error(
                    f"Contradictory ROOM rules for course '{course_id}': "
                    f"previously assigned to '{prev_room}', now '{room_id}'.",
                    rule_text=rule_text, line=line,
                )
            else:
                self._add_warning(
                    f"Line {line}: Duplicate ROOM rule for course '{course_id}'.",
                    rule_text=rule_text,
                )
        else:
            self._sym.course_room[course_id] = room_id

    def _check_course_teacher(
        self, tokens: List[str], line: int, rule_text: str
    ) -> None:
        """RULE <course_id> TEACHER <teacher_name>;"""
        if len(tokens) < 3:
            self._add_error(
                "TEACHER rule requires: <course_id> TEACHER <teacher_name>.",
                rule_text=rule_text, line=line,
            )
            return

        course_id, _kw, teacher = tokens[0], tokens[1], tokens[2]

        self._require_course(course_id, line, rule_text)
        self._require_teacher(teacher, line, rule_text)

        # Contradiction: same course assigned two different teachers
        if course_id in self._sym.course_teacher:
            prev_teacher = self._sym.course_teacher[course_id]
            if prev_teacher != teacher:
                self._add_error(
                    f"Contradictory TEACHER rules for course '{course_id}': "
                    f"previously assigned to '{prev_teacher}', now '{teacher}'.",
                    rule_text=rule_text, line=line,
                )
            else:
                self._add_warning(
                    f"Line {line}: Duplicate TEACHER rule for course '{course_id}'.",
                    rule_text=rule_text,
                )
        else:
            self._sym.course_teacher[course_id] = teacher

    def _check_course_duration(
        self, tokens: List[str], line: int, rule_text: str
    ) -> None:
        """RULE <course_id> DURATION <n>HOUR;"""
        if len(tokens) < 3:
            self._add_error(
                "DURATION rule requires: <course_id> DURATION <n>HOUR.",
                rule_text=rule_text, line=line,
            )
            return

        course_id = tokens[0]
        # The duration value may be tokens[2] like "2HOUR" or separate "2" "HOUR"
        raw = tokens[2] if len(tokens) > 2 else ""
        hours = self._parse_hour_value(raw, tokens, line, rule_text)
        if hours is None:
            return

        self._require_course(course_id, line, rule_text)

        if not (MIN_DURATION <= hours <= MAX_DURATION):
            self._add_error(
                f"Duration for course '{course_id}' is {hours} hour(s), "
                f"but must be between {MIN_DURATION} and {MAX_DURATION}.",
                rule_text=rule_text, line=line,
            )
            return

        if course_id in self._sym.course_duration:
            prev = self._sym.course_duration[course_id]
            if prev != hours:
                self._add_error(
                    f"Contradictory DURATION rules for course '{course_id}': "
                    f"previously {prev}h, now {hours}h.",
                    rule_text=rule_text, line=line,
                )
            else:
                self._add_warning(
                    f"Line {line}: Duplicate DURATION rule for course '{course_id}'.",
                    rule_text=rule_text,
                )
        else:
            self._sym.course_duration[course_id] = hours

    def _check_course_students(
        self, tokens: List[str], line: int, rule_text: str
    ) -> None:
        """RULE <course_id> STUDENTS <n>;"""
        if len(tokens) < 3:
            self._add_error(
                "STUDENTS rule requires: <course_id> STUDENTS <n>.",
                rule_text=rule_text, line=line,
            )
            return

        course_id, _kw, raw_n = tokens[0], tokens[1], tokens[2]

        self._require_course(course_id, line, rule_text)

        count = self._parse_positive_int(raw_n, "student count", line, rule_text)
        if count is None:
            return

        if course_id in self._sym.course_students:
            prev = self._sym.course_students[course_id]
            if prev != count:
                self._add_error(
                    f"Contradictory STUDENTS rules for course '{course_id}': "
                    f"previously {prev}, now {count}.",
                    rule_text=rule_text, line=line,
                )
            else:
                self._add_warning(
                    f"Line {line}: Duplicate STUDENTS rule for course '{course_id}'.",
                    rule_text=rule_text,
                )
        else:
            self._sym.course_students[course_id] = count

    def _check_course_days_per_week(
        self, tokens: List[str], line: int, rule_text: str
    ) -> None:
        """RULE <course_id> DAYS_PER_WEEK <n>;"""
        if len(tokens) < 3:
            self._add_error(
                "DAYS_PER_WEEK rule requires: <course_id> DAYS_PER_WEEK <n>.",
                rule_text=rule_text, line=line,
            )
            return

        course_id, _kw, raw_n = tokens[0], tokens[1], tokens[2]

        self._require_course(course_id, line, rule_text)

        count = self._parse_positive_int(raw_n, "days per week", line, rule_text)
        if count is None:
            return

        if count > 5:
            self._add_error(
                f"DAYS_PER_WEEK for course '{course_id}' is {count}, "
                "but the working week only has 5 days (Monday–Friday).",
                rule_text=rule_text, line=line,
            )
            return

        if course_id in self._sym.course_days_per_week:
            prev = self._sym.course_days_per_week[course_id]
            if prev != count:
                self._add_error(
                    f"Contradictory DAYS_PER_WEEK rules for course '{course_id}': "
                    f"previously {prev}, now {count}.",
                    rule_text=rule_text, line=line,
                )
            else:
                self._add_warning(
                    f"Line {line}: Duplicate DAYS_PER_WEEK rule for "
                    f"course '{course_id}'.",
                    rule_text=rule_text,
                )
        else:
            self._sym.course_days_per_week[course_id] = count

    def _check_room_capacity(
        self, tokens: List[str], line: int, rule_text: str
    ) -> None:
        """RULE <room_id> CAPACITY <n>;"""
        if len(tokens) < 3:
            self._add_error(
                "CAPACITY rule requires: <room_id> CAPACITY <n>.",
                rule_text=rule_text, line=line,
            )
            return

        room_id, _kw, raw_n = tokens[0], tokens[1], tokens[2]

        self._require_room(room_id, line, rule_text)

        cap = self._parse_positive_int(raw_n, "room capacity", line, rule_text)
        if cap is None:
            return

        if room_id in self._sym.room_capacity:
            prev = self._sym.room_capacity[room_id]
            if prev != cap:
                self._add_error(
                    f"Contradictory CAPACITY rules for room '{room_id}': "
                    f"previously {prev}, now {cap}.",
                    rule_text=rule_text, line=line,
                )
            else:
                self._add_warning(
                    f"Line {line}: Duplicate CAPACITY rule for room '{room_id}'.",
                    rule_text=rule_text,
                )
        else:
            self._sym.room_capacity[room_id] = cap

        # Also check DB-stored capacity consistency
        if self._db.connected:
            room_row = self._db.get_room(room_id)
            if room_row and "capacity" in room_row:
                db_cap = int(room_row["capacity"])
                if db_cap != cap:
                    self._add_warning(
                        f"Line {line}: CAPACITY rule declares {cap} seats "
                        f"for room '{room_id}', but the database records "
                        f"{db_cap} seats. The rule value will override.",
                        rule_text=rule_text,
                    )

    def _check_preferred_time(
        self, tokens: List[str], line: int, rule_text: str
    ) -> None:
        """RULE <course_id> PREFERRED_TIME <time>;"""
        if len(tokens) < 3:
            self._add_error(
                "PREFERRED_TIME rule requires: <course_id> PREFERRED_TIME <time>.",
                rule_text=rule_text, line=line,
            )
            return

        course_id, _kw, time_slot = tokens[0], tokens[1], tokens[2]

        self._require_course(course_id, line, rule_text)
        self._require_valid_time(time_slot, line, rule_text)

        if course_id in self._sym.course_preferred_time:
            prev = self._sym.course_preferred_time[course_id]
            if prev != time_slot:
                self._add_warning(
                    f"Line {line}: Course '{course_id}' has multiple "
                    f"PREFERRED_TIME rules ({prev} and {time_slot}). "
                    "Only the first will be used by the solver.",
                    rule_text=rule_text,
                )
            else:
                self._add_warning(
                    f"Line {line}: Duplicate PREFERRED_TIME rule for "
                    f"course '{course_id}'.",
                    rule_text=rule_text,
                )
        else:
            self._sym.course_preferred_time[course_id] = time_slot

    def _check_preferred_day(
        self, tokens: List[str], line: int, rule_text: str
    ) -> None:
        """RULE <course_id> PREFERRED_DAY <day>;"""
        if len(tokens) < 3:
            self._add_error(
                "PREFERRED_DAY rule requires: <course_id> PREFERRED_DAY <day>.",
                rule_text=rule_text, line=line,
            )
            return

        course_id, _kw, day = tokens[0], tokens[1], tokens[2]

        self._require_course(course_id, line, rule_text)
        self._require_valid_day(day, line, rule_text)

        if course_id in self._sym.course_preferred_day:
            prev = self._sym.course_preferred_day[course_id]
            if prev != day:
                self._add_warning(
                    f"Line {line}: Course '{course_id}' has multiple "
                    f"PREFERRED_DAY rules ({prev} and {day}). "
                    "Only the first will be used by the solver.",
                    rule_text=rule_text,
                )
        else:
            self._sym.course_preferred_day[course_id] = day

    def _check_group_no_clash(
        self, tokens: List[str], line: int, rule_text: str
    ) -> None:
        """RULE <group_id> NO_CLASH;"""
        if len(tokens) < 2:
            self._add_error(
                "NO_CLASH rule requires: <group_id> NO_CLASH.",
                rule_text=rule_text, line=line,
            )
            return

        group_id = tokens[0]

        if group_id in self._sym.no_clash_groups:
            self._add_warning(
                f"Line {line}: Duplicate NO_CLASH rule for group '{group_id}'.",
                rule_text=rule_text,
            )
        else:
            self._sym.no_clash_groups.add(group_id)

    # ------------------------------------------------------------------
    # Cross-rule consistency checks
    # ------------------------------------------------------------------

    def _check_capacity_consistency(self) -> None:
        """
        For every course that has both a ROOM and a STUDENTS rule, verify
        that the room (from either the DSL CAPACITY rule or the DB) can hold
        the students.
        """
        for course_id, room_id in self._sym.course_room.items():
            students = self._sym.course_students.get(course_id)
            if students is None:
                continue  # No student count declared — skip

            # Prefer the DSL-declared capacity, fall back to DB
            cap = self._sym.room_capacity.get(room_id)
            if cap is None and self._db.connected:
                room_row = self._db.get_room(room_id)
                if room_row and "capacity" in room_row:
                    cap = int(room_row["capacity"])

            if cap is not None and cap < students:
                self._add_error(
                    f"Room '{room_id}' has capacity {cap} but course "
                    f"'{course_id}' has {students} students — the room is "
                    "too small.",
                    rule_text=(
                        f"{course_id} ROOM {room_id} | "
                        f"{course_id} STUDENTS {students}"
                    ),
                )
            elif cap is None:
                self._add_warning(
                    f"Could not verify capacity for room '{room_id}' "
                    f"(assigned to course '{course_id}', {students} students) "
                    "— no CAPACITY rule and room not found in DB.",
                    rule_text=f"{course_id} ROOM {room_id}",
                )

    def _check_teacher_schedule_conflicts(self) -> None:
        """
        Detect potential scheduling conflicts:

        * If two courses share the same teacher and each has DAYS_PER_WEEK ≥ 1
          and DURATION ≥ 1 declared, check whether the total weekly slot usage
          exceeds the available slots, raising an error when physically
          impossible.

        * If a teacher is flagged NOT_AVAILABLE on a day but is the sole
          teacher assigned to a course with DAYS_PER_WEEK = 5, warn that
          scheduling may be infeasible.
        """
        # Build a map: teacher -> list of course_ids
        teacher_courses: Dict[str, List[str]] = {}
        for course_id, teacher in self._sym.course_teacher.items():
            teacher_courses.setdefault(teacher, []).append(course_id)

        total_weekly_slots = len(VALID_DAYS) * len(VALID_TIMES)  # 5 * 10 = 50

        for teacher, courses in teacher_courses.items():
            # Sum up required slots across all courses this teacher teaches
            total_required = 0
            for c in courses:
                dpw = self._sym.course_days_per_week.get(c, 1)
                dur = self._sym.course_duration.get(c, 1)
                total_required += dpw * dur

            unavail_count = len(
                self._sym.teacher_unavailable.get(teacher, set())
            )
            available_slots = total_weekly_slots - unavail_count

            if total_required > available_slots:
                self._add_error(
                    f"Teacher '{teacher}' is assigned {len(courses)} course(s) "
                    f"requiring {total_required} slot(s) per week, but only "
                    f"{available_slots} slot(s) are available after "
                    f"{unavail_count} unavailability declaration(s).",
                    rule_text=f"Teacher '{teacher}' schedule",
                )

        # Check teacher unavailability vs days_per_week = 5
        for course_id, teacher in self._sym.course_teacher.items():
            dpw = self._sym.course_days_per_week.get(course_id, 0)
            if dpw == 5:
                unavail_days = {
                    day for day, _t
                    in self._sym.teacher_unavailable.get(teacher, set())
                }
                if unavail_days:
                    self._add_warning(
                        f"Course '{course_id}' requires 5 days/week but "
                        f"teacher '{teacher}' is marked NOT_AVAILABLE on "
                        f"{', '.join(sorted(unavail_days))}. Scheduling may "
                        "be infeasible.",
                        rule_text=f"{course_id} DAYS_PER_WEEK 5",
                    )

    # ------------------------------------------------------------------
    # DB entity requirement helpers
    # ------------------------------------------------------------------

    def _require_teacher(
        self, name: str, line: int, rule_text: str
    ) -> bool:
        """Return True if teacher exists in DB (or DB not connected)."""
        if not self._db.connected:
            return True  # Cannot verify — optimistically allow
        row = self._db.get_teacher(name)
        if row is None:
            self._add_error(
                f"Teacher '{name}' does not exist in the database.",
                rule_text=rule_text, line=line,
            )
            return False
        return True

    def _require_course(
        self, course_id: str, line: int, rule_text: str
    ) -> bool:
        """Return True if course exists in DB (or DB not connected)."""
        if not self._db.connected:
            return True
        row = self._db.get_course(course_id)
        if row is None:
            self._add_error(
                f"Course '{course_id}' does not exist in the database.",
                rule_text=rule_text, line=line,
            )
            return False
        return True

    def _require_room(
        self, room_id: str, line: int, rule_text: str
    ) -> bool:
        """Return True if room exists in DB (or DB not connected)."""
        if not self._db.connected:
            return True
        row = self._db.get_room(room_id)
        if row is None:
            self._add_error(
                f"Room '{room_id}' does not exist in the database.",
                rule_text=rule_text, line=line,
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Domain value validators
    # ------------------------------------------------------------------

    def _require_valid_day(
        self, day: str, line: int, rule_text: str
    ) -> bool:
        if day not in VALID_DAYS:
            self._add_error(
                f"'{day}' is not a valid day. "
                f"Must be one of: {', '.join(sorted(VALID_DAYS))}.",
                rule_text=rule_text, line=line,
            )
            return False
        return True

    def _require_valid_time(
        self, time_slot: str, line: int, rule_text: str
    ) -> bool:
        if time_slot not in VALID_TIMES:
            self._add_error(
                f"'{time_slot}' is not a valid time slot. "
                f"Must be one of: {', '.join(sorted(TIME_ORDER, key=lambda t: TIME_ORDER[t]))}.",
                rule_text=rule_text, line=line,
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Numeric parsing helpers
    # ------------------------------------------------------------------

    def _parse_positive_int(
        self,
        raw: str,
        field_name: str,
        line: int,
        rule_text: str,
    ) -> Optional[int]:
        """Parse a string token as a positive integer, adding an error if invalid."""
        try:
            value = int(raw)
        except (ValueError, TypeError):
            self._add_error(
                f"Expected a positive integer for {field_name}, "
                f"but got '{raw}'.",
                rule_text=rule_text, line=line,
            )
            return None

        if value <= 0:
            self._add_error(
                f"The {field_name} must be a positive integer (> 0), "
                f"but got {value}.",
                rule_text=rule_text, line=line,
            )
            return None

        return value

    def _parse_hour_value(
        self,
        raw: str,
        tokens: List[str],
        line: int,
        rule_text: str,
    ) -> Optional[int]:
        """
        Parse the DURATION value which the lexer may deliver as:
          - a combined token like "2HOUR" or "2HOURS"
          - separate tokens: ["2", "HOUR"] (tokens[2] and tokens[3])
        """
        # Try combined form first (e.g. "2HOUR")
        combined = raw.upper().replace("HOURS", "").replace("HOUR", "").strip()
        if combined.isdigit():
            return int(combined)

        # Maybe the number is tokens[2] and "HOUR" is tokens[3]
        if raw.isdigit():
            return int(raw)

        # Fallback: try to extract leading digits
        import re
        m = re.match(r"^(\d+)", raw)
        if m:
            return int(m.group(1))

        self._add_error(
            f"Cannot parse DURATION value '{raw}'. "
            "Expected format: <n>HOUR (e.g., 2HOUR).",
            rule_text=rule_text, line=line,
        )
        return None

    # ------------------------------------------------------------------
    # Token extraction helpers
    # ------------------------------------------------------------------

    def _extract_tokens(self, node: Tree) -> List[str]:
        """
        Flatten all terminal Token values from a rule_stmt subtree into a
        list of strings, skipping punctuation (SEMICOLON, NEWLINE).
        """
        result: List[str] = []
        self._collect_terminals(node, result)
        return result

    def _collect_terminals(self, node: Any, out: List[str]) -> None:
        """Recursively collect leaf Token string values."""
        if isinstance(node, Token):
            # Skip punctuation tokens
            token_type = str(node.type).upper()
            if token_type not in {"SEMICOLON", "NEWLINE", "WS", "__ANON_0"}:
                out.append(str(node))
        elif isinstance(node, Tree):
            for child in node.children:
                self._collect_terminals(child, out)

    @staticmethod
    def _get_line(node: Tree) -> int:
        """
        Return the source line of the first terminal token in *node*.
        Returns 0 if no line info is available.
        """
        for child in node.scan_values(lambda v: True):
            if hasattr(child, "line") and child.line is not None:
                return child.line
        return 0

    # ------------------------------------------------------------------
    # Error / warning accumulators
    # ------------------------------------------------------------------

    def _add_error(
        self,
        message: str,
        rule_text: str = "",
        line: int = 0,
    ) -> None:
        err = SemanticError(message=message, rule_text=rule_text, line=line)
        self._errors.append(err)
        logger.debug("Semantic error: %s", err)

    def _add_warning(
        self,
        message: str,
        rule_text: str = "",
    ) -> None:
        self._warnings.append(message)
        logger.debug("Semantic warning: %s", message)

    def _build_result(self) -> SemanticResult:
        return SemanticResult(
            valid=len(self._errors) == 0,
            errors=list(self._errors),
            warnings=list(self._warnings),
        )

    # ------------------------------------------------------------------
    # Public utility: analyse a plain-text rule list (without parse tree)
    # ------------------------------------------------------------------

    def analyze_rule_dicts(
        self,
        rules: List[Dict[str, Any]],
        db_connection: Optional[sqlite3.Connection] = None,
    ) -> SemanticResult:
        """
        Analyse a list of rule dictionaries directly — useful when the IR
        generator or other modules have already decomposed the parse tree.

        Each dict must have at least::

            {
                "type": "TEACHER_UNAVAILABLE",   # IR instruction type
                "teacher": "Dr_Ali",
                "day": "Monday",
                "time": "9AM",
                "line": 5,                        # optional
            }

        This method is a convenience wrapper; it reconstructs synthetic
        ``SemanticError`` / warning objects using the same validation logic.
        """
        self._errors = []
        self._warnings = []
        self._sym = _SymbolTable()
        self._db = _DBLookup(db_connection)

        dispatch = {
            "GLOBAL_CONSTRAINT":      self._analyse_dict_global,
            "TEACHER_UNAVAILABLE":    self._analyse_dict_unavailable,
            "COURSE_ROOM":            self._analyse_dict_course_room,
            "COURSE_TEACHER":         self._analyse_dict_course_teacher,
            "COURSE_DURATION":        self._analyse_dict_course_duration,
            "COURSE_STUDENTS":        self._analyse_dict_course_students,
            "COURSE_DAYS_PER_WEEK":   self._analyse_dict_days_per_week,
            "ROOM_CAPACITY":          self._analyse_dict_room_capacity,
            "COURSE_PREFERRED_TIME":  self._analyse_dict_preferred_time,
            "COURSE_PREFERRED_DAY":   self._analyse_dict_preferred_day,
            "GROUP_NO_CLASH":         self._analyse_dict_group_no_clash,
        }

        for rule in rules:
            rtype = rule.get("type", "").upper()
            handler = dispatch.get(rtype)
            if handler is None:
                self._add_error(
                    f"Unknown IR instruction type '{rtype}' in rule dict.",
                    rule_text=str(rule),
                )
            else:
                try:
                    handler(rule)
                except Exception as exc:  # pylint: disable=broad-except
                    self._add_error(
                        f"Error processing rule dict: {exc}",
                        rule_text=str(rule),
                    )

        self._check_capacity_consistency()
        self._check_teacher_schedule_conflicts()
        return self._build_result()

    # ------------------------------------------------------------------
    # Dict-based analysis helpers (used by analyze_rule_dicts)
    # ------------------------------------------------------------------

    def _analyse_dict_global(self, r: Dict) -> None:
        name = r.get("constraint_name", "").upper()
        line = r.get("line", 0)
        if name == "NO_ROOM_CLASH":
            self._check_global_no_room_clash(
                ["NO_ROOM_CLASH"], line, "NO_ROOM_CLASH"
            )
        elif name == "NO_TEACHER_CLASH":
            self._check_global_no_teacher_clash(
                ["NO_TEACHER_CLASH"], line, "NO_TEACHER_CLASH"
            )

    def _analyse_dict_unavailable(self, r: Dict) -> None:
        teacher   = r.get("teacher", "")
        day       = r.get("day", "")
        time_slot = r.get("time", "")
        line      = r.get("line", 0)
        rule_text = f"{teacher} NOT_AVAILABLE {day} {time_slot}"
        tokens    = [teacher, "NOT_AVAILABLE", day, time_slot]
        self._check_teacher_not_available(tokens, line, rule_text)

    def _analyse_dict_course_room(self, r: Dict) -> None:
        course_id = r.get("course", "")
        room_id   = r.get("room", "")
        line      = r.get("line", 0)
        rule_text = f"{course_id} ROOM {room_id}"
        self._check_course_room(
            [course_id, "ROOM", room_id], line, rule_text
        )

    def _analyse_dict_course_teacher(self, r: Dict) -> None:
        course_id = r.get("course", "")
        teacher   = r.get("teacher", "")
        line      = r.get("line", 0)
        rule_text = f"{course_id} TEACHER {teacher}"
        self._check_course_teacher(
            [course_id, "TEACHER", teacher], line, rule_text
        )

    def _analyse_dict_course_duration(self, r: Dict) -> None:
        course_id = r.get("course", "")
        hours     = r.get("hours", 1)
        line      = r.get("line", 0)
        rule_text = f"{course_id} DURATION {hours}HOUR"
        self._require_course(course_id, line, rule_text)
        try:
            h = int(hours)
        except (ValueError, TypeError):
            self._add_error(
                f"Invalid duration value '{hours}' for course '{course_id}'.",
                rule_text=rule_text, line=line,
            )
            return
        if not (MIN_DURATION <= h <= MAX_DURATION):
            self._add_error(
                f"Duration {h}h for course '{course_id}' is outside the "
                f"allowed range [{MIN_DURATION}–{MAX_DURATION}].",
                rule_text=rule_text, line=line,
            )
        else:
            if course_id in self._sym.course_duration:
                prev = self._sym.course_duration[course_id]
                if prev != h:
                    self._add_error(
                        f"Contradictory DURATION for '{course_id}': "
                        f"{prev}h vs {h}h.",
                        rule_text=rule_text, line=line,
                    )
            else:
                self._sym.course_duration[course_id] = h

    def _analyse_dict_course_students(self, r: Dict) -> None:
        course_id = r.get("course", "")
        count     = r.get("count", 0)
        line      = r.get("line", 0)
        rule_text = f"{course_id} STUDENTS {count}"
        self._require_course(course_id, line, rule_text)
        try:
            n = int(count)
        except (ValueError, TypeError):
            self._add_error(
                f"Invalid student count '{count}' for course '{course_id}'.",
                rule_text=rule_text, line=line,
            )
            return
        if n <= 0:
            self._add_error(
                f"Student count for course '{course_id}' must be > 0, got {n}.",
                rule_text=rule_text, line=line,
            )
            return
        if course_id in self._sym.course_students:
            prev = self._sym.course_students[course_id]
            if prev != n:
                self._add_error(
                    f"Contradictory STUDENTS for '{course_id}': {prev} vs {n}.",
                    rule_text=rule_text, line=line,
                )
        else:
            self._sym.course_students[course_id] = n

    def _analyse_dict_days_per_week(self, r: Dict) -> None:
        course_id = r.get("course", "")
        days      = r.get("days", 1)
        line      = r.get("line", 0)
        rule_text = f"{course_id} DAYS_PER_WEEK {days}"
        self._check_course_days_per_week(
            [course_id, "DAYS_PER_WEEK", str(days)], line, rule_text
        )

    def _analyse_dict_room_capacity(self, r: Dict) -> None:
        room_id  = r.get("room", "")
        capacity = r.get("capacity", 0)
        line     = r.get("line", 0)
        rule_text = f"{room_id} CAPACITY {capacity}"
        self._check_room_capacity(
            [room_id, "CAPACITY", str(capacity)], line, rule_text
        )

    def _analyse_dict_preferred_time(self, r: Dict) -> None:
        course_id = r.get("course", "")
        time_slot = r.get("time", "")
        line      = r.get("line", 0)
        rule_text = f"{course_id} PREFERRED_TIME {time_slot}"
        self._check_preferred_time(
            [course_id, "PREFERRED_TIME", time_slot], line, rule_text
        )

    def _analyse_dict_preferred_day(self, r: Dict) -> None:
        course_id = r.get("course", "")
        day       = r.get("day", "")
        line      = r.get("line", 0)
        rule_text = f"{course_id} PREFERRED_DAY {day}"
        self._check_preferred_day(
            [course_id, "PREFERRED_DAY", day], line, rule_text
        )

    def _analyse_dict_group_no_clash(self, r: Dict) -> None:
        group_id  = r.get("group", "")
        line      = r.get("line", 0)
        rule_text = f"{group_id} NO_CLASH"
        self._check_group_no_clash(
            [group_id, "NO_CLASH"], line, rule_text
        )

    # ------------------------------------------------------------------
    # Symbol table introspection (useful for the Streamlit UI)
    # ------------------------------------------------------------------

    def get_symbol_table(self) -> Dict[str, Any]:
        """
        Return a JSON-serialisable snapshot of the symbol table collected
        during the last :meth:`analyze` or :meth:`analyze_rule_dicts` call.
        """
        sym = self._sym
        return {
            "course_teacher":       dict(sym.course_teacher),
            "course_room":          dict(sym.course_room),
            "course_duration":      dict(sym.course_duration),
            "course_students":      dict(sym.course_students),
            "course_days_per_week": dict(sym.course_days_per_week),
            "room_capacity":        dict(sym.room_capacity),
            "teacher_unavailable":  {
                t: [list(s) for s in slots]
                for t, slots in sym.teacher_unavailable.items()
            },
            "course_preferred_time": dict(sym.course_preferred_time),
            "course_preferred_day":  dict(sym.course_preferred_day),
            "no_clash_groups":       list(sym.no_clash_groups),
            "no_room_clash":         sym.no_room_clash,
            "no_teacher_clash":      sym.no_teacher_clash,
        }
