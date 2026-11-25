# 🎓 Smart University Timetable Constraint Compiler

A complete, production-grade **Compiler Construction Semester Project** implementing a Domain-Specific Language (DSL) called **Timetable Constraint Script (TCS)** for intelligent university timetable scheduling.

The system processes administrative scheduling policies through a formal 7-phase compiler architecture, validates semantic database integrity, translates rules into intermediate representation (IR), emits mathematical constraints, and solves for an optimal clash-free timetable using **Google OR-Tools CP-SAT**.

---

## 🌟 Key Features

- **Domain-Specific Language (TCS)**: Simple, declarative grammar to declare timetable invariants, room assignments, faculty availability, and course parameters.
- **True 7-Phase Compiler Architecture**:
  1. **Lexical Analysis (Scanning)**: Lark-based tokenization with precise position tracking (line and column) and comprehensive token error detection.
  2. **Syntax Analysis (Parsing)**: Context-Free Grammar (CFG) defined in EBNF, generating Concrete Syntax Trees (CST).
  3. **Semantic Analysis**: Symbol table validation against SQLite database, capacity feasibility checks, and contradiction detection.
  4. **Intermediate Representation (IR)**: Architecture-neutral JSON instructions decoupling language syntax from solver back-ends.
  5. **Constraint Code Generation**: Emits structured Hard Feasibility Invariants and Soft Preference Objectives.
  6. **Constraint Satisfaction Solver**: Google OR-Tools CP-SAT engine for optimal clash-free schedule generation.
  7. **Diagnostic Engine & Error Reporter**: Uniform diagnostics across all phases with actionable suggestions.
- **Modern Interactive Dashboard**: Built with Streamlit, featuring live code editing, token tables, parse tree viewers, IR inspectors, and weekly master grids.
- **Export Capabilities**: Export schedules as CSV spreadsheets or printable PDF timetables.
- **Realistic Dataset**: Pre-seeded with university data (Faculty, Courses, Classrooms, Labs, Student Groups, Time Slots).

---

## 🏗️ Project Architecture & Structure

```
Project/
├── compiler/
│   ├── __init__.py
│   ├── lexer.py          # Phase 1: Lexical Analysis (Lark token stream)
│   ├── parser.py         # Phase 2: Syntax Analysis (Lark EBNF grammar & CST)
│   ├── semantic.py       # Phase 3: Semantic Analysis (Symbol tables & DB integrity)
│   ├── ir_generator.py   # Phase 4: Intermediate Representation Generator (JSON)
│   ├── code_generator.py # Phase 5: OR-Tools constraint specification
│   ├── solver.py         # Phase 6: Google OR-Tools CP-SAT Solver
│   └── error_reporter.py # Phase 7: Uniform error diagnostic engine
├── database/
│   ├── __init__.py
│   ├── models.py         # SQLite schema & DatabaseManager API
│   └── seed_data.py      # University seed dataset
├── ui/
│   ├── __init__.py
│   ├── dashboard.py      # System overview & metrics
│   └── pages/
│       ├── __init__.py
│       ├── data_management.py   # Faculty, Course, and Room CRUD
│       ├── rule_editor.py       # TCS script editor & pipeline trigger
│       ├── lexical_view.py      # Token stream table & distribution chart
│       ├── syntax_view.py       # Parse tree visualization & EBNF grammar
│       ├── semantic_view.py     # Semantic verification diagnostics
│       ├── ir_view.py           # Structured IR instructions & JSON code
│       ├── constraints_view.py  # Hard & soft mathematical constraints
│       ├── timetable_view.py    # Weekly timetable grid & PDF/CSV export
│       └── error_view.py        # Diagnostic reports & fix suggestions
├── tests/
│   ├── __init__.py
│   ├── test_lexer.py     # Scanner unit tests
│   ├── test_parser.py    # Parser unit tests
│   ├── test_semantic.py  # Semantic analysis unit tests
│   ├── test_ir.py        # IR generator unit tests
│   └── test_solver.py    # CP-SAT constraint solver unit tests
├── sample_rules/
│   ├── valid_rules.tcs       # Clash-free benchmark script
│   ├── invalid_tokens.tcs    # Lexical error demonstration
│   ├── syntax_errors.tcs     # Syntax error demonstration
│   └── semantic_errors.tcs   # Semantic conflict demonstration
├── docs/
│   └── project_documentation.md  # Comprehensive 3500+ word academic document
├── app.py                # Main Streamlit application entry point
├── requirements.txt      # Project dependencies
└── README.md             # Project documentation & run guide
```

---

## 💻 Technology Stack

| Component | Technology | Role |
|-----------|------------|------|
| Language | Python 3.10+ | Core language |
| Front-end Parsing | Lark | EBNF Grammar, Scanning & Parsing |
| Constraint Solver | Google OR-Tools | CP-SAT mathematical optimization |
| User Interface | Streamlit | Web dashboard & pipeline controls |
| Data Persistence | SQLite 3 | Relational database for university entities |
| Data Processing | Pandas | Pivot tables, grid views, and tabular formatting |
| PDF Export | FPDF2 | Generating formatted PDF schedules |
| Visualizations | Plotly | Interactive token distribution charts |

---

## 🚀 Installation & Setup

### 1. Prerequisites
Ensure Python 3.10 or higher is installed on your system.

### 2. Install Dependencies
Open PowerShell or your preferred terminal in the project directory:
```bash
pip install -r requirements.txt
```

### 3. Initialize University Database
Run the seed script to create and populate `timetable.db`:
```bash
python -c "from database.models import DatabaseManager; from database.seed_data import seed_database; db = DatabaseManager(); db.initialize_db(); seed_database(db); print('Database initialized!')"
```

### 4. Launch the Web Application
```bash
streamlit run app.py
```
The browser will automatically open to `http://localhost:8501`.

---

## 🧪 Running Unit Tests

Run the full automated test suite using `unittest`:
```bash
python -m unittest discover tests -v
```

---

## 📝 TCS Language Quick Reference

| Rule Syntax | Description | Example |
|-------------|-------------|---------|
| `RULE NO_ROOM_CLASH;` | Global invariant: no room double-booking | `RULE NO_ROOM_CLASH;` |
| `RULE NO_TEACHER_CLASH;` | Global invariant: no teacher double-booking | `RULE NO_TEACHER_CLASH;` |
| `RULE <teacher> NOT_AVAILABLE <day> <time>;` | Teacher unavailability block | `RULE Ahmed NOT_AVAILABLE Monday 9AM;` |
| `RULE <course> ROOM <room>;` | Pinned room assignment | `RULE CS101 ROOM CR1;` |
| `RULE <course> TEACHER <teacher>;` | Course instructor assignment | `RULE CS101 TEACHER Ahmed;` |
| `RULE <course> DURATION <n>HOUR;` | Session duration (1-3 hours) | `RULE CS101 DURATION 1HOUR;` |
| `RULE <course> STUDENTS <n>;` | Course enrolment count | `RULE CS101 STUDENTS 40;` |
| `RULE <course> DAYS_PER_WEEK <n>;` | Required weekly sessions | `RULE CS101 DAYS_PER_WEEK 3;` |
| `RULE <room> CAPACITY <n>;` | Room seating capacity | `RULE CR1 CAPACITY 50;` |
| `RULE <course> PREFERRED_TIME <time>;` | Soft preference: start time | `RULE CS101 PREFERRED_TIME 9AM;` |
| `RULE <course> PREFERRED_DAY <day>;` | Soft preference: day | `RULE CS101 PREFERRED_DAY Monday;` |
