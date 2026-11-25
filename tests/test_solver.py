"""
tests/test_solver.py
====================
Unit tests for Code Generator (Phase 5) and CP-SAT Solver (Phase 6).
"""

import unittest
from database.models import DatabaseManager
from database.seed_data import seed_database
from compiler.parser import Parser
from compiler.ir_generator import IRGenerator
from compiler.code_generator import CodeGenerator
from compiler.solver import TimetableSolver


class TestSolver(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseManager(":memory:")
        cls.db.initialize_db()
        seed_database(cls.db)
        cls.parser = Parser()
        cls.ir_gen = IRGenerator()
        cls.code_gen = CodeGenerator()
        cls.solver = TimetableSolver()

    def test_feasible_timetable_generation(self):
        source = """
        RULE NO_ROOM_CLASH;
        RULE NO_TEACHER_CLASH;
        RULE CS101 ROOM CR1;
        RULE CS101 TEACHER Ahmed;
        RULE CS101 DAYS_PER_WEEK 2;
        RULE CS201 ROOM CR2;
        RULE CS201 TEACHER Ahmed;
        RULE CS201 DAYS_PER_WEEK 2;
        RULE Ahmed NOT_AVAILABLE Monday 9AM;
        """
        p_res = self.parser.parse(source)
        ir_res = self.ir_gen.generate(p_res.tree)
        with self.db.get_connection() as conn:
            cs = self.code_gen.generate_constraints(ir_res.instructions, conn)
            solver_res = self.solver.solve(cs, conn)

        self.assertTrue(solver_res.success)
        self.assertIn(solver_res.status, ("OPTIMAL", "FEASIBLE"))
        self.assertTrue(len(solver_res.timetable) > 0)

        # Verify hard constraint: Ahmed is NOT scheduled Monday 9AM
        for entry in solver_res.timetable:
            if entry.teacher_name == "Ahmed":
                self.assertFalse(entry.day == "Monday" and entry.time_slot == "9AM")

    def test_no_room_double_booking(self):
        source = """
        RULE NO_ROOM_CLASH;
        RULE CS101 ROOM CR1;
        RULE CS201 ROOM CR1;
        RULE CS101 DAYS_PER_WEEK 2;
        RULE CS201 DAYS_PER_WEEK 2;
        """
        p_res = self.parser.parse(source)
        ir_res = self.ir_gen.generate(p_res.tree)
        with self.db.get_connection() as conn:
            cs = self.code_gen.generate_constraints(ir_res.instructions, conn)
            solver_res = self.solver.solve(cs, conn)

        self.assertTrue(solver_res.success)
        # Verify no two entries share (day, time_slot, room_id)
        room_slots = set()
        for e in solver_res.timetable:
            key = (e.day, e.time_slot, e.room_id)
            self.assertNotIn(key, room_slots)
            room_slots.add(key)


if __name__ == "__main__":
    unittest.main()
