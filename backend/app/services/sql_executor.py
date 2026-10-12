"""
AutoInsight — Safe SQL Executor
================================
Executes read-path SQL against the reader engine with:
  * Automatic LIMIT enforcement (via sqlglot — no string manipulation)
  * Statement timeout (30s, enforced at the Postgres role level)
  * Row serialization (Decimal → float, date → ISO string, etc.)
  * Clean error wrapping

This module trusts that the SQL has ALREADY passed the SQL agent's
3-stage validation (AST parse → SELECT-only → schema references).
It is NOT a security boundary — the Postgres role is.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlglot
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import get_connection_manager
from app.state import QueryResult


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEFAULT_MAX_ROWS = 1000
DEFAULT_TIMEOUT_S = 30         # already enforced at the role level too


class SQLExecutionError(Exception):
    """Raised when SQL execution fails after validation has passed."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def execute_read_query(
    sql: str,
    *,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> QueryResult:
    """
    Execute a SELECT query via the reader engine and return a QueryResult.

    LIMIT is enforced automatically. Rows are serialized to JSON-safe values.
    Statement timeout is enforced at the Postgres role level (30s).

    Raises:
        SQLExecutionError — on any execution failure (wraps SQLAlchemy errors)
    """
    safe_sql = enforce_limit(sql, max_rows)
    engine = get_connection_manager().read_engine

    try:
        with engine.connect() as conn:
            result = conn.execute(text(safe_sql))
            columns = list(result.keys())
            raw_rows = result.fetchall()
    except SQLAlchemyError as e:
        # Expose a clean message; the raw exception may be very long
        root = e.__cause__ or e
        raise SQLExecutionError(f"{type(root).__name__}: {str(root)[:300]}") from e

    serialized = [[_serialize(v) for v in row] for row in raw_rows]
    truncated = len(serialized) >= max_rows

    return QueryResult(
        columns=columns,
        rows=serialized,
        row_count=len(serialized),
        truncated=truncated,
        executed_sql=safe_sql,
    )


# ---------------------------------------------------------------------------
# LIMIT enforcement — AST-based, not string munging
# ---------------------------------------------------------------------------
def enforce_limit(sql: str, max_rows: int) -> str:
    """
    Return `sql` with `LIMIT max_rows` added if no LIMIT is already present,
    OR with the existing LIMIT lowered if it exceeds `max_rows`.

    Uses sqlglot to manipulate the AST so SELECTs, UNIONs, and CTEs are all
    handled correctly without regex surgery.
    """
    try:
        parsed = sqlglot.parse_one(sql, read="postgres")
    except Exception:
        # Parse failure here is unexpected (validation should have caught it)
        # — fall back to a crude append so we never execute unlimited.
        clean = sql.rstrip().rstrip(";").strip()
        return f"{clean} LIMIT {max_rows}"

    existing = parsed.args.get("limit")
    if existing is None:
        parsed = parsed.limit(max_rows)
    else:
        # Already limited — respect user's cap unless it exceeds ours
        try:
            current = int(existing.expression.name)
            if current > max_rows:
                parsed = parsed.limit(max_rows)
        except (AttributeError, ValueError):
            # Weird LIMIT expression — leave it alone
            pass

    return parsed.sql(dialect="postgres")


# ---------------------------------------------------------------------------
# Row serialization
# ---------------------------------------------------------------------------
def _serialize(v: Any) -> Any:
    """Convert DB types to JSON-safe primitives."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        # JSON has no Decimal; floats are fine for display
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return v
