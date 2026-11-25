"""
database package
================
Database layer for the Smart University Timetable Constraint Compiler.
"""

from database.models import DatabaseManager
from database.seed_data import seed_database

__all__ = ["DatabaseManager", "seed_database"]
