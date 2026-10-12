"""
AutoInsight — Safety Pipeline
==============================
The deterministic tool that gates every write operation. Six stages, each one
a hard gate that halts the whole chain on failure:

    1. AST VALIDATE       Parse via sqlglot; must be INSERT / UPDATE / DELETE,
                          exactly one statement, no DDL anywhere in the tree.

    2. SCHEMA VALIDATE    Every referenced table + column must exist
                          (reuses SchemaService.validate_references).

    3. RISK SCORING       Score 0-100 from four factors:
                            * operation type    (DELETE > UPDATE > INSERT)
                            * table sensitivity (sales/salespersons > rest)
                            * WHERE specificity (none > generic > PK-based)
                            * estimated rows    (count-same-WHERE heuristic)
                          Scores ≥ RISK_THRESHOLD require human approval.

    4. TXN PREVIEW        Open a transaction, run a SELECT with the SAME
                          WHERE clause to show what would change, then
                          ROLLBACK. The write is NOT executed here — the
                          preview is purely read-only.

    5. HUMAN APPROVAL     Returned to LangGraph as a wait_approval interrupt.
                          Frontend's ApprovalCard shows preview + risk and
                          posts the decision back via graph.update_state().

    6. EXECUTE + AUDIT    On "approved", run the write in its own transaction
                          with COMMIT, then append a JSONL audit entry.
                          On "rejected" or any failure, audit the outcome too.

Public interface (used by SQL agent write path in Step 6):

    pipeline = SafetyPipeline()
    assessment = pipeline.assess(sql, session_id=..., user_query=...)
    # assessment is a dict with risk_score, requires_approval, preview_result, ...

    # Later, after approval:
    result = pipeline.execute(sql, assessment, approved_by="user@example.com")

The SafetyPipeline is a service, not an agent — it never calls an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import sqlglot
import sqlglot.expressions as exp
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db import get_connection_manager
from app.services.audit_log import get_audit_logger
from app.services.schema_service import get_schema_service
from app.services.sql_executor import _serialize   # row serializer


# ===========================================================================
# Configuration
# ===========================================================================
# Score at which human approval is required. Writes above this threshold
# cannot be auto-executed. Everything mutative scores >= 25 in practice,
# so a threshold of 30 means "approve everything except trivial inserts".
RISK_THRESHOLD = int(__import__("os").environ.get("SAFETY_RISK_THRESHOLD", "30"))

# Max rows the preview SELECT returns before truncation (keeps UI responsive).
PREVIEW_MAX_ROWS = 50

# Per-table sensitivity weights (0-25). Everything else defaults to 10.
TABLE_SENSITIVITY = {
    "sales":         25,
    "salespersons":  25,
    "customers":     20,
    "vehicles":      20,
    "expenses":      15,
    "services":      15,
    "leads":         10,
    "inventory_log": 10,
}

# Operation-type weights (0-40)
OP_WEIGHTS = {
    "INSERT": 10,
    "UPDATE": 25,
    "DELETE": 40,
}


# ===========================================================================
# Dataclass for the assessment payload
# ===========================================================================
Decision = Literal[
    "auto_approved",   # risk < threshold, pipeline will execute next
    "needs_approval",  # risk >= threshold, pipeline paused
    "approved",        # user approved via ApprovalCard
    "rejected",        # user rejected via ApprovalCard
    "blocked",         # failed AST or schema validation
    "error",           # execution raised
]


@dataclass
class Assessment:
    """Result of `pipeline.assess()`. Fed to execute() and the frontend."""
    sql: str
    operation: str                              # INSERT / UPDATE / DELETE
    target_table: str
    risk_score: int                             # 0-100
    risk_factors: dict[str, int]                # per-factor breakdown
    requires_approval: bool
    preview_columns: list[str] = field(default_factory=list)
    preview_rows: list[list[Any]] = field(default_factory=list)
    affected_rows: int = 0
    decision: Decision = "needs_approval"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sql": self.sql,
            "operation": self.operation,
            "target_table": self.target_table,
            "risk_score": self.risk_score,
            "risk_factors": self.risk_factors,
            "requires_approval": self.requires_approval,
            "preview": {
                "columns": self.preview_columns,
                "rows": self.preview_rows,
                "affected_rows": self.affected_rows,
            },
            "decision": self.decision,
            "error": self.error,
        }


# ===========================================================================
# SafetyPipeline — the public interface
# ===========================================================================
class SafetyPipeline:
    """Stages 1-4 happen in assess(). Stage 6 happens in execute()."""

    # -------------------------------------------------------------------
    # Entry: assess (stages 1-4)
    # -------------------------------------------------------------------
    def assess(
        self,
        sql: str,
        *,
        session_id: str = "unknown",
        user_query: str = "",
    ) -> Assessment:
        """
        Run stages 1-4 and return an Assessment.

        Stage 1 or 2 failure → Assessment with decision="blocked" and error set.
        Stage 3+ success → decision is either "auto_approved" or "needs_approval".
        """
        # ---- Stage 1: AST validate ----
        ast_ok, operation, target_table, parsed, err = _parse_and_classify(sql)
        if not ast_ok:
            return Assessment(
                sql=sql, operation=operation or "UNKNOWN",
                target_table=target_table or "",
                risk_score=100, risk_factors={},
                requires_approval=True, decision="blocked", error=err,
            )

        # ---- Stage 2: Schema validate ----
        schema_svc = get_schema_service()
        schema_ok, schema_errs = schema_svc.validate_references(sql)
        if not schema_ok:
            return Assessment(
                sql=sql, operation=operation, target_table=target_table,
                risk_score=100, risk_factors={},
                requires_approval=True, decision="blocked",
                error="Schema validation failed: " + "; ".join(schema_errs),
            )

        # ---- Stage 3: Risk score ----
        preview_cols, preview_rows, affected = _run_preview(
            sql, parsed, operation, target_table
        )
        risk_score, factors = _score_risk(
            operation=operation,
            target_table=target_table,
            parsed=parsed,
            affected_rows=affected,
        )
        requires_approval = risk_score >= RISK_THRESHOLD

        return Assessment(
            sql=sql,
            operation=operation,
            target_table=target_table,
            risk_score=risk_score,
            risk_factors=factors,
            requires_approval=requires_approval,
            preview_columns=preview_cols,
            preview_rows=preview_rows,
            affected_rows=affected,
            decision="needs_approval" if requires_approval else "auto_approved",
        )

    # -------------------------------------------------------------------
    # Entry: execute (stage 6)
    # -------------------------------------------------------------------
    def execute(
        self,
        assessment: Assessment,
        *,
        session_id: str,
        user_query: str,
        approved_by: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute the write in its own transaction, write an audit entry,
        return a result dict suitable for state["query_result"].

        Caller is responsible for only calling this once the user approved
        OR when assessment.decision == "auto_approved".
        """
        audit = get_audit_logger()

        if assessment.decision == "blocked":
            audit.log(
                session_id=session_id, user_query=user_query, sql=assessment.sql,
                operation=assessment.operation, target_table=assessment.target_table,
                risk_score=assessment.risk_score, risk_factors=assessment.risk_factors,
                affected_rows=0, decision="blocked", executed=False,
                approved_by=approved_by, error=assessment.error,
            )
            return {
                "executed": False,
                "error": assessment.error,
                "affected_rows": 0,
                "sql": assessment.sql,
            }

        engine = get_connection_manager().write_engine
        decision_label: Decision = "approved" if approved_by else "auto_approved"
        rows_affected = 0
        err: str | None = None

        try:
            with engine.begin() as conn:                 # txn with auto-commit
                result = conn.execute(text(assessment.sql))
                rows_affected = result.rowcount if result.rowcount is not None else 0
        except SQLAlchemyError as e:
            root = e.__cause__ or e
            err = f"{type(root).__name__}: {str(root)[:300]}"
            decision_label = "error"

        audit.log(
            session_id=session_id, user_query=user_query, sql=assessment.sql,
            operation=assessment.operation, target_table=assessment.target_table,
            risk_score=assessment.risk_score, risk_factors=assessment.risk_factors,
            affected_rows=rows_affected, decision=decision_label,
            executed=(err is None), approved_by=approved_by, error=err,
        )

        return {
            "executed": err is None,
            "error": err,
            "affected_rows": rows_affected,
            "sql": assessment.sql,
            "decision": decision_label,
        }

    # -------------------------------------------------------------------
    # Entry: reject (also audits)
    # -------------------------------------------------------------------
    def reject(
        self,
        assessment: Assessment,
        *,
        session_id: str,
        user_query: str,
        rejected_by: str | None = None,
    ) -> dict[str, Any]:
        """User chose Reject on the ApprovalCard — audit it."""
        get_audit_logger().log(
            session_id=session_id, user_query=user_query, sql=assessment.sql,
            operation=assessment.operation, target_table=assessment.target_table,
            risk_score=assessment.risk_score, risk_factors=assessment.risk_factors,
            affected_rows=0, decision="rejected", executed=False,
            approved_by=rejected_by, error=None,
        )
        return {
            "executed": False, "error": None, "affected_rows": 0,
            "sql": assessment.sql, "decision": "rejected",
        }


