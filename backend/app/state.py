"""
AutoInsight — LangGraph State Object
=====================================
The TypedDict carried through every node in the StateGraph.

LangGraph merges nodes' return dicts into this state by key. A node returns
ONLY the fields it changed; everything else is preserved automatically.

Field groups:
  * conversation      — raw user turn & accumulated chat history
  * router outputs    — Supervisor's classification of intent
  * execution outputs — results from SQL / ML agents
  * guard rails       — retry counting, approval gating, error tracking
  * final response    — narrative + viz handed back to the frontend
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from langchain_core.messages import BaseMessage


Intent = Literal[
    "sql_read",
    "sql_write",
    "ml_forecast",
    "ml_cluster",
    "ml_anomaly",
    "clarification",
    "unsupported",
]

ApprovalStatus = Literal["not_required", "pending", "approved", "rejected"]


# ---------------------------------------------------------------------------
# Nested payload shapes
# ---------------------------------------------------------------------------
class SchemaContext(TypedDict, total=False):
    tables: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    enum_values: dict[str, list[str]]
    row_counts: dict[str, int]


class QueryResult(TypedDict, total=False):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    executed_sql: str


class MLResult(TypedDict, total=False):
    technique: Literal["forecast", "cluster", "anomaly"]
    summary: dict[str, Any]
    chart_data: list[dict[str, Any]]
    metrics: dict[str, float]


class VizConfig(TypedDict, total=False):
    chart_type: Literal["line", "bar", "pie", "scatter", "area", "table"]
    data: list[dict[str, Any]]
    x_key: str
    y_keys: list[str]
    title: str


class WriteAssessment(TypedDict, total=False):
    """
    Serialized SafetyPipeline.Assessment. Carried across the wait_approval
    interrupt so the agent can reconstruct the write to execute.
    """
    sql: str
    operation: str
    target_table: str
    risk_score: int
    risk_factors: dict[str, int]
    requires_approval: bool
    preview_columns: list[str]
    preview_rows: list[list[Any]]
    affected_rows: int
    decision: str
    error: str | None


# ---------------------------------------------------------------------------
# Main state object
# ---------------------------------------------------------------------------
class AutoInsightState(TypedDict, total=False):
    """The single state object flowing through the LangGraph."""

    # ---- Conversation ----
    messages: list[BaseMessage]
    user_query: str
    session_id: str

    # ---- Router outputs ----
    intent: Intent | None
    plan: list[str]
    current_step: int

    # ---- Schema context ----
    schema_context: SchemaContext

    # ---- SQL agent outputs ----
    sql_query: str
    query_result: QueryResult
    risk_score: int
    preview_result: QueryResult
    write_assessment: WriteAssessment     # NEW — carries pipeline Assessment

    # ---- ML agent outputs ----
    ml_result: MLResult

    # ---- Visualization ----
    viz_config: VizConfig

    # ---- Guard rails ----
    error: str | None
    retry_count: int
    requires_approval: bool
    approval_status: ApprovalStatus
    approved_by: str | None               # NEW — who approved/rejected

    # ---- Final response ----
    response: str


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def new_state(user_query: str, session_id: str) -> AutoInsightState:
    """Build a fresh state for a new user turn."""
    return AutoInsightState(
        messages=[],
        user_query=user_query,
        session_id=session_id,
        intent=None,
        plan=[],
        current_step=0,
        schema_context=SchemaContext(),
        sql_query="",
        query_result=QueryResult(),
        risk_score=0,
        preview_result=QueryResult(),
        write_assessment=WriteAssessment(),
        ml_result=MLResult(),
        viz_config=VizConfig(),
        error=None,
        retry_count=0,
        requires_approval=False,
        approval_status="not_required",
        approved_by=None,
        response="",
    )


# Configuration constants used by the graph & routing
MAX_RETRIES = 2
RISK_SCORE_THRESHOLD = 50
