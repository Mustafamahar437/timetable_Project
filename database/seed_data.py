"""
database/seed_data.py
=====================
Seed realistic university dataset for testing and demonstration.
Includes Faculty, Courses, Lecture Halls, Laboratories, Time Slots, and Student Groups.
"""

from __future__ import annotations
from database.models import DatabaseManager


def seed_database(db: DatabaseManager) -> None:
    """Populates the database with realistic sample university data."""
    db.initialize_db()

    with db.get_connection() as conn:
        cur = conn.cursor()

        # 1. Days
        days = [
            ("Monday", 0),
            ("Tuesday", 1),
            ("Wednesday", 2),
            ("Thursday", 3),
            ("Friday", 4),
        ]
        for day_name, day_idx in days:
            cur.execute(
                "INSERT OR IGNORE INTO days (day_name, day_index) VALUES (?, ?)",
                (day_name, day_idx),
            )

        # 2. Time Slots
        slots = [
            ("8AM", "08:00", "09:00", 0),
            ("9AM", "09:00", "10:00", 1),
            ("10AM", "10:00", "11:00", 2),
            ("11AM", "11:00", "12:00", 3),
            ("12PM", "12:00", "13:00", 4),
            ("1PM", "13:00", "14:00", 5),
            ("2PM", "14:00", "15:00", 6),
            ("3PM", "15:00", "16:00", 7),
            ("4PM", "16:00", "17:00", 8),
            ("5PM", "17:00", "18:00", 9),
        ]
        for slot_id, start_t, end_t, s_idx in slots:
            cur.execute(
                "INSERT OR IGNORE INTO time_slots (slot_id, start_time, end_time, slot_index) VALUES (?, ?, ?, ?)",
                (slot_id, start_t, end_t, s_idx),
            )

        # 3. Teachers (Allow both short and full names for flexible DSL parsing)
        teachers = [
            ("Ahmed", "Dr. Ahmed Khan", "ahmed.khan@iba.edu.pk", "Computer Science"),
            ("Sara", "Dr. Sara Malik", "sara.malik@iba.edu.pk", "Computer Science"),
            ("Bilal", "Dr. Bilal Hussain", "bilal.hussain@iba.edu.pk", "Computer Science"),
            ("Ayesha", "Dr. Ayesha Raza", "ayesha.raza@iba.edu.pk", "Mathematics"),
            ("Kamran", "Dr. Kamran Ali", "kamran.ali@iba.edu.pk", "Computer Science"),
            ("Nadia", "Dr. Nadia Sheikh", "nadia.sheikh@iba.edu.pk", "Social Sciences"),
            ("Usman", "Dr. Usman Tariq", "usman.tariq@iba.edu.pk", "Management"),
            ("Hira", "Dr. Hira Baig", "hira.baig@iba.edu.pk", "Natural Sciences"),
        ]
        for short_name, full_name, email, dept in teachers:
            cur.execute(
                """
                INSERT OR REPLACE INTO teachers (teacher_id, name, email, department)
                VALUES (?, ?, ?, ?)
                """,
                (short_name, short_name, email, dept),
            )

        # 4. Rooms (Classrooms, Lecture Halls, and Computer Labs)
        rooms = [
            ("CR1", "Classroom 1", 50, "LECTURE"),
            ("CR2", "Classroom 2", 50, "LECTURE"),
            ("CR3", "Classroom 3", 40, "LECTURE"),
            ("LH1", "Lecture Hall 1", 120, "AUDITORIUM"),
            ("LH2", "Lecture Hall 2", 80, "AUDITORIUM"),
            ("Lab1", "Computing Lab 1", 45, "LAB"),
            ("Lab2", "Software Engineering Lab", 45, "LAB"),
            ("Sem1", "Seminar Room 1", 30, "SEMINAR"),
        ]
        for r_id, r_name, cap, r_type in rooms:
            cur.execute(
                """
                INSERT OR REPLACE INTO rooms (room_id, name, room_name, capacity, room_type)
                VALUES (?, ?, ?, ?, ?)
                """,
                (r_id, r_name, r_name, cap, r_type),
            )

        # 5. Courses
        courses = [
            ("CS101", "Intro to Programming", "Computer Science", 3, "Ahmed", "CR1", 1, 40, 3),
            ("CS201", "Data Structures", "Computer Science", 3, "Ahmed", "CR2", 1, 40, 3),
            ("CS301", "Algorithms Design", "Computer Science", 3, "Sara", "CR1", 1, 35, 3),
            ("CS401", "Database Systems", "Computer Science", 3, "Sara", "Lab1", 1, 40, 2),
            ("CS501", "Software Engineering", "Computer Science", 3, "Bilal", "CR3", 1, 35, 2),
            ("CS601", "Artificial Intelligence", "Computer Science", 3, "Bilal", "Lab2", 1, 30, 2),
            ("MATH101", "Calculus & Analytical Geometry", "Mathematics", 3, "Ayesha", "LH1", 1, 50, 3),
            ("ENG101", "Functional English", "Social Sciences", 2, "Nadia", "CR2", 1, 40, 2),
            ("BUS101", "Business Communications", "Management", 2, "Usman", "LH2", 1, 45, 2),
            ("PHY101", "Applied Physics", "Natural Sciences", 3, "Hira", "LH1", 1, 40, 3),
        ]
        for c_id, c_name, dept, cr, t_id, r_id, dur, stu, dpw in courses:
            cur.execute(
                """
                INSERT OR REPLACE INTO courses 
                (course_id, name, course_name, department, credit_hours, teacher_id, room_id, duration_hours, students_count, days_per_week)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (c_id, c_name, c_name, dept, cr, t_id, r_id, dur, stu, dpw),
            )

        # 6. Student Groups
        groups = [
            ("CS-1A", "BSCS Freshman Section A", 40, "Computer Science"),
            ("CS-2A", "BSCS Sophomore Section A", 40, "Computer Science"),
            ("CS-3A", "BSCS Junior Section A", 35, "Computer Science"),
            ("CS-4A", "BSCS Senior Section A", 35, "Computer Science"),
            ("MATH-1A", "BS Math Freshman", 35, "Mathematics"),
            ("BBA-1A", "BBA Section A", 45, "Management"),
        ]
        for g_id, g_name, sz, dept in groups:
            cur.execute(
                """
                INSERT OR REPLACE INTO student_groups (group_id, name, size, department)
                VALUES (?, ?, ?, ?)
                """,
                (g_id, g_name, sz, dept),
            )

        conn.commit()


if __name__ == "__main__":
    db_mgr = DatabaseManager()
    seed_database(db_mgr)
    print("Database successfully seeded.")
