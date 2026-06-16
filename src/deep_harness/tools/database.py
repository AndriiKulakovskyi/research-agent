"""Read-only database tools (SQLAlchemy) with semantics merged from the data dictionary."""

from __future__ import annotations

import re
from typing import Any

from langchain_core.tools import tool
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from deep_harness.config import get_settings
from deep_harness.tools.semantics import load_dictionary

MAX_ROWS = 200

_engine: Engine | None = None
_engine_url: str | None = None

# Statements allowed through run_sql. Writes go through migrations/scripts the
# user reviews, not through the agent's ad-hoc query tool. A read-only statement
# must START with one of these prefixes...
_READONLY_PREFIXES = ("select", "with", "explain", "show", "describe", "values")

# ...and contain NONE of these write/DDL/side-effecting keywords anywhere. The
# prefix check alone is not enough: a data-modifying CTE
# (`WITH x AS (DELETE ... RETURNING *) SELECT * FROM x`) or `EXPLAIN <write>`
# starts with an allowed word but mutates data on PostgreSQL/MySQL. `pragma` is
# dropped from the allow-list entirely because some SQLite pragmas write.
_WRITE_KEYWORDS = frozenset(
    {
        "insert", "update", "delete", "drop", "alter", "create", "truncate",
        "merge", "upsert", "grant", "revoke", "attach", "detach",
        "copy", "call", "do", "vacuum", "reindex", "exec", "execute", "into",
    }
)
# `REPLACE INTO` is caught by the prefix check (replace isn't an allowed prefix),
# so `replace` is intentionally NOT a banned keyword — replace() is a read-only
# string function in SQLite/Postgres/MySQL.

# Functions that read/write files, run OS commands, mutate sequences, or stall
# the server — all callable from inside a plain SELECT, where the keyword scan
# can't see them (e.g. SQLite `writefile()`, MySQL `sys_exec()`, Postgres
# `nextval()`/`pg_read_file()`). Denylisting is inherently incomplete: the real
# boundary for untrusted data is a least-privilege read-only DB account, which
# `_enforce_readonly` requests at the engine layer as defense in depth.
_DANGEROUS_FUNCTIONS = frozenset(
    {
        # SQLite
        "writefile", "readfile", "load_extension", "edit", "fts3_tokenizer",
        # PostgreSQL
        "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_stat_file",
        "lo_import", "lo_export", "lo_create", "lo_unlink", "dblink", "dblink_exec",
        "pg_terminate_backend", "pg_cancel_backend", "pg_reload_conf",
        "pg_stat_reset", "pg_switch_wal", "pg_rotate_logfile",
        "nextval", "setval", "pg_sleep", "pg_advisory_lock",
        # MySQL
        "sys_eval", "sys_exec", "load_file", "benchmark", "sleep", "get_lock",
    }
)


def _get_engine() -> Engine:
    global _engine, _engine_url
    url = get_settings().database_url
    if _engine is None or _engine_url != url:
        _engine = create_engine(url)
        _engine_url = url
    return _engine


def _strip_literals_and_comments(sql: str) -> str:
    """Blank out string literals and comments so keyword scanning isn't fooled by
    them and a `;` inside a string can't split one statement into two."""
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"'(?:[^']|'')*'", " ", sql)  # single-quoted strings
    sql = re.sub(r'"(?:[^"]|"")*"', " ", sql)  # double-quoted identifiers
    return sql


def _is_readonly(sql: str) -> bool:
    cleaned = _strip_literals_and_comments(sql)
    statements = [s.strip() for s in cleaned.split(";") if s.strip()]
    if len(statements) != 1:
        return False
    stmt = statements[0].lower()
    first_word = re.split(r"\s+", stmt, maxsplit=1)[0]
    if first_word not in _READONLY_PREFIXES:
        return False
    # Reject if any write/DDL keyword or dangerous function appears as a whole
    # word (catches CTE writes, EXPLAIN <write>, and side-effecting functions
    # called from a SELECT). Token-matching avoids false hits on substrings like
    # "offset" or "created_at".
    tokens = set(re.findall(r"[a-z_]+", stmt))
    return not (tokens & _WRITE_KEYWORDS) and not (tokens & _DANGEROUS_FUNCTIONS)