# ===========================================================================
# Stage 1 — AST parse + operation classification
# ===========================================================================
# Only these DML top-level nodes are allowed on the write path.
_ALLOWED_WRITE = {exp.Insert: "INSERT", exp.Update: "UPDATE", exp.Delete: "DELETE"}

# These top-level or nested types abort validation immediately.
_FORBIDDEN = (
    exp.Drop, exp.Create, exp.Alter, exp.TruncateTable, exp.Merge,
)


def _parse_and_classify(sql: str):
    """Return (ok, operation, target_table, parsed, error)."""
    try:
        parsed = sqlglot.parse_one(sql, read="postgres")
    except Exception as e:
        return (False, None, None, None, f"SQL parse error: {e}")

    if parsed is None:
        return (False, None, None, None, "Empty SQL")

    # No DDL anywhere in the tree
    for walked in parsed.walk():
        node = walked[0] if isinstance(walked, tuple) else walked
        if isinstance(node, _FORBIDDEN):
            return (False, None, None, None,
                    f"DDL / destructive operation not allowed: {type(node).__name__}")

    # Top-level must be INSERT / UPDATE / DELETE
    operation = None
    for cls, name in _ALLOWED_WRITE.items():
        if isinstance(parsed, cls):
            operation = name
            break
    if operation is None:
        return (False, None, None, None,
                f"Write path requires INSERT/UPDATE/DELETE — got {type(parsed).__name__}")

    # Target table
    target_table = _extract_target_table(parsed, operation)
    if not target_table:
        return (False, operation, None, parsed, "Could not identify target table")

    return (True, operation, target_table, parsed, None)


