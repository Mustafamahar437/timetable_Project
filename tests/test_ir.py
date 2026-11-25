"""
tests/test_ir.py
================
Unit tests for the IR Generator (Phase 4).
"""

import json
import unittest
from compiler.parser import Parser
from compiler.ir_generator import IRGenerator


class TestIRGenerator(unittest.TestCase):
    def setUp(self):
        self.parser = Parser()
        self.ir_gen = IRGenerator()

    def test_global_constraint_ir(self):
        source = "RULE NO_ROOM_CLASH;\nRULE NO_TEACHER_CLASH;"
        p_res = self.parser.parse(source)
        ir_res = self.ir_gen.generate(p_res.tree)
        self.assertEqual(len(ir_res.instructions), 2)
        types = [i.type for i in ir_res.instructions]
        self.assertEqual(types, ["GLOBAL_CONSTRAINT", "GLOBAL_CONSTRAINT"])

    def test_teacher_unavailable_ir(self):
        source = "RULE Ahmed NOT_AVAILABLE Monday 9AM;"
        p_res = self.parser.parse(source)
        ir_res = self.ir_gen.generate(p_res.tree)
        instr = ir_res.instructions[0]
        self.assertEqual(instr.type, "TEACHER_UNAVAILABLE")
        self.assertEqual(instr.params.get("teacher"), "Ahmed")
        self.assertEqual(instr.params.get("day"), "Monday")
        self.assertEqual(instr.params.get("time"), "9AM")

    def test_course_room_ir(self):
        source = "RULE CS101 ROOM CR1;"
        p_res = self.parser.parse(source)
        ir_res = self.ir_gen.generate(p_res.tree)
        instr = ir_res.instructions[0]
        self.assertEqual(instr.type, "COURSE_ROOM")
        self.assertEqual(instr.params.get("course"), "CS101")
        self.assertEqual(instr.params.get("room"), "CR1")

    def test_json_serialization(self):
        source = "RULE CS101 DURATION 2HOUR;"
        p_res = self.parser.parse(source)
        ir_res = self.ir_gen.generate(p_res.tree)
        # Verify JSON parses cleanly
        data = json.loads(ir_res.json_repr)
        self.assertIsInstance(data, list)
        self.assertEqual(data[0]["type"], "COURSE_DURATION")


if __name__ == "__main__":
    unittest.main()