def _enforce_readonly(conn) -> None:
    """Defense in depth on top of `_is_readonly`: ask the engine itself to refuse
    writes on this connection, so a side effect that slips past the text guard is
    still blocked. Best-effort and dialect-specific — the real boundary for
    untrusted data is pointing DATABASE_URL at a least-privilege read-only account.
    """
    dialect = conn.engine.dialect.name
    try:
        if dialect == "sqlite":
            conn.exec_driver_sql("PRAGMA query_only=ON")
        elif dialect == "postgresql":
            conn.exec_driver_sql("SET TRANSACTION READ ONLY")
    except Exception:
        pass  # never let hardening break a legitimate read


def _format_rows(columns: list[str], rows: list[tuple[Any, ...]]) -> str:
    header = " | ".join(columns)
    sep = "-+-".join("-" * len(c) for c in columns)
    body = "\n".join(" | ".join(str(v) for v in row) for row in rows)
    return f"{header}\n{sep}\n{body}" if body else f"{header}\n{sep}\n(no rows)"


@tool
def list_tables() -> str:
    """List all tables (and views) in the configured database."""
    insp = inspect(_get_engine())
    tables = insp.get_table_names()
    views = insp.get_view_names()
    parts = []
    if tables:
        parts.append("Tables: " + ", ".join(sorted(tables)))
    if views:
        parts.append("Views: " + ", ".join(sorted(views)))
    return "\n".join(parts) or "The database has no tables yet."


@tool
def describe_table(table: str) -> str:
    """Show a table's columns with SQL types, primary/foreign keys, and — when the
    data dictionary has them — semantic descriptions of each column. Always check
    this before writing queries against an unfamiliar table.
    """
    insp = inspect(_get_engine())
    if table not in insp.get_table_names() + insp.get_view_names():
        return f"No table named {table!r}. Known tables: {', '.join(insp.get_table_names())}"

    dictionary = load_dictionary()
    pk = set(insp.get_pk_constraint(table).get("constrained_columns") or [])
    fks = {
        col: f"{fk['referred_table']}.{fk['referred_columns'][0]}"
        for fk in insp.get_foreign_keys(table)
        for col in fk["constrained_columns"]
    }

    lines = [f"Table {table}:"]
    for col in insp.get_columns(table):
        name = col["name"]
        flags = []
        if name in pk:
            flags.append("PK")
        if name in fks:
            flags.append(f"FK -> {fks[name]}")
        if not col.get("nullable", True):
            flags.append("NOT NULL")
        flag_str = f" [{', '.join(flags)}]" if flags else ""
        semantic = dictionary.get(f"{table}.{name}", {})
        desc = semantic.get("description", "")
        unit = semantic.get("unit", "")
        semantic_str = f" — {desc}" if desc else ""
        if unit:
            semantic_str += f" (unit: {unit})"
        lines.append(f"  {name}: {col['type']}{flag_str}{semantic_str}")

    undocumented = [
        c["name"] for c in insp.get_columns(table) if f"{table}.{c['name']}" not in dictionary
    ]
    if undocumented:
        lines.append(
            f"Columns without dictionary entries: {', '.join(undocumented)} "
            "(consider define_variable after you learn their meaning)."
        )
    return "\n".join(lines)


@tool
def run_sql(query: str, limit: int = 50) -> str:
    """Run a single read-only SQL statement (SELECT/WITH/EXPLAIN...) against the
    configured database and return the rows as a text table. Results are capped
    at `limit` rows (max 200). Mutating statements are rejected — write changes
    via scripts in the workspace instead.
    """
    if not _is_readonly(query):
        return (
            "Rejected: run_sql only accepts a single read-only statement "
            "(SELECT, WITH, EXPLAIN, PRAGMA, SHOW, DESCRIBE, VALUES). "
            "For writes, generate a script in the workspace and run it via execute."
        )
    limit = max(1, min(limit, MAX_ROWS))
    try:
        with _get_engine().connect() as conn:
            _enforce_readonly(conn)
            result = conn.execute(text(query))
            columns = list(result.keys())
            rows = result.fetchmany(limit + 1)
    except Exception as exc:  # surface DB errors to the model so it can adapt
        return f"SQL error: {exc}"
    truncated = len(rows) > limit
    table = _format_rows(columns, [tuple(r) for r in rows[:limit]])
    if truncated:
        table += f"\n... truncated at {limit} rows; refine the query or raise `limit`."
    return table


DATABASE_TOOLS = [list_tables, describe_table, run_sql]
