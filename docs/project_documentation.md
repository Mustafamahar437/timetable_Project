# Academic Project Documentation
# Smart University Timetable Constraint Compiler

**Course:** Compiler Construction (Semester 7)  
**Institution:** Institute of Business Administration (IBA)  
**Project Title:** Smart University Timetable Constraint Compiler  
**Language Specification:** Timetable Constraint Script (TCS) DSL  
**Implementation Stack:** Python 3, Lark (EBNF Parser), Google OR-Tools (CP-SAT), SQLite, Streamlit  

---

## Table of Contents
1. [Executive Summary & Introduction](#1-executive-summary--introduction)
2. [Problem Statement](#2-problem-statement)
3. [Project Objectives & Scope](#3-project-objectives--scope)
4. [Formal Language Design & Grammar](#4-formal-language-design--grammar)
5. [Compiler Architecture & Pipeline](#5-compiler-architecture--pipeline)
6. [Phase 1: Lexical Analysis (Scanning)](#6-phase-1-lexical-analysis-scanning)
7. [Phase 2: Syntax Analysis (Parsing)](#7-phase-2-syntax-analysis-parsing)
8. [Phase 3: Semantic Analysis (Type & Constraint Validation)](#8-phase-3-semantic-analysis-type--constraint-validation)
9. [Phase 4: Intermediate Representation (IR) Generation](#9-phase-4-intermediate-representation-ir-generation)
10. [Phase 5: Code Generation (Target Constraint Modeling)](#10-phase-5-code-generation-target-constraint-modeling)
11. [Phase 6: Constraint Satisfaction & Optimization (Solver)](#11-phase-6-constraint-satisfaction--optimization-solver)
12. [Phase 7: Diagnostic Engine & Error Recovery](#12-phase-7-diagnostic-engine--error-recovery)
13. [Verification & Test Methodology](#13-verification--test-methodology)
14. [Limitations & Future Enhancements](#14-limitations--future-enhancements)
15. [Conclusion & References](#15-conclusion--references)

---

## 1. Executive Summary & Introduction

University timetabling is an NP-hard combinatorial optimization problem characterized by competing resource demands, multidimensional physical constraints, and dynamic institutional policies. Traditional academic management software relies on inflexible graphical form wizards that fail to express complex, non-trivial administrative rules.

This project approaches university course timetabling from the rigorous perspective of **Compiler Construction**. Rather than treating scheduling as a manual database filtering task, we introduce **Timetable Constraint Script (TCS)**, a declarative Domain-Specific Language (DSL). Administrators express scheduling policies as high-level linguistic rules. The compiler transforms this code through seven classic compiler phases:
1. Lexical Analysis (Scanning)
2. Syntax Analysis (Context-Free Grammar Parsing)
3. Semantic Analysis (Symbol Table & Relational Consistency)
4. Intermediate Representation (Target-Independent IR)
5. Code Generation (Target Constraint Formulation)
6. Constraint Solving (Google OR-Tools CP-SAT Engine)
7. Diagnostic Error Reporting

The end deliverable is a functional compiler integrated with a modern interactive Streamlit dashboard, providing compile-time diagnostics, parse tree visualizers, token inspectors, and exportable weekly schedules in CSV and PDF formats.

---

## 2. Problem Statement

At modern tertiary institutions, timetable scheduling involves coordinating:
- $F$ faculty members with individual research commitments, pedagogical constraints, and availability windows.
- $C$ active courses requiring specific session frequencies, credit hour durations, and student cohort sizing.
- $R$ physical facilities (lecture halls, computing laboratories, seminar rooms) with strict seating capacities and specialized equipment.
- $T$ discrete weekly time slots across working days ($D$).

Manual or heuristic scheduling frequently results in:
1. **Teacher Clashes**: Faculty assigned to multiple concurrent lectures.
2. **Room Collisions**: Multiple courses allocated to the same physical venue at identical time slots.
3. **Capacity Overflow**: Enrolment exceeding physical room seating capacity, creating safety and pedagogical violations.
4. **Policy Inflexibility**: Inability to easily express institutional rules such as *"Dr. Ahmed is unavailable on Monday mornings"* or *"CS101 must be scheduled in Lab 1"*.

By treating these policies as code written in a formal DSL, administrative rules can be validated syntactically and semantically before entering a mathematical solver, ensuring provable clash-free correctness.

---

## 3. Project Objectives & Scope

### 3.1 Primary Objectives
- **Design a Formal DSL**: Construct a clean, expressive grammar for academic scheduling rules.
- **Implement a 7-Phase Compiler**: Construct distinct, decoupled modules reflecting classical compiler architecture principles.
- **Enforce Strict Semantic Invariants**: Verify symbol existence, type consistency, and relational integrity against a persistent SQLite database.
- **Emit Decoupled Intermediate Representation (IR)**: Decouple front-end language syntax from back-end constraint solvers.
- **Integrate CP-SAT Mathematical Optimization**: Translate IR into exact mathematical constraints using Google OR-Tools.
- **Deliver an Interactive Graphical Dashboard**: Build an administrator dashboard in Streamlit for editing scripts, inspecting compilation artifacts, and exporting timetables.

### 3.2 Scope & Boundaries
- **Temporal Domain**: Standard university working week (Monday through Friday), 1-hour time slots from 8:00 AM to 5:00 PM (10 slots/day, 50 slots/week).
- **Hard Constraints**: Non-negotiable physical constraints (zero room double-booking, zero teacher double-booking, room capacity $\ge$ students, teacher availability).
- **Soft Constraints**: Preferential optimization objectives (preferred start times, preferred days) penalized when violated.

---

## 4. Formal Language Design & Grammar

The **Timetable Constraint Script (TCS)** language is designed with clean, deterministic syntax. Every declaration begins with the keyword `RULE` and terminates with a semicolon (`;`).

### 4.1 Extended Backus-Naur Form (EBNF) Grammar

```ebnf
program         ::= statement* EOF
statement       ::= rule_decl ";"

rule_decl       ::= "RULE" ( global_rule 
                           | availability_rule 
                           | assignment_rule 
                           | property_rule 
                           | preference_rule )

global_rule     ::= "NO_ROOM_CLASH"
                  | "NO_TEACHER_CLASH"

availability_rule ::= IDENTIFIER "NOT_AVAILABLE" DAY TIME

assignment_rule ::= IDENTIFIER "ROOM" IDENTIFIER
                  | IDENTIFIER "TEACHER" IDENTIFIER

property_rule   ::= IDENTIFIER "DURATION" DURATION_VAL
                  | IDENTIFIER "STUDENTS" NUMBER
                  | IDENTIFIER "DAYS_PER_WEEK" NUMBER
                  | IDENTIFIER "CAPACITY" NUMBER
                  | IDENTIFIER "NO_CLASH"

preference_rule ::= IDENTIFIER "PREFERRED_TIME" TIME
                  | IDENTIFIER "PREFERRED_DAY" DAY

DAY             ::= "Monday" | "Tuesday" | "Wednesday" | "Thursday" | "Friday"
TIME            ::= "8AM" | "9AM" | "10AM" | "11AM" | "12PM" 
                  | "1PM" | "2PM" | "3PM" | "4PM" | "5PM"
DURATION_VAL    ::= NUMBER "HOUR"
IDENTIFIER      ::= [a-zA-Z_][a-zA-Z0-9_]*
NUMBER          ::= [0-9]+
```

---

## 5. Compiler Architecture & Pipeline

The system adheres strictly to the classic multi-pass compiler organization:

```
+-------------------------------------------------------+
|             Administrator Rule Script (.tcs)          |
+-------------------------------------------------------+
                           |
                           v
+-------------------------------------------------------+
|  Phase 1: Lexer (Token Stream & Position Tracking)    |
+-------------------------------------------------------+
                           | Tokens
                           v
+-------------------------------------------------------+
|  Phase 2: Parser (EBNF Concrete Syntax Tree)          |
+-------------------------------------------------------+
                           | CST / Parse Tree
                           v
+-------------------------------------------------------+
|  Phase 3: Semantic Analyzer (Symbol & DB Validation)  | <---> SQLite Database
+-------------------------------------------------------+
                           | Validated Tree
                           v
+-------------------------------------------------------+
|  Phase 4: IR Generator (Target-Neutral Instructions)  |
+-------------------------------------------------------+
                           | JSON IR Instructions
                           v
+-------------------------------------------------------+
|  Phase 5: Code Generator (Constraint Specification)   |
+-------------------------------------------------------+
                           | ConstraintSet (Hard + Soft)
                           v
+-------------------------------------------------------+
|  Phase 6: Solver (Google OR-Tools CP-SAT Engine)      |
+-------------------------------------------------------+
                           | Solution Matrix
                           v
+-------------------------------------------------------+
|  Output: University Timetable (Weekly Grid, CSV, PDF) |
+-------------------------------------------------------+
```

---

## 6. Phase 1: Lexical Analysis (Scanning)

The Lexical Analyzer transforms the raw ASCII source stream into typed `Token` objects.

### 6.1 Token Classes
- `KEYWORD`: `RULE`, `NOT_AVAILABLE`, `ROOM`, `TEACHER`, `DURATION`, `STUDENTS`, `DAYS_PER_WEEK`, `CAPACITY`, `NO_ROOM_CLASH`, `NO_TEACHER_CLASH`, `PREFERRED_TIME`, `PREFERRED_DAY`, `NO_CLASH`.
- `IDENTIFIER`: Entity references (`CS101`, `Ahmed`, `CR1`, `Lab1`).
- `NUMBER`: Integer literals (`40`, `50`, `3`).
- `DAY`: Enumerated days (`Monday` through `Friday`).
- `TIME`: Enumerated slots (`8AM` through `5PM`).
- `HOUR_SUFFIX`: Duration unit (`HOUR`).
- `SEMICOLON`: Statement terminator (`;`).

### 6.2 Lexical Error Detection
When the scanner encounters non-alphabetical symbols, invalid time formats, or malformed suffixes, it halts and reports a `LexicalError` containing:
- 1-based source `line` number
- 1-based source `column` number
- The exact offending line text snippet and caret locator (`^`).

---

## 7. Phase 2: Syntax Analysis (Parsing)

The Syntax Analyzer constructs a Concrete Syntax Tree (CST) by applying the Context-Free Grammar. We utilize Lark's robust Earley / LALR parser engine.

### 7.1 Parse Tree Representation
Each valid rule statement generates a structured subtree. For example, `RULE CS101 ROOM CR1;` yields:
```
statement
  rule_decl
    course_room
      Token(IDENTIFIER, 'CS101')
      Token(IDENTIFIER, 'CR1')
  Token(SEMICOLON, ';')
```

### 7.2 Syntax Error Diagnostics
If an administrator omits a semicolon, misplaces a keyword (`RULE TEACHER Ahmed CS101;`), or writes trailing tokens, the parser catches the error, generates human-readable diagnostics, and offers actionable syntax suggestions.

---

## 8. Phase 3: Semantic Analysis (Type & Constraint Validation)

Syntax analysis only verifies structural grammaticality; it cannot verify whether referenced entities actually exist or make physical sense. Semantic analysis enforces these rules by interrogating the university database.

### 8.1 Semantic Rules Enforced
1. **Teacher Existence**: Every teacher identifier in a `TEACHER` or `NOT_AVAILABLE` rule must match a valid entry in the `teachers` database table.
2. **Course Existence**: Every course identifier must exist in the `courses` catalog.
3. **Room Existence**: Every room identifier must exist in the `rooms` catalog.
4. **Capacity Feasibility**: If course $c$ is assigned to room $r$, then $\text{Capacity}(r) \ge \text{Students}(c)$.
5. **Duration Bounds**: Course session duration must fall within $[1, 3]$ hours.
6. **Days Per Week Bounds**: Weekly sessions must be within $[1, 5]$.
7. **Contradiction Detection**: Detects direct conflicts (e.g., pinning course $c$ to two distinct rooms in the same script).

---

## 9. Phase 4: Intermediate Representation (IR) Generation

The Intermediate Representation (IR) provides a target-independent, serialized representation of every constraint.

### 9.1 IR Instruction Types
```json
[
  { "type": "GLOBAL_CONSTRAINT", "constraint_name": "NO_ROOM_CLASH" },
  { "type": "TEACHER_UNAVAILABLE", "teacher": "Ahmed", "day": "Monday", "time": "9AM" },
  { "type": "COURSE_ROOM", "course": "CS101", "room": "CR1" },
  { "type": "COURSE_TEACHER", "course": "CS101", "teacher": "Ahmed" },
  { "type": "COURSE_DURATION", "course": "CS101", "hours": 1 },
  { "type": "COURSE_DAYS_PER_WEEK", "course": "CS101", "days": 3 },
  { "type": "ROOM_CAPACITY", "room": "CR1", "capacity": 50 },
  { "type": "COURSE_PREFERRED_TIME", "course": "CS101", "time": "9AM" }
]
```

### 9.2 Compiler Advantages of IR
- **Modular Portability**: The front-end parser can be altered or extended without modifying the constraint solver.
- **Optimization Passes**: Facilitates dead-rule elimination and constant folding before solver execution.
- **Standardized Export**: The IR can be persisted, transmitted over network APIs, or inspected in visual tooling.

---

## 10. Phase 5: Code Generation (Target Constraint Modeling)

The Code Generator translates the high-level IR instructions into concrete mathematical constraints partitioned into two explicit sets:
1. **Hard Constraints**: Must be satisfied strictly for a schedule to be feasible.
2. **Soft Constraints**: Associated with penalty weights minimized in the solver's objective function.

It also computes the complete decision variable domain bounds:
$$\text{Days} = \{0, 1, 2, 3, 4\}, \quad \text{TimeSlots} = \{0, 1, \dots, 9\}, \quad \text{Rooms} = \{0, \dots, |R|-1\}$$

---

## 11. Phase 6: Constraint Satisfaction & Optimization (Solver)

The back-end employs the **Google OR-Tools CP-SAT** constraint solver.

### 11.1 Mathematical Formulation

#### Decision Variables
For each course $c \in C$, session $s \in \{0, \dots, S_c - 1\}$, day $d \in D$, time slot $t \in T$, and room $r \in R$:
$$x_{c, s, d, t, r} \in \{0, 1\}$$
where $x_{c, s, d, t, r} = 1$ if session $s$ of course $c$ is scheduled at day $d$, time slot $t$, in room $r$.

#### 1. Exactly One Assignment per Session
Every required course session must be assigned to exactly one (day, slot, room) tuple:
$$\forall c \in C, \forall s \in \{0, \dots, S_c - 1\}: \sum_{d \in D} \sum_{t \in T} \sum_{r \in R} x_{c, s, d, t, r} = 1$$

#### 2. Spreading Across Days
A course cannot have multiple sessions on the same day:
$$\forall c \in C, \forall d \in D: \sum_{s=0}^{S_c - 1} \sum_{t \in T} \sum_{r \in R} x_{c, s, d, t, r} \le 1$$

#### 3. Room Clash Invariant (`NO_ROOM_CLASH`)
At most one course session can occupy a given room during any time slot:
$$\forall d \in D, \forall t \in T, \forall r \in R: \sum_{c \in C} \sum_{s=0}^{S_c - 1} x_{c, s, d, t, r} \le 1$$

#### 4. Teacher Clash Invariant (`NO_TEACHER_CLASH`)
Let $C(f) \subseteq C$ be the set of courses taught by faculty member $f$. A teacher can teach at most one session at any time:
$$\forall f \in F, \forall d \in D, \forall t \in T: \sum_{c \in C(f)} \sum_{s=0}^{S_c - 1} \sum_{r \in R} x_{c, s, d, t, r} \le 1$$

#### 5. Faculty Availability
If teacher $f$ is unavailable at day $d^*$ and time $t^*$:
$$\forall c \in C(f), \forall s \in \{0, \dots, S_c - 1\}, \forall r \in R: x_{c, s, d^*, t^*, r} = 0$$

#### 6. Objective Function (Soft Constraint Optimization)
Minimizes weighted penalty costs for violated soft preferences:
$$\min \sum_{c \in C} \left[ W_{\text{time}} \cdot (1 - \text{is\_preferred\_time}_c) + W_{\text{day}} \cdot (1 - \text{is\_preferred\_day}_c) \right]$$

---

## 12. Phase 7: Diagnostic Engine & Error Recovery

The Error Reporter standardizes diagnostics across all phases into a uniform schema:
- `phase`: Lexical, Syntax, Semantic, or Solver.
- `line` & `column`: Exact source code location.
- `message`: Clear technical explanation of the failure.
- `suggestion`: Actionable correction recommendation based on an internal diagnostic knowledge base.

If any compiler phase encounters a fatal error, the pipeline immediately stops and displays the diagnostic card, preventing the generation of an invalid schedule.

---

## 13. Verification & Test Methodology

The system is validated through comprehensive automated test suites covering:
- **Lexical Tests**: Valid token streams, boundary line/column calculations, rejection of illegal characters.
- **Parser Tests**: Grammar rule acceptance, detection of omitted semicolons, detection of invalid rule structures.
- **Semantic Tests**: Database entity lookups, detection of non-existent teachers/courses/rooms, capacity mismatch detection.
- **IR Generator Tests**: Field integrity, JSON serialization.
- **Solver Tests**: Verified generation of clash-free timetables under teacher unavailability and room constraints.

---

## 14. Limitations & Future Enhancements

### Limitations
- **Discrete Granularity**: Time is discretized into uniform 1-hour slots.
- **Single-Teacher Model**: Team-taught courses with multiple concurrent instructors are not currently supported.

### Future Enhancements
- **Multi-Room Laboratories**: Support for courses requiring linked lecture and laboratory sections.
- **Consecutive Session Blocks**: Explicit syntax for 2-hour or 3-hour continuous lab blocks (`BLOCK 3HOURS`).
- **Student Elective Collision Avoidance**: Advanced bipartite graph matching for elective course clashes.

---

## 15. Conclusion & References

The **Smart University Timetable Constraint Compiler** demonstrates that formal compiler construction principles—lexical tokenization, EBNF syntax analysis, semantic AST decoration, intermediate code generation, and constraint-based code compilation—provide an elegant, robust, and extensible solution to complex academic scheduling challenges.

### References
1. Aho, A. V., Lam, M. S., Sethi, R., & Ullman, J. D. (2006). *Compilers: Principles, Techniques, and Tools* (2nd ed.). Addison-Wesley.
2. Cooper, K. D., & Torczon, L. (2011). *Engineering a Compiler* (2nd ed.). Morgan Kaufmann.
3. Lark Parser Documentation. (2024). *Lark - a parsing toolkit for Python*. https://github.com/lark-parser/lark
4. Google OR-Tools Documentation. (2024). *CP-SAT Solver Reference*. Google Developers. https://developers.google.com/optimization/cp
