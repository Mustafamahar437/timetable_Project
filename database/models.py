"""
database/models.py
==================
Database manager for the Smart University Timetable Constraint Compiler.
Supports standard SQLite (sqlite3) with seamless fallback to an in-memory/JSON
relational table store if Windows Application Control / AppLocker blocks native _sqlite3.pyd.
"""

from __future__ import annotations

import os
import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Attempt to import native sqlite3
try:
    import sqlite3
    SQLITE_AVAILABLE = True
except Exception:
    sqlite3 = None
    SQLITE_AVAILABLE = False


class _FallbackCursor:
    """A lightweight SQL-compatible cursor for when native sqlite3 is unavailable."""
    def __init__(self, db: "DatabaseManager"):
        self.db = db
        self._last_results = []
        self.description = [("id",), ("name",)]

    def execute(self, sql: str, params: tuple = ()):
        sql_clean = " ".join(sql.strip().split())
        sql_upper = sql_clean.upper()

        if "SELECT * FROM TEACHERS" in sql_upper:
            if "WHERE NAME =" in sql_upper:
                name_query = params[0].lower()
                self._last_results = [t for t in self.db._store["teachers"] if t["name"].lower() == name_query or t.get("teacher_id", "").lower() == name_query]
            else:
                self._last_results = sorted(self.db._store["teachers"], key=lambda x: x.get("name", ""))
            self.description = [("id",), ("teacher_id",), ("name",), ("email",), ("department",)]

        elif "SELECT * FROM COURSES" in sql_upper or "SELECT COURSE_ID" in sql_upper:
            if "WHERE COURSE_ID =" in sql_upper:
                cid_query = params[0].lower()
                self._last_results = [c for c in self.db._store["courses"] if c["course_id"].lower() == cid_query]
            else:
                self._last_results = sorted(self.db._store["courses"], key=lambda x: x.get("course_id", ""))
            self.description = [("id",), ("course_id",), ("name",), ("course_name",), ("department",), ("credit_hours",), ("teacher_id",), ("room_id",), ("duration_hours",), ("students_count",), ("days_per_week",)]

        elif "SELECT * FROM ROOMS" in sql_upper or "SELECT ROOM_ID" in sql_upper:
            if "WHERE ROOM_ID =" in sql_upper:
                rid_query = params[0].lower()
                self._last_results = [r for r in self.db._store["rooms"] if r["room_id"].lower() == rid_query]
            else:
                self._last_results = sorted(self.db._store["rooms"], key=lambda x: x.get("room_id", ""))
            self.description = [("id",), ("room_id",), ("name",), ("room_name",), ("capacity",), ("room_type",)]

        elif "SELECT * FROM STUDENT_GROUPS" in sql_upper:
            self._last_results = sorted(self.db._store["student_groups"], key=lambda x: x.get("group_id", ""))
            self.description = [("id",), ("group_id",), ("name",), ("size",), ("department",)]

        elif "SELECT * FROM TIME_SLOTS" in sql_upper:
            self._last_results = sorted(self.db._store["time_slots"], key=lambda x: x.get("slot_index", 0))
            self.description = [("id",), ("slot_id",), ("start_time",), ("end_time",), ("slot_index",)]

        elif "SELECT * FROM DAYS" in sql_upper:
            self._last_results = sorted(self.db._store["days"], key=lambda x: x.get("day_index", 0))
            self.description = [("id",), ("day_name",), ("day_index",)]

        elif "SELECT * FROM TIMETABLE_ENTRIES" in sql_upper:
            self._last_results = list(self.db._store["timetable_entries"])
            self.description = [("id",), ("course_id",), ("teacher_name",), ("room_id",), ("group_id",), ("day",), ("time_slot",), ("duration",)]

        elif "DELETE FROM TIMETABLE_ENTRIES" in sql_upper:
            self.db._store["timetable_entries"].clear()
            self._last_results = []

        elif "INSERT" in sql_upper:
            if "INTO TEACHERS" in sql_upper:
                t_id, name, email, dept = params
                self.db._store["teachers"] = [t for t in self.db._store["teachers"] if t["name"] != name]
                self.db._store["teachers"].append({"id": len(self.db._store["teachers"]) + 1, "teacher_id": t_id, "name": name, "email": email, "department": dept})
            elif "INTO ROOMS" in sql_upper:
                r_id, name, r_name, cap, r_type = params
                self.db._store["rooms"] = [r for r in self.db._store["rooms"] if r["room_id"] != r_id]
                self.db._store["rooms"].append({"id": len(self.db._store["rooms"]) + 1, "room_id": r_id, "name": name, "room_name": r_name, "capacity": cap, "room_type": r_type})
            elif "INTO COURSES" in sql_upper:
                if len(params) == 10:
                    c_id, name, c_name, dept, cr, t_id, r_id, dur, stu, dpw = params
                else:
                    c_id, name, c_name, dept, cr, stu, dpw, dur = params
                    t_id, r_id = "Ahmed", "CR1"
                self.db._store["courses"] = [c for c in self.db._store["courses"] if c["course_id"] != c_id]
                self.db._store["courses"].append({
                    "id": len(self.db._store["courses"]) + 1,
                    "course_id": c_id,
                    "name": name,
                    "course_name": c_name,
                    "department": dept,
                    "credit_hours": cr,
                    "students_count": stu,
                    "days_per_week": dpw,
                    "duration_hours": dur,
                    "teacher_id": t_id,
                    "room_id": r_id
                })
            elif "INTO STUDENT_GROUPS" in sql_upper:
                g_id, name, sz, dept = params
                self.db._store["student_groups"] = [g for g in self.db._store["student_groups"] if g["group_id"] != g_id]
                self.db._store["student_groups"].append({"id": len(self.db._store["student_groups"]) + 1, "group_id": g_id, "name": name, "size": sz, "department": dept})
            elif "INTO TIMETABLE_ENTRIES" in sql_upper:
                c_id, t_name, r_id, g_id, day, slot, dur = params
                self.db._store["timetable_entries"].append({"id": len(self.db._store["timetable_entries"]) + 1, "course_id": c_id, "teacher_name": t_name, "room_id": r_id, "group_id": g_id, "day": day, "time_slot": slot, "duration": dur})
            self._last_results = []
        return self

    def fetchall(self) -> List[Dict[str, Any]]:
        return list(self._last_results)

    def fetchone(self) -> Optional[Dict[str, Any]]:
        return self._last_results[0] if self._last_results else None


