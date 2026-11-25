"""
tests/test_lexer.py
===================
Unit tests for the Lexer (Phase 1) using Python's standard unittest.
"""

import unittest
from compiler.lexer import Lexer, LexicalError, Token


class TestLexer(unittest.TestCase):
    def setUp(self):
        self.lexer = Lexer()

    def test_global_clash_rules(self):
        source = "RULE NO_ROOM_CLASH;\nRULE NO_TEACHER_CLASH;"
        tokens = self.lexer.tokenize(source)
        self.assertTrue(len(tokens) > 0)
        types = [t.type for t in tokens if t.type not in ("NEWLINE", "_SEMICOLON", "SEMICOLON")]
        self.assertIn("KEYWORD", types)

    def test_teacher_not_available(self):
        source = "RULE Ahmed NOT_AVAILABLE Monday 9AM;"
        tokens = self.lexer.tokenize(source)
        values = [t.value for t in tokens]
        self.assertIn("Ahmed", values)
        self.assertIn("NOT_AVAILABLE", values)
        self.assertIn("Monday", values)
        self.assertIn("9AM", values)

    def test_course_room_assignment(self):
        source = "RULE CS101 ROOM CR1;"
        tokens = self.lexer.tokenize(source)
        values = [t.value for t in tokens]
        self.assertIn("CS101", values)
        self.assertIn("ROOM", values)
        self.assertIn("CR1", values)

    def test_course_duration_tokenization(self):
        source = "RULE CS101 DURATION 2HOUR;"
        tokens = self.lexer.tokenize(source)
        values = [t.value for t in tokens]
        self.assertTrue("2HOUR" in values or ("2" in values and "HOUR" in values))

    def test_invalid_character_token_raises_error(self):
        source = "RULE CS101 ROOM @InvalidRoom;"
        with self.assertRaises(LexicalError):
            self.lexer.tokenize(source)

    def test_token_line_tracking(self):
        source = "\n\nRULE CS101 ROOM CR1;"
        tokens = self.lexer.tokenize(source)
        rule_tok = [t for t in tokens if t.value == "RULE"][0]
        self.assertEqual(rule_tok.line, 3)

    def test_empty_source(self):
        tokens = self.lexer.tokenize("")
        # Empty source may contain only EOF/NEWLINE or be empty
        meaningful = [t for t in tokens if t.type != "NEWLINE"]
        self.assertEqual(len(meaningful), 0)


if __name__ == "__main__":
    unittest.main()
