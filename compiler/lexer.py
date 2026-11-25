"""
compiler/lexer.py
=================
Lexer (Tokenizer) for the Smart University Timetable Constraint Compiler.

The DSL is called TCS (Timetable Constraint Script) and files use the `.tcs`
extension.  This module is the **first phase** of the classic compiler pipeline:

    Source Text  ->  [LEXER]  ->  Token Stream  ->  Parser  ->  ...

The lexer breaks raw source text into a flat list of meaningful *tokens*.  Each
token carries:
    - its *type*   (e.g. KEYWORD, IDENTIFIER, NUMBER, TIME, DAY …)
    - its *value*  (the exact matched text)
    - its *line*   (1-based line number in the source)
    - its *column* (1-based column number within the line)

We use the **Lark** library for the heavy lifting.  Lark's `contextual` lexer is
used here (via the `lalr` parser back-end) so that we get rich position info and
clean error messages.

Supported rule shapes
---------------------
    RULE NO_ROOM_CLASH ;
    RULE NO_TEACHER_CLASH ;
    RULE <teacher>  NOT_AVAILABLE <day> <time> ;
    RULE <course>   ROOM          <room_id>    ;
    RULE <course>   TEACHER       <teacher>    ;
    RULE <course>   DURATION      <n>HOUR      ;
    RULE <course>   STUDENTS      <n>          ;
    RULE <course>   DAYS_PER_WEEK <n>          ;
    RULE <room>     CAPACITY      <n>          ;
    RULE <course>   PREFERRED_TIME <time>      ;
    RULE <course>   PREFERRED_DAY  <day>       ;
    RULE <group>    NO_CLASH                   ;

Days  : Monday | Tuesday | Wednesday | Thursday | Friday
Times : 8AM | 9AM | 10AM | 11AM | 12PM | 1PM | 2PM | 3PM | 4PM | 5PM
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------

class LexicalError(Exception):
    """
    Raised when the lexer encounters a character sequence it cannot tokenize.

    Attributes
    ----------
    message : str
        Human-readable description of the problem.
    line : int
        1-based line number where the error was detected.
    column : int
        1-based column number where the error was detected.
    source_line : str
        The raw text of the offending line (for error display).
    """

    def __init__(
        self,
        message: str,
        line: int = 0,
        column: int = 0,
        source_line: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column
        self.source_line = source_line

    def __str__(self) -> str:
        location = f"line {self.line}, column {self.column}"
        snippet = f"\n  {self.source_line}\n  {' ' * (self.column - 1)}^" if self.source_line else ""
        return f"LexicalError at {location}: {self.message}{snippet}"

    def to_dict(self) -> dict:
        return {
            "phase": "Lexical Analysis",
            "line": self.line,
            "column": self.column,
            "message": self.message,
            "source_line": self.source_line,
        }


# ---------------------------------------------------------------------------
# Token dataclass
# ---------------------------------------------------------------------------

@dataclass
class Token:
    """
    A single lexical token produced by the Lexer.

    Fields
    ------
    type : str
        One of: KEYWORD, IDENTIFIER, NUMBER, TIME, DAY, HOUR_SUFFIX,
                SEMICOLON, NEWLINE, COMMENT.
    value : str
        The exact matched text from the source.
    line : int
        1-based line number.
    column : int
        1-based column number.
    """

    type: str
    value: str
    line: int
    column: int

    def to_dict(self) -> dict:
        """Return a JSON-serializable dictionary representation."""
        return {
            "type": self.type,
            "value": self.value,
            "line": self.line,
            "column": self.column,
        }

    def __repr__(self) -> str:
        return f"Token(type={self.type!r}, value={self.value!r}, line={self.line}, col={self.column})"


# ---------------------------------------------------------------------------
# Token-type constants
# ---------------------------------------------------------------------------

# All keyword strings recognised by the DSL (case-sensitive).
KEYWORDS: set[str] = {
    "RULE",
    "NOT_AVAILABLE",
    "ROOM",
    "TEACHER",
    "DURATION",
    "STUDENTS",
    "DAYS_PER_WEEK",
    "CAPACITY",
    "NO_ROOM_CLASH",
    "NO_TEACHER_CLASH",
    "PREFERRED_TIME",
    "PREFERRED_DAY",
    "NO_CLASH",
}

# Valid day names (case-sensitive).
DAYS: set[str] = {
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
}

# Valid time tokens (case-sensitive).
TIMES: set[str] = {
    "8AM",
    "9AM",
    "10AM",
    "11AM",
    "12PM",
    "1PM",
    "2PM",
    "3PM",
    "4PM",
    "5PM",
}

# ---------------------------------------------------------------------------
# Hand-written regex-based lexer (no Lark needed for token-stream phase)
# ---------------------------------------------------------------------------
# We implement a classic *maximal-munch* (longest-match) tokenizer using a
# single compiled regex with named groups.  This is simpler than standing up
# a full Lark grammar just for the tokenizer phase and avoids Lark version
# compatibility issues.
#
# Token recognition order (earlier groups have priority):
#   1. COMMENT         – # … to end of line  (skipped / stored as COMMENT)
#   2. NEWLINE         – \r\n or \n
#   3. WHITESPACE      – spaces / tabs  (skipped)
#   4. HOUR_SUFFIX     – the literal "HOUR" (must come before IDENTIFIER so
#                        that "3HOUR" in DURATION rules splits cleanly)
#   5. TIME            – e.g. 8AM, 12PM  (must come before NUMBER/IDENTIFIER)
#   6. NUMBER          – one or more decimal digits
#   7. SEMICOLON       – ;
#   8. WORD            – a "word" token: letters, digits, underscores
#                        (later classified as KEYWORD / DAY / IDENTIFIER)
#   9. UNKNOWN         – anything else  → triggers LexicalError

_TOKEN_PATTERN = re.compile(
    r"""
    (?P<COMMENT>  (?:\#|\/\/)[^\r\n]*    )   # single-line comment (# or //)
  | (?P<NEWLINE>  \r\n | \n              )   # line terminator
  | (?P<WS>       [ \t]+                 )   # whitespace (skip)
  | (?P<TIME>     (?:1[012]|[1-9])(?:AM|PM) )  # time  e.g. 8AM, 12PM
  | (?P<HOUR_SUFFIX> HOUR                )   # e.g. the HOUR in 3HOUR
  | (?P<NUMBER>   \d+                    )   # integer literal
  | (?P<SEMICOLON> ;                     )   # statement terminator
  | (?P<WORD>     [A-Za-z_][A-Za-z0-9_]* )  # keyword / day / identifier
  | (?P<UNKNOWN>  .                      )   # catch-all – lexical error
    """,
    re.VERBOSE,
)


# ---------------------------------------------------------------------------
# Lark grammar (kept as a string for documentation / future parser integration)
# ---------------------------------------------------------------------------

TCS_GRAMMAR = r"""
// ============================================================
// TCS (Timetable Constraint Script) Grammar  –  Lark EBNF
// Used by compiler/parser.py for full parse-tree construction.
// The lexer phase (this file) produces a token stream that the
// parser then validates against this grammar.
// ============================================================

start: statement+

statement: rule_stmt SEMICOLON

rule_stmt: RULE NO_ROOM_CLASH                                   -> global_no_room_clash
         | RULE NO_TEACHER_CLASH                                -> global_no_teacher_clash
         | RULE IDENTIFIER NOT_AVAILABLE DAY TIME               -> teacher_unavailable
         | RULE IDENTIFIER ROOM IDENTIFIER                      -> course_room
         | RULE IDENTIFIER TEACHER IDENTIFIER                   -> course_teacher
         | RULE IDENTIFIER DURATION NUMBER HOUR_SUFFIX          -> course_duration
         | RULE IDENTIFIER STUDENTS NUMBER                      -> course_students
         | RULE IDENTIFIER DAYS_PER_WEEK NUMBER                 -> course_days_per_week
         | RULE IDENTIFIER CAPACITY NUMBER                      -> room_capacity
         | RULE IDENTIFIER PREFERRED_TIME TIME                  -> course_preferred_time
         | RULE IDENTIFIER PREFERRED_DAY DAY                    -> course_preferred_day
         | RULE IDENTIFIER NO_CLASH                             -> group_no_clash

// ---- Terminals ----
RULE            : "RULE"
NOT_AVAILABLE   : "NOT_AVAILABLE"
ROOM            : "ROOM"
TEACHER         : "TEACHER"
DURATION        : "DURATION"
STUDENTS        : "STUDENTS"
DAYS_PER_WEEK   : "DAYS_PER_WEEK"
CAPACITY        : "CAPACITY"
NO_ROOM_CLASH   : "NO_ROOM_CLASH"
NO_TEACHER_CLASH: "NO_TEACHER_CLASH"
PREFERRED_TIME  : "PREFERRED_TIME"
PREFERRED_DAY   : "PREFERRED_DAY"
NO_CLASH        : "NO_CLASH"

DAY : "Monday" | "Tuesday" | "Wednesday" | "Thursday" | "Friday"

TIME : "8AM" | "9AM" | "10AM" | "11AM" | "12PM"
     | "1PM" | "2PM"  | "3PM"  | "4PM"  | "5PM"

HOUR_SUFFIX : "HOUR"

NUMBER      : /\d+/
IDENTIFIER  : /[A-Za-z_][A-Za-z0-9_]*/
SEMICOLON   : ";"

%ignore /[ \t\r\n]+/
%ignore /#[^\r\n]*/
"""


# ---------------------------------------------------------------------------
# Lexer class
# ---------------------------------------------------------------------------

class Lexer:
    """
    Tokenizer for the TCS (Timetable Constraint Script) DSL.

    Usage
    -----
    ::

        lexer = Lexer()
        tokens = lexer.tokenize(source_code)
        for tok in tokens:
            print(tok)

    The tokenizer uses a hand-written maximal-munch regex engine so that
    it can emit precise line/column information and meaningful error messages
    without depending on a full Lark parse pass.

    Token-type taxonomy
    -------------------
    KEYWORD
        Any of the reserved DSL words (RULE, ROOM, TEACHER, …).
    DAY
        A day-of-week name: Monday … Friday.
    TIME
        A time-of-day literal: 8AM … 5PM.
    HOUR_SUFFIX
        The word "HOUR" when it immediately follows a NUMBER in a DURATION
        rule.  Stored separately so the parser can validate ``<n>HOUR``.
    NUMBER
        A sequence of decimal digits.
    IDENTIFIER
        Any ``[A-Za-z_][A-Za-z0-9_]*`` word that is not a keyword, day, or
        HOUR_SUFFIX.
    SEMICOLON
        The ```;``` character that terminates each rule statement.
    NEWLINE
        A line break (``\\n`` or ``\\r\\n``).  Stored so that the parser can
        track line context; typically filtered out in the parser phase.
    COMMENT
        A ``#``-prefixed comment to end-of-line.  Stored for tooling (e.g.
        syntax highlighters) but ignored by the parser.
    """

    # Suggestions for common lexical mistakes
    _SUGGESTIONS: dict[str, str] = {
        "@": "Use '#' for comments, not '@'.",
        "!": "Unexpected '!'. Did you mean ';' to end a rule?",
        ":": "Unexpected ':'. TCS rules end with ';', not ':'.",
        "=": "Unexpected '='. TCS does not use '=' assignment syntax.",
        ".": "Unexpected '.'. Did you mean ';'?",
        ",": "Unexpected ','. TCS rule operands are space-separated.",
    }

    def __init__(self, keep_comments: bool = False, keep_newlines: bool = True) -> None:
        """
        Parameters
        ----------
        keep_comments : bool
            If ``True`` COMMENT tokens are included in the output list.
            Default ``False`` (comments are discarded).
        keep_newlines : bool
            If ``True`` NEWLINE tokens are included in the output list.
            Default ``True`` (useful for the parser to track positions).
        """
        self.keep_comments = keep_comments
        self.keep_newlines = keep_newlines

        # Accumulate all tokens & errors from the last tokenize() call
        self._tokens: List[Token] = []
        self._errors: List[LexicalError] = []
        self._source_lines: List[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def tokenize(self, source: str) -> List[Token]:
        """
        Lex *source* and return a list of :class:`Token` objects.

        Parameters
        ----------
        source : str
            The raw TCS source text.

        Returns
        -------
        List[Token]
            Ordered list of tokens.  NEWLINE and (optionally) COMMENT tokens
            are included according to the constructor flags.

        Raises
        ------
        LexicalError
            On the **first** unrecognised character.  Downstream callers that
            want to collect *all* errors should call
            :py:meth:`tokenize_recover` instead.
        """
        self._tokens = []
        self._errors = []
        self._source_lines = source.splitlines()

        line_num = 1
        line_start = 0  # byte offset of the current line's first character

        for match in _TOKEN_PATTERN.finditer(source):
            kind = match.lastgroup
            text = match.group()
            col = match.start() - line_start + 1  # 1-based

            # ---- skip whitespace ----
            if kind == "WS":
                continue

            # ---- handle NEWLINE ----
            if kind == "NEWLINE":
                if self.keep_newlines:
                    self._tokens.append(Token("NEWLINE", text, line_num, col))
                line_num += 1
                line_start = match.end()
                continue

            # ---- handle COMMENT ----
            if kind == "COMMENT":
                if self.keep_comments:
                    self._tokens.append(Token("COMMENT", text, line_num, col))
                continue

            # ---- handle UNKNOWN (lexical error) ----
            if kind == "UNKNOWN":
                src_line = self._source_lines[line_num - 1] if line_num <= len(self._source_lines) else ""
                suggestion = self._SUGGESTIONS.get(text, f"Remove or replace the unexpected character '{text}'.")
                err = LexicalError(
                    f"Unexpected character '{text}'. {suggestion}",
                    line=line_num,
                    column=col,
                    source_line=src_line,
                )
                self._errors.append(err)
                raise err  # stop on first error (use tokenize_recover for all)

            # ---- classify WORD tokens ----
            if kind == "WORD":
                tok_type = self._classify_word(text)
                self._tokens.append(Token(tok_type, text, line_num, col))
                continue

            # ---- TIME, NUMBER, SEMICOLON, HOUR_SUFFIX ----
            self._tokens.append(Token(kind, text, line_num, col))

        return self._tokens

    def tokenize_recover(self, source: str) -> tuple[List[Token], List[LexicalError]]:
        """
        Like :py:meth:`tokenize` but *does not* raise on lexical errors.
        Instead, every bad character is recorded and lexing continues.

        Returns
        -------
        (tokens, errors) : tuple
            *tokens* – all valid tokens collected before / after errors.
            *errors* – list of :class:`LexicalError` for each bad character.
        """
        self._tokens = []
        self._errors = []
        self._source_lines = source.splitlines()

        line_num = 1
        line_start = 0

        for match in _TOKEN_PATTERN.finditer(source):
            kind = match.lastgroup
            text = match.group()
            col = match.start() - line_start + 1

            if kind == "WS":
                continue

            if kind == "NEWLINE":
                if self.keep_newlines:
                    self._tokens.append(Token("NEWLINE", text, line_num, col))
                line_num += 1
                line_start = match.end()
                continue

            if kind == "COMMENT":
                if self.keep_comments:
                    self._tokens.append(Token("COMMENT", text, line_num, col))
                continue

            if kind == "UNKNOWN":
                src_line = self._source_lines[line_num - 1] if line_num <= len(self._source_lines) else ""
                suggestion = self._SUGGESTIONS.get(text, f"Remove or replace the unexpected character '{text}'.")
                err = LexicalError(
                    f"Unexpected character '{text}'. {suggestion}",
                    line=line_num,
                    column=col,
                    source_line=src_line,
                )
                self._errors.append(err)
                continue  # keep going instead of raising

            if kind == "WORD":
                tok_type = self._classify_word(text)
                self._tokens.append(Token(tok_type, text, line_num, col))
                continue

            self._tokens.append(Token(kind, text, line_num, col))

        return self._tokens, self._errors

    def get_tokens_as_dicts(self) -> List[dict]:
        """
        Return the tokens from the most recent :py:meth:`tokenize` call as a
        list of plain dictionaries.  Suitable for direct use in a Streamlit
        ``st.dataframe()`` call or JSON serialisation.

        Returns
        -------
        List[dict]
            Each dict has keys: ``type``, ``value``, ``line``, ``column``.
        """
        return [tok.to_dict() for tok in self._tokens]

    @property
    def tokens(self) -> List[Token]:
        """Read-only view of the token list from the last tokenize call."""
        return list(self._tokens)

    @property
    def errors(self) -> List[LexicalError]:
        """Read-only view of the error list from the last tokenize_recover call."""
        return list(self._errors)

    # ------------------------------------------------------------------
    # Grammar accessor (for downstream parser)
    # ------------------------------------------------------------------

    @staticmethod
    def get_grammar() -> str:
        """Return the Lark EBNF grammar string for the TCS DSL."""
        return TCS_GRAMMAR

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_word(text: str) -> str:
        """
        Classify a raw WORD token into one of:
        ``KEYWORD``, ``DAY``, ``HOUR_SUFFIX``, or ``IDENTIFIER``.

        The HOUR_SUFFIX case is included here because the regex can match
        "HOUR" as a WORD (the HOUR_SUFFIX group only fires when HOUR appears
        *before* a non-word character, e.g. directly after a digit group
        that is matched separately).

        Parameters
        ----------
        text : str
            The matched word string.

        Returns
        -------
        str
            One of the token-type constants.
        """
        if text in KEYWORDS:
            return "KEYWORD"
        if text in DAYS:
            return "DAY"
        if text == "HOUR":
            return "HOUR_SUFFIX"
        return "IDENTIFIER"

    # ------------------------------------------------------------------
    # Utility / diagnostics
    # ------------------------------------------------------------------

    def summarize(self) -> dict:
        """
        Return a summary dict describing the token distribution of the last
        tokenize call.  Useful for the Streamlit dashboard.

        Returns
        -------
        dict
            Keys: ``total``, ``by_type`` (dict[str, int]), ``errors``.
        """
        by_type: dict[str, int] = {}
        for tok in self._tokens:
            by_type[tok.type] = by_type.get(tok.type, 0) + 1
        return {
            "total": len(self._tokens),
            "by_type": by_type,
            "errors": len(self._errors),
        }

    def pretty_print(self) -> str:
        """
        Return a human-readable table of all tokens.  Useful for debugging.
        """
        if not self._tokens:
            return "(no tokens)"
        col_widths = [10, 20, 6, 7]  # type, value, line, column
        header = (
            f"{'TYPE':<{col_widths[0]}} {'VALUE':<{col_widths[1]}} "
            f"{'LINE':>{col_widths[2]}} {'COLUMN':>{col_widths[3]}}"
        )
        sep = "-" * (sum(col_widths) + 3)
        rows = [header, sep]
        for tok in self._tokens:
            rows.append(
                f"{tok.type:<{col_widths[0]}} {tok.value!r:<{col_widths[1]}} "
                f"{tok.line:>{col_widths[2]}} {tok.column:>{col_widths[3]}}"
            )
        return "\n".join(rows)


# ---------------------------------------------------------------------------
# Convenience function (module-level)
# ---------------------------------------------------------------------------

def tokenize(source: str, **kwargs) -> List[Token]:
    """
    Module-level shortcut: create a :class:`Lexer` and tokenize *source*.

    Parameters
    ----------
    source : str
        TCS source text.
    **kwargs
        Forwarded to the :class:`Lexer` constructor
        (e.g. ``keep_comments=True``).

    Returns
    -------
    List[Token]

    Raises
    ------
    LexicalError
        On the first unrecognised character.
    """
    return Lexer(**kwargs).tokenize(source)


# ---------------------------------------------------------------------------
# Self-test / demo  (run: python -m compiler.lexer)
# ---------------------------------------------------------------------------

_SAMPLE_TCS = """\
# Sample TCS file for testing the lexer
RULE NO_ROOM_CLASH;
RULE NO_TEACHER_CLASH;
RULE Dr_Smith NOT_AVAILABLE Monday 9AM;
RULE CS101 ROOM R201;
RULE CS101 TEACHER Dr_Smith;
RULE CS101 DURATION 2HOUR;
RULE CS101 STUDENTS 35;
RULE CS101 DAYS_PER_WEEK 3;
RULE R201 CAPACITY 40;
RULE CS101 PREFERRED_TIME 10AM;
RULE CS101 PREFERRED_DAY Tuesday;
RULE GroupA NO_CLASH;
"""


def _run_demo() -> None:
    """Run a quick self-test and print results to stdout."""
    print("=" * 60)
    print("TCS Lexer — self-test")
    print("=" * 60)
    lexer = Lexer(keep_comments=True, keep_newlines=False)
    try:
        tokens = lexer.tokenize(_SAMPLE_TCS)
        print(lexer.pretty_print())
        print()
        summary = lexer.summarize()
        print(f"Total tokens : {summary['total']}")
        print(f"By type      : {summary['by_type']}")
        print(f"Errors       : {summary['errors']}")
    except LexicalError as exc:
        print(f"LEXICAL ERROR: {exc}")


if __name__ == "__main__":
    _run_demo()