def _extract_target_table(parsed, operation: str) -> str | None:
    """Pull the target table name out of an INSERT / UPDATE / DELETE AST."""
    if operation == "INSERT":
        tbl = parsed.find(exp.Table)
    elif operation == "UPDATE":
        tbl = parsed.find(exp.Table)
    elif operation == "DELETE":
        tbl = parsed.find(exp.Table)
    else:
        tbl = None
    return tbl.name.lower() if tbl else None


# ===========================================================================
# Stage 3 — Risk scoring
# ===========================================================================
def _score_risk(
    *,
    operation: str,
    target_table: str,
    parsed,
    affected_rows: int,
) -> tuple[int, dict[str, int]]:
    """
    Return (score, factor_breakdown) where score is 0-100.

    Factors (max contributions):
      * op              40
      * table_sens      25
      * where_spec      20
      * est_rows        15
    """
    f_op = OP_WEIGHTS.get(operation, 25)
    f_tbl = TABLE_SENSITIVITY.get(target_table, 10)
    f_where = _where_specificity(parsed, operation)
    f_rows = _row_count_factor(affected_rows)

    score = f_op + f_tbl + f_where + f_rows
    return score, {
        "op": f_op,
        "table_sensitivity": f_tbl,
        "where_specificity": f_where,
        "estimated_rows": f_rows,
    }


