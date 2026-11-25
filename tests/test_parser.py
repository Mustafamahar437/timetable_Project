"""
tests/test_parser.py
====================
Unit tests for the Parser (Phase 2) using standard unittest.
"""

import unittest
from compiler.parser import Parser


class TestParser(unittest.TestCase):
    def setUp(self):
        self.parser = Parser()

    def test_valid_global_invariants(self):
        source = "RULE NO_ROOM_CLASH;\nRULE NO_TEACHER_CLASH;"
        res = self.parser.parse(source)
        self.assertTrue(res.success)
        self.assertIsNotNone(res.tree)
        self.assertEqual(len(res.errors), 0)

    def test_valid_teacher_unavailability(self):
        source = "RULE Ahmed NOT_AVAILABLE Monday 9AM;"
        res = self.parser.parse(source)
        self.assertTrue(res.success)
        self.assertIsNotNone(res.tree)

    def test_valid_course_specifications(self):
        source = """
        RULE CS101 ROOM CR1;
        RULE CS101 TEACHER Ahmed;
        RULE CS101 DURATION 1HOUR;
        RULE CS101 STUDENTS 40;
        RULE CS101 DAYS_PER_WEEK 3;
        RULE CR1 CAPACITY 50;
        """
        res = self.parser.parse(source)
        self.assertTrue(res.success)
        self.assertEqual(len(res.errors), 0)

    def test_missing_semicolon_detected(self):
        source = "RULE NO_ROOM_CLASH"  # Missing semicolon
        res = self.parser.parse(source)
        self.assertFalse(res.success)
        self.assertTrue(len(res.errors) > 0)

    def test_inverted_rule_order_detected(self):
        source = "RULE TEACHER Ahmed CS101;"  # Invalid grammar production
        res = self.parser.parse(source)
        self.assertFalse(res.success)
        self.assertTrue(len(res.errors) > 0)

    def test_tree_formatting(self):
        source = "RULE CS101 ROOM CR1;"
        res = self.parser.parse(source)
        pretty = self.parser.format_tree_pretty(res.tree)
        self.assertIn("course_room", pretty)


if __name__ == "__main__":
    unittest.main()
