"""
verify_compiler.py
==================
End-to-End Command-Line Verification Script.
Executes all 7 compiler phases on sample_rules/valid_rules.tcs
and verifies timetable generation.
"""

import sys
import os

from database.models import DatabaseManager
from database.seed_data import seed_database
from compiler.lexer import Lexer
from compiler.parser import Parser
from compiler.semantic import SemanticAnalyzer
from compiler.ir_generator import IRGenerator
from compiler.code_generator import CodeGenerator
from compiler.solver import TimetableSolver
from compiler.error_reporter import ErrorReporter


def run_verification():
    print("=================================================================")
    print(" Smart University Timetable Constraint Compiler - Verification  ")
    print("=================================================================")

    # 1. Database Setup
    print("\n[DB] Initializing and Seeding SQLite Database...")
    db_mgr = DatabaseManager("timetable.db")
    db_mgr.initialize_db()
    seed_database(db_mgr)
    print("  -> Database initialized with Faculty, Courses, and Rooms.")

    # 2. Load Sample Rules
    rule_file = "sample_rules/valid_rules.tcs"
    if not os.path.exists(rule_file):
        print(f"ERROR: {rule_file} not found.")
        return False

    with open(rule_file, "r", encoding="utf-8") as f:
        source = f.read()

    print(f"\n[Source] Loaded {len(source.splitlines())} lines from {rule_file}.")

    # 3. Phase 1: Lexical Analysis
    print("\n[Phase 1: Lexer] Tokenizing input...")
    lexer = Lexer()
    tokens = lexer.tokenize(source)
    print(f"  -> Generated {len(tokens)} tokens.")

    # 4. Phase 2: Syntax Analysis
    print("\n[Phase 2: Parser] Parsing Concrete Syntax Tree...")
    parser = Parser()
    p_res = parser.parse(source)
    if not p_res.success:
        print("  -> PARSE FAILED!")
        for err in p_res.errors:
            print(f"     Line {err.line}: {err.message}")
        return False
    print("  -> Parse Tree successfully constructed.")

    # 5. Phase 3: Semantic Analysis
    print("\n[Phase 3: Semantic] Validating entities against database...")
    analyzer = SemanticAnalyzer()
    with db_mgr.get_connection() as conn:
        sem_res = analyzer.analyze(p_res.tree, conn)

    if not sem_res.valid:
        print("  -> SEMANTIC VALIDATION FAILED!")
        for err in sem_res.errors:
            print(f"     Line {err.line}: {err.message}")
        return False
    print(f"  -> Semantic check PASSED! ({len(sem_res.errors)} errors, {len(sem_res.warnings)} warnings)")

    # 6. Phase 4: Intermediate Representation
    print("\n[Phase 4: IR Gen] Emitting target-independent IR...")
    ir_gen = IRGenerator()
    ir_res = ir_gen.generate(p_res.tree)
    print(f"  -> Emitted {len(ir_res.instructions)} IR instructions.")

    # 7. Phase 5: Code Generation
    print("\n[Phase 5: Code Gen] Translating IR to Solver Constraints...")
    code_gen = CodeGenerator()
    with db_mgr.get_connection() as conn:
        cs = code_gen.generate_constraints(ir_res.instructions, conn)

    print(f"  -> Hard Constraints: {len(cs.hard_constraints)}")
    print(f"  -> Soft Constraints: {len(cs.soft_constraints)}")

    # 8. Phase 6: Constraint Satisfaction Solver
    print("\n[Phase 6: Solver] Solving CP-SAT model using Google OR-Tools...")
    solver = TimetableSolver()
    with db_mgr.get_connection() as conn:
        solver_res = solver.solve(cs, conn)

    print(f"  -> Solver Status: {solver_res.status}")
    print(f"  -> Solve Time:    {solver_res.solve_time:.3f} seconds")
    print(f"  -> Objective:     {solver_res.objective_value}")
    print(f"  -> Sessions:      {len(solver_res.timetable)} scheduled")

    if solver_res.success:
        print("\n=================================================================")
        print(" FINAL TIMETABLE PREVIEW (First 8 Scheduled Sessions)           ")
        print("=================================================================")
        print(f"{'Day':<12} {'Time':<8} {'Course':<10} {'Room':<8} {'Faculty':<15}")
        print("-" * 55)
        for entry in solver_res.timetable[:8]:
            print(f"{entry.day:<12} {entry.time_slot:<8} {entry.course_id:<10} {entry.room_id:<8} {entry.teacher_name:<15}")
        print("...")
        print("\nALL COMPILER PHASES AND CP-SAT SOLVER VERIFIED SUCCESSFULLY!")
        return True
    else:
        print(f"SOLVER FAILED: {solver_res.message}")
        return False


if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)