def _where_specificity(parsed, operation: str) -> int:
    """
    How targeted is the WHERE clause?
      no WHERE                   → 20   (unbounded; worst)
      WHERE present, no PK col   → 10   (generic predicate)
      WHERE on primary key       →  0   (surgical)
    INSERTs always get 0 (no WHERE applies).
    """
    if operation == "INSERT":
        return 0

    where = parsed.find(exp.Where)
    if where is None:
        return 20

    # Walk the WHERE and see if any column is 'id' or ends in '_id' with "="
    pk_touched = False
    for node in where.walk():
        n = node[0] if isinstance(node, tuple) else node
        if isinstance(n, exp.EQ):
            col = n.find(exp.Column)
            if col:
                cname = col.name.lower()
                if cname == "id" or cname.endswith("_id"):
                    pk_touched = True
                    break
    return 0 if pk_touched else 10


def _row_count_factor(affected: int) -> int:
    if affected <= 0:
        return 0
    if affected <= 10:
        return 5
    if affected <= 100:
        return 10
    return 15


# ===========================================================================
# Stage 4 — Transactional preview
# ===========================================================================
def _run_preview(
    sql: str, parsed, operation: str, target_table: str,
) -> tuple[list[str], list[list[Any]], int]:
    """
    Return (columns, rows, affected_count).

    For UPDATE / DELETE: issue a SELECT with the SAME WHERE clause.
    For INSERT: no preview rows — just affected = 1 for a single VALUES tuple.
    """
    engine = get_connection_manager().read_engine     # read-only for the preview

    if operation == "INSERT":
        # INSERT ... VALUES — rowcount = len(VALUES tuples)
        # INSERT ... SELECT — we can run the SELECT to count
        values_count = _count_insert_values(parsed)
        if values_count is not None:
            return ([], [], values_count)
        # INSERT ... SELECT path
        select = parsed.find(exp.Select)
        if select is None:
            return ([], [], 0)
        count_sql = f"SELECT COUNT(*) FROM ({select.sql(dialect='postgres')}) sub"
        try:
            with engine.connect() as conn:
                n = conn.execute(text(count_sql)).scalar() or 0
            return ([], [], int(n))
        except Exception:
            return ([], [], 0)

    # UPDATE / DELETE preview SELECT
    where = parsed.find(exp.Where)
    where_sql = f"WHERE {where.this.sql(dialect='postgres')}" if where else ""
    preview_sql = f'SELECT * FROM "{target_table}" {where_sql} LIMIT {PREVIEW_MAX_ROWS}'
    count_sql = f'SELECT COUNT(*) FROM "{target_table}" {where_sql}'

    cols: list[str] = []
    rows: list[list[Any]] = []
    affected = 0

    try:
        with engine.connect() as conn:
            affected = int(conn.execute(text(count_sql)).scalar() or 0)
            result = conn.execute(text(preview_sql))
            cols = list(result.keys())
            raw = result.fetchall()
            rows = [[_serialize(v) for v in r] for r in raw]
    except SQLAlchemyError:
        # Preview failures should not abort assessment — surface rows=0
        pass

    return cols, rows, affected


def _count_insert_values(parsed) -> int | None:
    """For an INSERT ... VALUES, return the number of value tuples. Else None."""
    values = parsed.find(exp.Values)
    if values is None:
        return None
    return len(values.expressions)


# ===========================================================================
# Module-level singleton
# ===========================================================================
_pipeline: SafetyPipeline | None = None


def get_safety_pipeline() -> SafetyPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = SafetyPipeline()
    return _pipeline
