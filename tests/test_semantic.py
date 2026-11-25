"""
tests/test_semantic.py
======================
Unit tests for the Semantic Analyzer (Phase 3).
"""

import unittest
from database.models import DatabaseManager
from database.seed_data import seed_database
from compiler.parser import Parser
from compiler.semantic import SemanticAnalyzer


class TestSemanticAnalyzer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseManager(":memory:")
        cls.db.initialize_db()
        seed_database(cls.db)
        cls.parser = Parser()
        cls.analyzer = SemanticAnalyzer()

    def test_valid_rule_set_passes(self):
        source = """
        RULE NO_ROOM_CLASH;
        RULE CS101 ROOM CR1;
        RULE CS101 TEACHER Ahmed;
        RULE Ahmed NOT_AVAILABLE Monday 9AM;
        """
        parse_res = self.parser.parse(source)
        with self.db.get_connection() as conn:
            sem_res = self.analyzer.analyze(parse_res.tree, conn)
        self.assertTrue(sem_res.valid)
        self.assertEqual(len(sem_res.errors), 0)

    def test_nonexistent_teacher_detected(self):
        source = "RULE UnknownProfessor NOT_AVAILABLE Monday 9AM;"
        parse_res = self.parser.parse(source)
        with self.db.get_connection() as conn:
            sem_res = self.analyzer.analyze(parse_res.tree, conn)
        self.assertFalse(sem_res.valid)
        error_msgs = [e.message for e in sem_res.errors]
        self.assertTrue(any("UnknownProfessor" in m for m in error_msgs))

    def test_nonexistent_course_detected(self):
        source = "RULE CS999 ROOM CR1;"
        parse_res = self.parser.parse(source)
        with self.db.get_connection() as conn:
            sem_res = self.analyzer.analyze(parse_res.tree, conn)
        self.assertFalse(sem_res.valid)
        error_msgs = [e.message for e in sem_res.errors]
        self.assertTrue(any("CS999" in m for m in error_msgs))

    def test_nonexistent_room_detected(self):
        source = "RULE CS101 ROOM FakeRoom99;"
        parse_res = self.parser.parse(source)
        with self.db.get_connection() as conn:
            sem_res = self.analyzer.analyze(parse_res.tree, conn)
        self.assertFalse(sem_res.valid)
        error_msgs = [e.message for e in sem_res.errors]
        self.assertTrue(any("FakeRoom99" in m for m in error_msgs))

    def test_capacity_overflow_detected(self):
        source = """
        RULE CS101 ROOM Sem1;
        RULE CS101 STUDENTS 60;
        RULE Sem1 CAPACITY 30;
        """
        parse_res = self.parser.parse(source)
        with self.db.get_connection() as conn:
            sem_res = self.analyzer.analyze(parse_res.tree, conn)
        self.assertFalse(sem_res.valid)
        error_msgs = [e.message for e in sem_res.errors]
        self.assertTrue(any("capacity" in m.lower() for m in error_msgs))


if __name__ == "__main__":
    unittest.main()
