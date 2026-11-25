"""
compiler package
================
Smart University Timetable Constraint Compiler
Provides all 7 compiler phases:
  Phase 1: Lexical Analysis (lexer.py)
  Phase 2: Syntax Analysis (parser.py)
  Phase 3: Semantic Analysis (semantic.py)
  Phase 4: Intermediate Representation (ir_generator.py)
  Phase 5: Code Generation (code_generator.py)
  Phase 6: Constraint Satisfaction Solver (solver.py)
  Phase 7: Diagnostic Reporting (error_reporter.py)
"""

from compiler.lexer import Lexer, LexicalError, Token
from compiler.parser import Parser, ParseResult
from compiler.semantic import SemanticAnalyzer, SemanticResult, SemanticError
from compiler.ir_generator import IRGenerator, IRResult, IRInstruction
from compiler.code_generator import CodeGenerator, ConstraintSet
from compiler.solver import TimetableSolver, SolverResult, TimetableEntry
from compiler.error_reporter import ErrorReporter

__all__ = [
    "Lexer",
    "LexicalError",
    "Token",
    "Parser",
    "ParseResult",
    "SemanticAnalyzer",
    "SemanticResult",
    "SemanticError",
    "IRGenerator",
    "IRResult",
    "IRInstruction",
    "CodeGenerator",
    "ConstraintSet",
    "TimetableSolver",
    "SolverResult",
    "TimetableEntry",
    "ErrorReporter",
]
