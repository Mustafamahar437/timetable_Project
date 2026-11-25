"""
code_generator.py — Code Generation Phase of the Timetable Constraint Compiler
===============================================================================

Compiler Phase: IR → OR-Tools-ready Constraint Specification
--------------------------------------------------------------
This module is the **code generation** stage of the compiler pipeline. In a
traditional compiler, this phase translates an Intermediate Representation (IR)
into the target language (e.g., machine code or bytecode). Here the "target
language" is a structured constraint specification understood by the OR-Tools
CP-SAT solver (see solver.py).

Pipeline position:
  Source (.tcs)
    → Lexer (tokens)
    → Parser (parse tree)
    → Semantic Analyzer (validated tree)
    → IR Generator (IRInstruction list)
    → **Code Generator**  ← YOU ARE HERE
    → Solver (timetable)

The CodeGenerator translates each IRInstruction into a concrete constraint dict
that the solver can directly consume. It also:
  - Fetches live data from the database (courses, teachers, rooms, time slots)
    to build the full decision-variable domain.
  - Separates hard constraints (must hold) from soft constraints (penalised
    when violated, with a configurable cost).
  - Emits a solver_config dict that parameterises the CP-SAT search (time
    limits, optimisation objective weights, etc.).

Design note on constraint representation
-----------------------------------------
Every constraint is a plain Python dict so it is JSON-serialisable and easy to
inspect in the Streamlit UI.  The solver reads these dicts generically; the
``constraint_type`` key is the discriminant.

Constraint taxonomy
-------------------
Hard constraints (feasibility):
  ROOM_CLASH_FREE        – each room used ≤ 1 time per slot
  TEACHER_CLASH_FREE     – each teacher used ≤ 1 time per slot
  TEACHER_UNAVAILABLE    – specific (teacher, day, slot) must be blocked
  COURSE_ROOM_ASSIGNMENT – course must be in a specific room
  COURSE_TEACHER_ASSIGN  – course must be taught by a specific teacher
  COURSE_DAYS_PER_WEEK   – course must be scheduled exactly N sessions/week
  COURSE_DURATION        – each session of a course lasts exactly N slots
  ROOM_CAPACITY          – room capacity must ≥ enrolled students
  GROUP_NO_CLASH         – all courses in a group must not overlap in time

Soft constraints (objective / penalty):
  PREFERRED_TIME         – prefer a specific start time for a course
  PREFERRED_DAY          – prefer a specific day for a course
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants shared across the compiler
# ---------------------------------------------------------------------------

VALID_DAYS: List[str] = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"
]

VALID_TIMES: List[str] = [
    "8AM", "9AM", "10AM", "11AM", "12PM",
    "1PM", "2PM", "3PM", "4PM", "5PM"
]

# Map time-string → integer index (used by the solver as slot numbers)
TIME_TO_SLOT: Dict[str, int] = {t: i for i, t in enumerate(VALID_TIMES)}
DAY_TO_INDEX: Dict[str, int] = {d: i for i, d in enumerate(VALID_DAYS)}

# Default penalty costs for soft constraints (solver minimises total penalty)
DEFAULT_PREFERRED_TIME_PENALTY: int = 10
DEFAULT_PREFERRED_DAY_PENALTY: int = 5


# ---------------------------------------------------------------------------
# IRInstruction — mirrors the shape produced by ir_generator.py
# ---------------------------------------------------------------------------

@dataclass
class IRInstruction:
    """
    A single instruction in the Intermediate Representation.

    The IR generator emits one IRInstruction per DSL rule.  Each instruction
    carries a ``type`` discriminant and arbitrary keyword data as ``params``.

    Attributes
    ----------
    type : str
        One of the IR instruction type constants defined in ir_generator.py.
        Examples: ``GLOBAL_CONSTRAINT``, ``TEACHER_UNAVAILABLE``,
        ``COURSE_ROOM``, …
    params : dict
        Payload whose keys depend on the instruction type.
    """
    type: str
    params: Dict[str, Any] = field(default_factory=dict)

    # Allow attribute-style access on params for ergonomic reading
    def __getattr__(self, name: str) -> Any:
        try:
            return self.params[name]
        except KeyError:
            raise AttributeError(
                f"IRInstruction of type '{self.type}' has no param '{name}'"
            ) from None

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {"type": self.type, **self.params}


# ---------------------------------------------------------------------------
# ConstraintSet — the output of CodeGenerator
# ---------------------------------------------------------------------------

@dataclass
class ConstraintSet:
    """
    The compiled set of constraints ready for the OR-Tools CP-SAT solver.

    Attributes
    ----------
    hard_constraints : List[dict]
        Constraints that must hold in every feasible solution.
    soft_constraints : List[dict]
        Constraints with associated penalty costs; violations are penalised in
        the objective function rather than making the problem infeasible.
    solver_config : dict
        Meta-configuration for the solver: time limits, objective weights,
        variable domain information, etc.
    generation_errors : List[str]
        Non-fatal issues encountered during code generation (e.g., a course
        referenced in the IR that is not in the database).
    """
    hard_constraints: List[Dict[str, Any]] = field(default_factory=list)
    soft_constraints: List[Dict[str, Any]] = field(default_factory=list)
    solver_config: Dict[str, Any] = field(default_factory=dict)
    generation_errors: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def add_hard(self, constraint: Dict[str, Any]) -> None:
        """Append a hard constraint to the set."""
        self.hard_constraints.append(constraint)

    def add_soft(self, constraint: Dict[str, Any]) -> None:
        """Append a soft constraint to the set."""
        self.soft_constraints.append(constraint)

    def add_error(self, msg: str) -> None:
        """Record a non-fatal code-generation error."""
        logger.warning("CodeGenerator: %s", msg)
        self.generation_errors.append(msg)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Return a fully JSON-serialisable representation of the constraint set."""
        return {
            "hard_constraints": self.hard_constraints,
            "soft_constraints": self.soft_constraints,
            "solver_config": self.solver_config,
            "generation_errors": self.generation_errors,
            "summary": {
                "num_hard": len(self.hard_constraints),
                "num_soft": len(self.soft_constraints),
                "num_errors": len(self.generation_errors),
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """Return a pretty-printed JSON string of the constraint set."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @property
    def is_valid(self) -> bool:
        """True when no generation errors were recorded."""
        return len(self.generation_errors) == 0

    def summary_str(self) -> str:
        """Return a one-line human-readable summary."""
        return (
            f"ConstraintSet("
            f"hard={len(self.hard_constraints)}, "
            f"soft={len(self.soft_constraints)}, "
            f"errors={len(self.generation_errors)})"
        )


# ---------------------------------------------------------------------------
# Database helpers — thin wrappers around raw sqlite3 / any DBAPI2 connection
# ---------------------------------------------------------------------------

def _fetch_courses(db_conn) -> Dict[str, Dict[str, Any]]:
    """
    Return a dict mapping course_id → course row dict.

    Expected columns in the ``courses`` table:
      course_id, course_name, teacher_id, room_id, duration_hours,
      students_count, days_per_week
    """
    if db_conn is None:
        return {}
    try:
        cur = db_conn.cursor()
        cur.execute("SELECT * FROM courses")
        cols = [d[0] for d in cur.description] if cur.description else []
        res = {}
        for row in cur.fetchall():
            d = row if isinstance(row, dict) else dict(zip(cols, row))
            key = str(d.get("course_id") or d.get("name") or (row[0] if isinstance(row, (list, tuple)) else ""))
            if key:
                res[key] = d
        return res
    except Exception as exc:
        logger.error("Failed to fetch courses: %s", exc)
        return {}


def _fetch_rooms(db_conn) -> Dict[str, Dict[str, Any]]:
    """
    Return a dict mapping room_id → room row dict.

    Expected columns: room_id, room_name, capacity
    """
    if db_conn is None:
        return {}
    try:
        cur = db_conn.cursor()
        cur.execute("SELECT * FROM rooms")
        cols = [d[0] for d in cur.description] if cur.description else []
        res = {}
        for row in cur.fetchall():
            d = row if isinstance(row, dict) else dict(zip(cols, row))
            key = str(d.get("room_id") or d.get("name") or (row[0] if isinstance(row, (list, tuple)) else ""))
            if key:
                res[key] = d
        return res
    except Exception as exc:
        logger.error("Failed to fetch rooms: %s", exc)
        return {}


def _fetch_teachers(db_conn) -> Dict[str, Dict[str, Any]]:
    """
    Return a dict mapping teacher_id/name → teacher row dict.

    Expected columns: teacher_id, teacher_name
    """
    if db_conn is None:
        return {}
    try:
        cur = db_conn.cursor()
        cur.execute("SELECT * FROM teachers")
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            d = row if isinstance(row, dict) else dict(zip(cols, row))
            if "teacher_id" in d and d["teacher_id"]:
                result[str(d["teacher_id"])] = d
            if "name" in d and d["name"]:
                result[str(d["name"])] = d
            if "teacher_name" in d and d["teacher_name"]:
                result[str(d["teacher_name"])] = d
            if isinstance(row, (list, tuple)) and len(row) > 0:
                result[str(row[0])] = d
        return result
    except Exception as exc:
        logger.error("Failed to fetch teachers: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# CodeGenerator — the main class
# ---------------------------------------------------------------------------

class CodeGenerator:
    """
    Translate a list of :class:`IRInstruction` objects into a
    :class:`ConstraintSet` that the OR-Tools CP-SAT solver can consume.

    Compiler analogy
    ----------------
    Just as a C compiler's back-end walks an AST/IR and emits x86 instructions,
    this class walks the IR instruction list and emits constraint dictionaries.
    Each ``_emit_*`` method is analogous to an instruction-selection rule.

    Usage
    -----
    ::

        from compiler.ir_generator import IRGenerator
        from compiler.code_generator import CodeGenerator

        ir_result = IRGenerator().generate(parse_tree)
        cg = CodeGenerator()
        constraint_set = cg.generate_constraints(ir_result.instructions, db_conn)
        print(constraint_set.to_json())
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_constraints(
        self,
        ir_instructions: List[IRInstruction],
        db_conn=None,
    ) -> ConstraintSet:
        """
        Main entry point.  Walk the IR and produce a :class:`ConstraintSet`.

        Parameters
        ----------
        ir_instructions : List[IRInstruction]
            The flat list of IR instructions produced by :class:`IRGenerator`.
            These may also be plain dicts (the method normalises them).
        db_conn :
            An open DBAPI-2-compatible database connection (e.g. sqlite3).
            Pass ``None`` to skip database-backed validation; the solver will
            still receive the structural constraints from the IR.

        Returns
        -------
        ConstraintSet
            A fully populated constraint set ready for the solver.
        """
        # Normalise: accept either IRInstruction objects or raw dicts
        instructions = [
            self._normalise(instr) for instr in ir_instructions
        ]

        # Fetch live domain data from the database
        courses_db = _fetch_courses(db_conn)
        rooms_db = _fetch_rooms(db_conn)
        teachers_db = _fetch_teachers(db_conn)

        cs = ConstraintSet()

        # First pass: collect per-course accumulated data from the IR so we
        # can emit capacity and duration constraints after the full pass.
        course_students: Dict[str, int] = {}
        course_duration: Dict[str, int] = {}
        course_days_per_week: Dict[str, int] = {}
        course_room_map: Dict[str, str] = {}     # course_id → room_id

        # Flags for global constraints (emitted once, later)
        no_room_clash_requested = False
        no_teacher_clash_requested = False

        # Second-pass data: group no-clash sets
        group_courses: Dict[str, List[str]] = {}  # group_id → [course_ids]

        # ----------------------------------------------------------------
        # Dispatch loop — analogous to instruction selection in a compiler
        # ----------------------------------------------------------------
        for instr in instructions:
            itype = instr.type

            if itype == "GLOBAL_CONSTRAINT":
                name = instr.params.get("constraint_name", "")
                if name == "NO_ROOM_CLASH":
                    no_room_clash_requested = True
                elif name == "NO_TEACHER_CLASH":
                    no_teacher_clash_requested = True
                else:
                    cs.add_error(f"Unknown global constraint: '{name}'")

            elif itype == "TEACHER_UNAVAILABLE":
                self._emit_teacher_unavailable(instr, cs)

            elif itype == "COURSE_ROOM":
                course_id = instr.params.get("course", "")
                room_id = instr.params.get("room", "")
                course_room_map[course_id] = room_id
                self._emit_course_room(instr, rooms_db, cs)

            elif itype == "COURSE_TEACHER":
                self._emit_course_teacher(instr, teachers_db, cs)

            elif itype == "COURSE_DURATION":
                course_id = instr.params.get("course", "")
                hours = instr.params.get("hours", 1)
                try:
                    course_duration[course_id] = int(hours)
                except (ValueError, TypeError):
                    cs.add_error(
                        f"Invalid duration value '{hours}' for course '{course_id}'"
                    )
                self._emit_course_duration(instr, cs)

            elif itype == "COURSE_STUDENTS":
                course_id = instr.params.get("course", "")
                count = instr.params.get("count", 0)
                try:
                    course_students[course_id] = int(count)
                except (ValueError, TypeError):
                    cs.add_error(
                        f"Invalid student count '{count}' for course '{course_id}'"
                    )

            elif itype == "COURSE_DAYS_PER_WEEK":
                course_id = instr.params.get("course", "")
                days = instr.params.get("days", 1)
                try:
                    course_days_per_week[course_id] = int(days)
                except (ValueError, TypeError):
                    cs.add_error(
                        f"Invalid days_per_week value '{days}' for course '{course_id}'"
                    )
                self._emit_course_days_per_week(instr, cs)

            elif itype == "ROOM_CAPACITY":
                self._emit_room_capacity(instr, rooms_db, cs)

            elif itype == "COURSE_PREFERRED_TIME":
                self._emit_preferred_time(instr, cs)

            elif itype == "COURSE_PREFERRED_DAY":
                self._emit_preferred_day(instr, cs)

            elif itype == "GROUP_NO_CLASH":
                group_id = instr.params.get("group", "")
                # Group membership is resolved later via the DB or naming
                # convention; for now record the group name.
                if group_id not in group_courses:
                    group_courses[group_id] = []
                self._emit_group_no_clash(instr, cs)

            else:
                cs.add_error(
                    f"Unknown IR instruction type: '{itype}' — skipped"
                )

        # ----------------------------------------------------------------
        # Emit global clash constraints after the full pass
        # ----------------------------------------------------------------
        if no_room_clash_requested:
            self._emit_room_clash_free(cs)

        if no_teacher_clash_requested:
            self._emit_teacher_clash_free(cs)

        # ----------------------------------------------------------------
        # Cross-reference: room capacity vs enrolled students
        # ----------------------------------------------------------------
        self._emit_capacity_vs_students(
            course_students, course_room_map, rooms_db, cs
        )

        # ----------------------------------------------------------------
        # Build solver configuration (variable domains, objective weights)
        # ----------------------------------------------------------------
        cs.solver_config = self._build_solver_config(
            courses_db=courses_db,
            rooms_db=rooms_db,
            teachers_db=teachers_db,
            course_duration=course_duration,
            course_days_per_week=course_days_per_week,
        )

        logger.info(
            "CodeGenerator finished. %s", cs.summary_str()
        )
        return cs

    # ------------------------------------------------------------------
    # Private emit methods — one per constraint type
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise(instr) -> IRInstruction:
        """
        Accept either an :class:`IRInstruction`, an IRInstruction from ir_generator,
        or a plain dict and return a code_generator :class:`IRInstruction`.
        """
        if isinstance(instr, IRInstruction):
            return instr
        if hasattr(instr, "type") and hasattr(instr, "fields"):
            return IRInstruction(type=instr.type, params=dict(instr.fields))
        if hasattr(instr, "type") and hasattr(instr, "params"):
            return IRInstruction(type=instr.type, params=dict(instr.params))
        if hasattr(instr, "to_dict"):
            d = dict(instr.to_dict())
            itype = d.pop("type", "UNKNOWN")
            return IRInstruction(type=itype, params=d)
        if isinstance(instr, dict):
            d = dict(instr)
            itype = d.pop("type", "UNKNOWN")
            return IRInstruction(type=itype, params=d)
        raise TypeError(
            f"Expected IRInstruction or dict, got {type(instr).__name__}"
        )

    # --- Global clash-free constraints -----------------------------------

    @staticmethod
    def _emit_room_clash_free(cs: ConstraintSet) -> None:
        """
        Emit a hard constraint that ensures no two courses share the same room
        in the same time slot.

        OR-Tools encoding hint: for each (room, day, slot) variable, at most
        one course may be assigned true.  The solver implements this with
        ``AddAtMostOne`` over the Boolean indicators.
        """
        cs.add_hard({
            "constraint_type": "ROOM_CLASH_FREE",
            "description": (
                "No two courses may be assigned to the same room "
                "on the same day at the same time slot."
            ),
            "scope": "global",
            "ortools_hint": "AddAtMostOne over (room, day, slot) indicators",
        })

    @staticmethod
    def _emit_teacher_clash_free(cs: ConstraintSet) -> None:
        """
        Emit a hard constraint that ensures no teacher is assigned to two
        courses at the same time.

        OR-Tools encoding hint: ``AddAtMostOne`` over (teacher, day, slot)
        Boolean indicators.
        """
        cs.add_hard({
            "constraint_type": "TEACHER_CLASH_FREE",
            "description": (
                "No teacher may be assigned to more than one course "
                "in the same day–time-slot combination."
            ),
            "scope": "global",
            "ortools_hint": "AddAtMostOne over (teacher, day, slot) indicators",
        })

    # --- Per-entity constraints ------------------------------------------

    @staticmethod
    def _emit_teacher_unavailable(
        instr: IRInstruction,
        cs: ConstraintSet,
    ) -> None:
        """
        Block a specific (teacher, day, time) combination.

        Generated from DSL rule:
          RULE <teacher> NOT_AVAILABLE <day> <time>;

        OR-Tools encoding: set the Boolean indicator variable for
        (teacher, day, slot) to 0 (False).
        """
        teacher = instr.params.get("teacher", "")
        day = instr.params.get("day", "")
        time_str = instr.params.get("time", "")

        # Validate day/time against the DSL spec
        errors: List[str] = []
        if day not in VALID_DAYS:
            errors.append(
                f"Teacher '{teacher}' unavailability: "
                f"invalid day '{day}' (expected one of {VALID_DAYS})"
            )
        if time_str not in VALID_TIMES:
            errors.append(
                f"Teacher '{teacher}' unavailability: "
                f"invalid time '{time_str}' (expected one of {VALID_TIMES})"
            )
        for err in errors:
            cs.add_error(err)
        if errors:
            return

        slot_index = TIME_TO_SLOT[time_str]
        day_index = DAY_TO_INDEX[day]

        cs.add_hard({
            "constraint_type": "TEACHER_UNAVAILABLE",
            "teacher": teacher,
            "day": day,
            "day_index": day_index,
            "time": time_str,
            "slot_index": slot_index,
            "description": (
                f"Teacher '{teacher}' is unavailable on {day} at {time_str}."
            ),
            "ortools_hint": (
                f"model.Add(teacher_day_slot['{teacher}'][{day_index}]"
                f"[{slot_index}] == 0)"
            ),
        })

    @staticmethod
    def _emit_course_room(
        instr: IRInstruction,
        rooms_db: Dict[str, Dict[str, Any]],
        cs: ConstraintSet,
    ) -> None:
        """
        Assign a specific room to a course.

        Generated from DSL rule:
          RULE <course_id> ROOM <room_id>;

        OR-Tools encoding: fix the room decision variable for the course.
        """
        course_id = instr.params.get("course", "")
        room_id = instr.params.get("room", "")

        if room_id not in rooms_db and rooms_db:
            cs.add_error(
                f"Course '{course_id}': assigned room '{room_id}' "
                f"not found in the database."
            )
            # Still emit — solver may handle unknown rooms gracefully
        capacity = (
            rooms_db.get(room_id, {}).get("capacity", None)
        )
        cs.add_hard({
            "constraint_type": "COURSE_ROOM_ASSIGNMENT",
            "course_id": course_id,
            "room_id": room_id,
            "room_capacity": capacity,
            "description": (
                f"Course '{course_id}' must be held in room '{room_id}'."
            ),
            "ortools_hint": (
                f"Fix room variable for course '{course_id}' to '{room_id}'"
            ),
        })

    @staticmethod
    def _emit_course_teacher(
        instr: IRInstruction,
        teachers_db: Dict[str, Dict[str, Any]],
        cs: ConstraintSet,
    ) -> None:
        """
        Assign a specific teacher to a course.

        Generated from DSL rule:
          RULE <course_id> TEACHER <teacher_name>;
        """
        course_id = instr.params.get("course", "")
        teacher = instr.params.get("teacher", "")

        if teacher not in teachers_db and teachers_db:
            cs.add_error(
                f"Course '{course_id}': assigned teacher '{teacher}' "
                f"not found in the database."
            )

        cs.add_hard({
            "constraint_type": "COURSE_TEACHER_ASSIGNMENT",
            "course_id": course_id,
            "teacher": teacher,
            "description": (
                f"Course '{course_id}' must be taught by '{teacher}'."
            ),
            "ortools_hint": (
                f"Fix teacher variable for course '{course_id}' to '{teacher}'"
            ),
        })

    @staticmethod
    def _emit_course_duration(
        instr: IRInstruction,
        cs: ConstraintSet,
    ) -> None:
        """
        Constrain the session length for a course.

        Generated from DSL rule:
          RULE <course_id> DURATION <n>HOUR;

        OR-Tools encoding: each session of the course occupies exactly n
        consecutive time slots.  The solver enforces that slots [t, t+n-1]
        are all assigned to the course without overlap with other courses.
        """
        course_id = instr.params.get("course", "")
        hours = instr.params.get("hours", 1)

        try:
            hours_int = int(hours)
        except (ValueError, TypeError):
            cs.add_error(
                f"Course '{course_id}': invalid duration value '{hours}'. "
                f"Must be an integer 1–3."
            )
            return

        if not 1 <= hours_int <= 3:
            cs.add_error(
                f"Course '{course_id}': duration {hours_int} is outside the "
                f"permitted range [1, 3]."
            )
            # Still emit with the given value so the solver can try

        cs.add_hard({
            "constraint_type": "COURSE_DURATION",
            "course_id": course_id,
            "duration_hours": hours_int,
            "description": (
                f"Each session of course '{course_id}' lasts {hours_int} hour(s)."
            ),
            "ortools_hint": (
                f"Session occupies {hours_int} consecutive slot(s); "
                f"end slot = start + {hours_int} - 1"
            ),
        })

    @staticmethod
    def _emit_course_days_per_week(
        instr: IRInstruction,
        cs: ConstraintSet,
    ) -> None:
        """
        Require that a course meets exactly N days per week.

        Generated from DSL rule:
          RULE <course_id> DAYS_PER_WEEK <n>;

        OR-Tools encoding: sum of Boolean day-assignment variables for the
        course over the 5 working days must equal n.
        """
        course_id = instr.params.get("course", "")
        days = instr.params.get("days", 1)

        try:
            days_int = int(days)
        except (ValueError, TypeError):
            cs.add_error(
                f"Course '{course_id}': invalid days_per_week '{days}'. "
                f"Must be an integer 1–5."
            )
            return

        if not 1 <= days_int <= 5:
            cs.add_error(
                f"Course '{course_id}': days_per_week {days_int} out of range [1, 5]."
            )

        cs.add_hard({
            "constraint_type": "COURSE_DAYS_PER_WEEK",
            "course_id": course_id,
            "days_per_week": days_int,
            "description": (
                f"Course '{course_id}' must be scheduled on "
                f"exactly {days_int} day(s) per week."
            ),
            "ortools_hint": (
                f"AddLinearConstraint: sum(day_vars['{course_id}'][d] "
                f"for d in days) == {days_int}"
            ),
        })

    @staticmethod
    def _emit_room_capacity(
        instr: IRInstruction,
        rooms_db: Dict[str, Dict[str, Any]],
        cs: ConstraintSet,
    ) -> None:
        """
        Register a room's capacity.

        Generated from DSL rule:
          RULE <room_id> CAPACITY <n>;

        This is treated as a hard constraint: any course assigned to this room
        must have enrolled students ≤ n.
        """
        room_id = instr.params.get("room", "")
        capacity = instr.params.get("capacity", 0)

        try:
            cap_int = int(capacity)
        except (ValueError, TypeError):
            cs.add_error(
                f"Room '{room_id}': invalid capacity value '{capacity}'."
            )
            return

        # Cross-check with DB if available
        db_cap = rooms_db.get(room_id, {}).get("capacity", None)
        if db_cap is not None and db_cap != cap_int:
            cs.add_error(
                f"Room '{room_id}': DSL capacity {cap_int} contradicts "
                f"database capacity {db_cap}. Using DSL value."
            )

        cs.add_hard({
            "constraint_type": "ROOM_CAPACITY",
            "room_id": room_id,
            "capacity": cap_int,
            "description": (
                f"Room '{room_id}' has a maximum capacity of {cap_int} students."
            ),
            "ortools_hint": (
                f"For every course c assigned to room '{room_id}': "
                f"students(c) <= {cap_int}"
            ),
        })

    @staticmethod
    def _emit_capacity_vs_students(
        course_students: Dict[str, int],
        course_room_map: Dict[str, str],
        rooms_db: Dict[str, Dict[str, Any]],
        cs: ConstraintSet,
    ) -> None:
        """
        Cross-reference enrolled students against assigned room capacity.

        This pass runs after all individual room/student IR instructions have
        been processed.  For every course that has BOTH a known student count
        AND a room assignment in the IR, we emit an explicit capacity check
        constraint.
        """
        for course_id, students in course_students.items():
            room_id = course_room_map.get(course_id)
            if room_id is None:
                # Room not constrained by IR; solver handles it generically
                continue

            capacity = rooms_db.get(room_id, {}).get("capacity")
            if capacity is None:
                # Capacity unknown; can't check
                continue

            if students > capacity:
                cs.add_error(
                    f"Course '{course_id}' has {students} students but its "
                    f"assigned room '{room_id}' has capacity {capacity}. "
                    f"This will be INFEASIBLE unless the room is changed."
                )

            cs.add_hard({
                "constraint_type": "CAPACITY_CHECK",
                "course_id": course_id,
                "room_id": room_id,
                "students": students,
                "room_capacity": capacity,
                "feasible": students <= capacity,
                "description": (
                    f"Course '{course_id}' ({students} students) in room "
                    f"'{room_id}' (capacity {capacity}): "
                    f"{'OK' if students <= capacity else 'OVERFLOW'}."
                ),
                "ortools_hint": (
                    f"Assert students({course_id}) <= capacity({room_id})"
                ),
            })

    @staticmethod
    def _emit_preferred_time(
        instr: IRInstruction,
        cs: ConstraintSet,
    ) -> None:
        """
        Express a soft preference for a specific start time.

        Generated from DSL rule:
          RULE <course_id> PREFERRED_TIME <time>;

        OR-Tools encoding: add a penalty term to the objective function that
        increases when the course is NOT assigned to the preferred time slot.
        """
        course_id = instr.params.get("course", "")
        time_str = instr.params.get("time", "")
        penalty = instr.params.get("penalty", DEFAULT_PREFERRED_TIME_PENALTY)

        if time_str not in VALID_TIMES:
            cs.add_error(
                f"Course '{course_id}': preferred time '{time_str}' is invalid. "
                f"Must be one of {VALID_TIMES}."
            )
            return

        slot_index = TIME_TO_SLOT[time_str]

        cs.add_soft({
            "constraint_type": "PREFERRED_TIME",
            "course_id": course_id,
            "preferred_time": time_str,
            "slot_index": slot_index,
            "penalty_cost": int(penalty),
            "description": (
                f"Course '{course_id}' prefers to start at {time_str} "
                f"(penalty {penalty} if not met)."
            ),
            "ortools_hint": (
                f"objective += {penalty} * (1 - is_at_slot['{course_id}'][{slot_index}])"
            ),
        })

    @staticmethod
    def _emit_preferred_day(
        instr: IRInstruction,
        cs: ConstraintSet,
    ) -> None:
        """
        Express a soft preference for a specific day.

        Generated from DSL rule:
          RULE <course_id> PREFERRED_DAY <day>;
        """
        course_id = instr.params.get("course", "")
        day = instr.params.get("day", "")
        penalty = instr.params.get("penalty", DEFAULT_PREFERRED_DAY_PENALTY)

        if day not in VALID_DAYS:
            cs.add_error(
                f"Course '{course_id}': preferred day '{day}' is invalid. "
                f"Must be one of {VALID_DAYS}."
            )
            return

        day_index = DAY_TO_INDEX[day]

        cs.add_soft({
            "constraint_type": "PREFERRED_DAY",
            "course_id": course_id,
            "preferred_day": day,
            "day_index": day_index,
            "penalty_cost": int(penalty),
            "description": (
                f"Course '{course_id}' prefers to be held on {day} "
                f"(penalty {penalty} if not met)."
            ),
            "ortools_hint": (
                f"objective += {penalty} * (1 - is_on_day['{course_id}'][{day_index}])"
            ),
        })

    @staticmethod
    def _emit_group_no_clash(
        instr: IRInstruction,
        cs: ConstraintSet,
    ) -> None:
        """
        Ensure courses in a student group do not overlap in time.

        Generated from DSL rule:
          RULE <group_id> NO_CLASH;

        OR-Tools encoding: for every pair of courses (c1, c2) in the group,
        at every (day, slot) combination, at most one of them may be assigned
        there: ``AddAtMostOne([indicator(c1,d,t), indicator(c2,d,t)])``.

        Note: the actual list of courses in the group is resolved by the solver
        from the database.  The code generator records the group name and the
        solver fetches group membership at solve time.
        """
        group_id = instr.params.get("group", "")

        cs.add_hard({
            "constraint_type": "GROUP_NO_CLASH",
            "group_id": group_id,
            "description": (
                f"All courses in student group '{group_id}' must not "
                f"overlap in time."
            ),
            "ortools_hint": (
                f"For every (c1, c2) in group '{group_id}' and "
                f"every (day, slot): "
                f"AddAtMostOne([ind(c1,d,t), ind(c2,d,t)])"
            ),
        })

    # ------------------------------------------------------------------
    # Solver configuration builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_solver_config(
        courses_db: Dict[str, Dict[str, Any]],
        rooms_db: Dict[str, Dict[str, Any]],
        teachers_db: Dict[str, Dict[str, Any]],
        course_duration: Dict[str, int],
        course_days_per_week: Dict[str, int],
    ) -> Dict[str, Any]:
        """
        Build a configuration dict that the solver uses to set up its
        decision variables and search parameters.

        The solver needs to know:
          - The full set of courses, rooms, teachers (variable domains)
          - Valid days and time slots
          - Per-course duration and sessions-per-week (to size variables)
          - Objective function weights

        Returns
        -------
        dict
            Solver configuration including domain information.
        """
        # Collect unique course IDs from the database
        all_course_ids = list(courses_db.keys()) if courses_db else []

        # Collect unique room IDs
        all_room_ids = list(rooms_db.keys()) if rooms_db else []

        # Collect unique teacher names (de-duplicate: DB may have both id+name)
        teacher_names: List[str] = []
        seen_teachers = set()
        for rec in (teachers_db.values() if teachers_db else []):
            name = rec.get("teacher_name", "")
            if name and name not in seen_teachers:
                teacher_names.append(name)
                seen_teachers.add(name)

        # Build per-course session count (defaults to 1 session/day × days_per_week)
        course_sessions: Dict[str, int] = {}
        for cid in all_course_ids:
            dpw = course_days_per_week.get(cid)
            if dpw is None:
                # Try DB column
                dpw = int(
                    courses_db.get(cid, {}).get("days_per_week", 1) or 1
                )
            course_sessions[cid] = dpw

        return {
            # ---- Domain data ----
            "days": VALID_DAYS,
            "day_indices": {d: i for i, d in enumerate(VALID_DAYS)},
            "time_slots": VALID_TIMES,
            "slot_indices": TIME_TO_SLOT,
            "num_days": len(VALID_DAYS),
            "num_slots": len(VALID_TIMES),

            # ---- Entities ----
            "course_ids": all_course_ids,
            "room_ids": all_room_ids,
            "teacher_names": teacher_names,

            # ---- Per-course solver parameters ----
            "course_durations": course_duration,     # course_id → int hours
            "course_sessions_per_week": course_sessions,  # course_id → int

            # ---- Search parameters ----
            "max_solve_time_seconds": 60,
            "num_search_workers": 4,
            "log_search_progress": False,

            # ---- Objective function weights ----
            "objective": {
                "minimise": "total_penalty",
                "preferred_time_penalty_weight": DEFAULT_PREFERRED_TIME_PENALTY,
                "preferred_day_penalty_weight": DEFAULT_PREFERRED_DAY_PENALTY,
            },

            # ---- Metadata ----
            "generated_by": "CodeGenerator",
            "dsl_version": "1.0",
        }


# ---------------------------------------------------------------------------
# Convenience function (useful in notebooks / tests)
# ---------------------------------------------------------------------------

def generate_constraints_from_ir(
    ir_instructions: List[Any],
    db_conn=None,
) -> ConstraintSet:
    """
    Module-level helper: instantiate :class:`CodeGenerator` and call
    :meth:`generate_constraints` in one step.

    Parameters
    ----------
    ir_instructions : List[IRInstruction | dict]
        IR instructions from the IR generator.
    db_conn :
        Open DBAPI-2 database connection, or ``None``.

    Returns
    -------
    ConstraintSet
    """
    return CodeGenerator().generate_constraints(ir_instructions, db_conn)


# ---------------------------------------------------------------------------
# CLI self-test (python -m compiler.code_generator)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

    print("=" * 60)
    print("CodeGenerator — self-test with synthetic IR instructions")
    print("=" * 60)

    sample_ir: List[Dict[str, Any]] = [
        # Global constraints
        {"type": "GLOBAL_CONSTRAINT", "constraint_name": "NO_ROOM_CLASH"},
        {"type": "GLOBAL_CONSTRAINT", "constraint_name": "NO_TEACHER_CLASH"},

        # Teacher unavailability
        {"type": "TEACHER_UNAVAILABLE",
         "teacher": "Dr_Ahmed", "day": "Monday", "time": "8AM"},
        {"type": "TEACHER_UNAVAILABLE",
         "teacher": "Prof_Khan", "day": "Friday", "time": "5PM"},

        # Course assignments
        {"type": "COURSE_ROOM",    "course": "CS101",  "room": "R101"},
        {"type": "COURSE_TEACHER", "course": "CS101",  "teacher": "Dr_Ahmed"},
        {"type": "COURSE_DURATION","course": "CS101",  "hours": 2},
        {"type": "COURSE_STUDENTS","course": "CS101",  "count": 40},
        {"type": "COURSE_DAYS_PER_WEEK", "course": "CS101", "days": 3},

        {"type": "COURSE_ROOM",    "course": "MATH201","room": "R202"},
        {"type": "COURSE_TEACHER", "course": "MATH201","teacher": "Prof_Khan"},
        {"type": "COURSE_DURATION","course": "MATH201","hours": 1},
        {"type": "COURSE_STUDENTS","course": "MATH201","count": 55},
        {"type": "COURSE_DAYS_PER_WEEK","course": "MATH201","days": 2},

        # Room capacities
        {"type": "ROOM_CAPACITY", "room": "R101", "capacity": 50},
        {"type": "ROOM_CAPACITY", "room": "R202", "capacity": 45},  # overflow!

        # Soft preferences
        {"type": "COURSE_PREFERRED_TIME", "course": "CS101",   "time": "10AM"},
        {"type": "COURSE_PREFERRED_DAY",  "course": "MATH201", "day": "Wednesday"},

        # Group no-clash
        {"type": "GROUP_NO_CLASH", "group": "BSCS_Y1"},
    ]

    cg = CodeGenerator()
    result = cg.generate_constraints(sample_ir, db_conn=None)

    print("\n--- Hard Constraints ---")
    for c in result.hard_constraints:
        print(f"  [{c['constraint_type']}] {c.get('description','')}")

    print("\n--- Soft Constraints ---")
    for c in result.soft_constraints:
        print(f"  [{c['constraint_type']}] {c.get('description','')}"
              f"  (penalty={c.get('penalty_cost')})")

    print("\n--- Generation Errors ---")
    for e in result.generation_errors:
        print(f"  ⚠  {e}")

    print("\n--- Solver Config (keys) ---")
    for k, v in result.solver_config.items():
        if not isinstance(v, (list, dict)):
            print(f"  {k}: {v}")
        else:
            print(f"  {k}: {type(v).__name__}[{len(v)}]")

    print("\n" + result.summary_str())
    print("\nJSON output snippet (first hard constraint):")
    if result.hard_constraints:
        print(json.dumps(result.hard_constraints[0], indent=2))