class _FallbackConnection:
    """Wraps the fallback store to provide standard DB-API context management."""
    def __init__(self, db: "DatabaseManager"):
        self.db = db

    def cursor(self):
        return _FallbackCursor(self.db)

    def commit(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class DatabaseManager:
    """Manages SQLite database operations with seamless fallback for locked environments."""

    def __init__(self, db_path: str = "timetable.db") -> None:
        self.db_path = db_path
        self._shared_conn = None
        self._store = {
            "teachers": [],
            "courses": [],
            "rooms": [],
            "student_groups": [],
            "time_slots": [],
            "days": [],
            "timetable_entries": []
        }

    def get_connection(self):
        if SQLITE_AVAILABLE and self.db_path != ":memory_fallback:":
            try:
                if self.db_path == ":memory:":
                    if self._shared_conn is None:
                        self._shared_conn = sqlite3.connect(":memory:")
                        self._shared_conn.row_factory = sqlite3.Row
                    return self._shared_conn
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                return conn
            except Exception as exc:
                logger.warning("SQLite connect failed (%s), using resilient store.", exc)
        return _FallbackConnection(self)

    def initialize_db(self) -> None:
        if SQLITE_AVAILABLE and self.db_path != ":memory_fallback:":
            try:
                with self.get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("CREATE TABLE IF NOT EXISTS teachers (id INTEGER PRIMARY KEY, teacher_id TEXT, name TEXT UNIQUE, email TEXT, department TEXT);")
                    cur.execute("CREATE TABLE IF NOT EXISTS rooms (id INTEGER PRIMARY KEY, room_id TEXT UNIQUE, name TEXT, room_name TEXT, capacity INTEGER, room_type TEXT);")
                    cur.execute("CREATE TABLE IF NOT EXISTS courses (id INTEGER PRIMARY KEY, course_id TEXT UNIQUE, name TEXT, course_name TEXT, department TEXT, credit_hours INTEGER, teacher_id TEXT, room_id TEXT, duration_hours INTEGER, students_count INTEGER, days_per_week INTEGER);")
                    cur.execute("CREATE TABLE IF NOT EXISTS student_groups (id INTEGER PRIMARY KEY, group_id TEXT UNIQUE, name TEXT, size INTEGER, department TEXT);")
                    cur.execute("CREATE TABLE IF NOT EXISTS time_slots (id INTEGER PRIMARY KEY, slot_id TEXT UNIQUE, start_time TEXT, end_time TEXT, slot_index INTEGER);")
                    cur.execute("CREATE TABLE IF NOT EXISTS days (id INTEGER PRIMARY KEY, day_name TEXT UNIQUE, day_index INTEGER);")
                    cur.execute("CREATE TABLE IF NOT EXISTS timetable_entries (id INTEGER PRIMARY KEY, course_id TEXT, teacher_name TEXT, room_id TEXT, group_id TEXT, day TEXT, time_slot TEXT, duration INTEGER);")
                    conn.commit()
                    return
            except Exception:
                pass

        # Fallback in-memory initialization
        pass

    def get_teachers(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM teachers ORDER BY name")
            return [dict(r) for r in cur.fetchall()]

    def get_courses(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM courses ORDER BY course_id")
            return [dict(r) for r in cur.fetchall()]

    def get_rooms(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM rooms ORDER BY room_id")
            return [dict(r) for r in cur.fetchall()]

    def get_student_groups(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM student_groups ORDER BY group_id")
            return [dict(r) for r in cur.fetchall()]

    def get_time_slots(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM time_slots ORDER BY slot_index")
            return [dict(r) for r in cur.fetchall()]

    def get_days(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM days ORDER BY day_index")
            return [dict(r) for r in cur.fetchall()]

    def get_teacher_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM teachers WHERE name = ? COLLATE NOCASE", (name,))
            r = cur.fetchone()
            return dict(r) if r else None

    def get_course_by_id(self, course_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM courses WHERE course_id = ? COLLATE NOCASE", (course_id,))
            r = cur.fetchone()
            return dict(r) if r else None

    def get_room_by_id(self, room_id: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM rooms WHERE room_id = ? COLLATE NOCASE", (room_id,))
            r = cur.fetchone()
            return dict(r) if r else None

    def add_teacher(self, name: str, email: str = "", department: str = "Computer Science") -> None:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO teachers (teacher_id, name, email, department) VALUES (?, ?, ?, ?)",
                (name, name, email, department),
            )
            conn.commit()

    def add_course(
        self,
        course_id: str,
        name: str,
        department: str = "Computer Science",
        credit_hours: int = 3,
        students_count: int = 40,
        days_per_week: int = 2,
        duration_hours: int = 1,
        teacher_id: str = "",
        room_id: str = "",
    ) -> None:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT OR REPLACE INTO courses
                (course_id, name, course_name, department, credit_hours, teacher_id, room_id, duration_hours, students_count, days_per_week)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (course_id, name, name, department, credit_hours, teacher_id, room_id, duration_hours, students_count, days_per_week),
            )
            conn.commit()

    def add_room(
        self,
        room_id: str,
        name: str = "",
        capacity: int = 50,
        room_type: str = "LECTURE",
    ) -> None:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO rooms (room_id, name, room_name, capacity, room_type) VALUES (?, ?, ?, ?, ?)",
                (room_id, name or room_id, name or room_id, capacity, room_type),
            )
            conn.commit()

    def add_student_group(
        self, group_id: str, name: str, size: int = 40, department: str = "Computer Science"
    ) -> None:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO student_groups (group_id, name, size, department) VALUES (?, ?, ?, ?)",
                (group_id, name, size, department),
            )
            conn.commit()

    def clear_timetable(self) -> None:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM timetable_entries")
            conn.commit()

    def save_timetable(self, entries: List[Dict[str, Any]]) -> None:
        self.clear_timetable()
        with self.get_connection() as conn:
            cur = conn.cursor()
            for entry in entries:
                cur.execute(
                    """
                    INSERT INTO timetable_entries 
                    (course_id, teacher_name, room_id, group_id, day, time_slot, duration)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.get("course_id", ""),
                        entry.get("teacher_name", ""),
                        entry.get("room_id", ""),
                        entry.get("group_id", "ALL"),
                        entry.get("day", ""),
                        entry.get("time_slot", ""),
                        entry.get("duration", 1),
                    ),
                )
            conn.commit()

    def get_timetable_entries(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM timetable_entries ORDER BY day, time_slot")
            return [dict(r) for r in cur.fetchall()]
