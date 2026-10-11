"""
SQL / CRUD Agent — STUB
========================
Generates SQL for the user's intent, validates it, executes it against the
database, and writes a narrative summary of the result.

This stub returns canned responses so the graph can be smoke-tested.
Real implementation (Steps 4 & 6):
  * Read path  → prompt LLM with schema → sqlglot AST validation → execute
                 with timeout + LIMIT → narrate result
  * Write path → prompt LLM → Safety Pipeline (6 stages) → request approval
                 → execute on approval → audit log
"""

from __future__ import annotations

from app.state import AutoInsightState


def sql_agent_node(state: AutoInsightState) -> dict:
    """
    STUB implementation of the SQL agent.

    Dispatches on state["intent"] (sql_read vs sql_write).
    """
    intent = state.get("intent")

    if intent == "sql_read":
        return _handle_read_stub(state)

    if intent == "sql_write":
        return _handle_write_stub(state)

    # Shouldn't get here — routing should prevent it
    return {
        "error": f"sql_agent called with unexpected intent: {intent}",
        "retry_count": state.get("retry_count", 0) + 1,
    }


def _handle_read_stub(state: AutoInsightState) -> dict:
    """Stub for the read path."""
    query = state.get("user_query", "")

    # Pretend we generated SQL and ran it
    stub_sql = "SELECT COUNT(*) FROM sales WHERE sale_date >= '2024-01-01';"
    stub_result = {
        "columns": ["count"],
        "rows": [[487]],
        "row_count": 1,
        "truncated": False,
        "executed_sql": stub_sql,
    }

    return {
        "sql_query": stub_sql,
        "query_result": stub_result,
        "response": f"[STUB] Generated SQL for: {query!r}. Would return 487 rows.",
        "error": None,
    }


def _handle_write_stub(state: AutoInsightState) -> dict:
    """
    Stub for the write path — simulates risk scoring and approval gating.
    Real implementation routes through the Safety Pipeline (Step 5).
    """
    query = state.get("user_query", "")
    stub_sql = "UPDATE vehicles SET status = 'reserved' WHERE id = 123;"

    # Simulated risk score (real one is computed by SafetyPipeline)
    stub_risk = 35

    # If already approved (second pass through), "execute"
    if state.get("approval_status") == "approved":
        return {
            "query_result": {
                "columns": [],
                "rows": [],
                "row_count": 1,
                "truncated": False,
                "executed_sql": stub_sql,
            },
            "response": f"[STUB] Executed write. 1 row affected.",
            "requires_approval": False,
            "approval_status": "not_required",
            "error": None,
        }

    # First pass: request approval
    return {
        "sql_query": stub_sql,
        "risk_score": stub_risk,
        "preview_result": {
            "columns": ["affected_rows"],
            "rows": [[1]],
            "row_count": 1,
            "truncated": False,
            "executed_sql": stub_sql,
        },
        "requires_approval": True,
        "approval_status": "pending",
        "response": f"[STUB] Prepared write for: {query!r}. Awaiting approval.",
        "error": None,
    }
