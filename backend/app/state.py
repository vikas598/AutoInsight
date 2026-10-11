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

# ---------------------------------------------------------------------------
# Enum-like Literals (TypedDict can't carry Enums without extras)
# ---------------------------------------------------------------------------
Intent = Literal[
    "sql_read",       # analytical SELECT query
    "sql_write",      # INSERT / UPDATE / DELETE  (requires approval)
    "ml_forecast",    # SARIMA / Prophet
    "ml_cluster",     # K-Means
    "ml_anomaly",     # Isolation Forest
    "clarification",  # question too vague — ask back
    "unsupported",    # outside scope entirely
]

ApprovalStatus = Literal["not_required", "pending", "approved", "rejected"]


# ---------------------------------------------------------------------------
# Nested payload shapes (declared loosely so stubs can return partial data)
# ---------------------------------------------------------------------------
class SchemaContext(TypedDict, total=False):
    """Trimmed, LLM-ready snapshot of the DB schema."""
    tables: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    enum_values: dict[str, list[str]]
    row_counts: dict[str, int]


class QueryResult(TypedDict, total=False):
    """Result of a successful SQL execution."""
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    executed_sql: str


class MLResult(TypedDict, total=False):
    """Result of an ML analytics run."""
    technique: Literal["forecast", "cluster", "anomaly"]
    summary: dict[str, Any]
    chart_data: list[dict[str, Any]]
    metrics: dict[str, float]


class VizConfig(TypedDict, total=False):
    """Recharts-ready chart spec produced by the Visualization Service."""
    chart_type: Literal["line", "bar", "pie", "scatter", "area", "table"]
    data: list[dict[str, Any]]
    x_key: str
    y_keys: list[str]
    title: str


# ---------------------------------------------------------------------------
# Main state object
# ---------------------------------------------------------------------------
class AutoInsightState(TypedDict, total=False):
    """
    The single state object flowing through the LangGraph.

    `total=False` so every field is optional — nodes only set what they touch.
    """

    # ---- Conversation ----
    messages: list[BaseMessage]        # full chat history (user + assistant turns)
    user_query: str                     # the latest user turn, verbatim
    session_id: str                     # ties this run to a DB connection

    # ---- Router outputs (Supervisor) ----
    intent: Intent | None
    plan: list[str]                     # optional step-by-step plan
    current_step: int                   # which step we're on (0-indexed)

    # ---- Schema context ----
    schema_context: SchemaContext

    # ---- SQL agent outputs ----
    sql_query: str                      # the generated SQL (read OR write)
    query_result: QueryResult           # execution result (read path)
    risk_score: int                     # 0-100, from Safety Pipeline (write path)
    preview_result: QueryResult         # dry-run preview (write path)

    # ---- ML agent outputs ----
    ml_result: MLResult

    # ---- Visualization ----
    viz_config: VizConfig

    # ---- Guard rails ----
    error: str | None                   # most recent error message, if any
    retry_count: int                    # how many times we've looped on error
    requires_approval: bool             # true for writes above risk threshold
    approval_status: ApprovalStatus     # driven by frontend ApprovalCard

    # ---- Final response ----
    response: str                       # narrative text sent back to the user


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
        ml_result=MLResult(),
        viz_config=VizConfig(),
        error=None,
        retry_count=0,
        requires_approval=False,
        approval_status="not_required",
        response="",
    )


# Configuration constants used by the graph & routing
MAX_RETRIES = 2
RISK_SCORE_THRESHOLD = 50   # writes with risk >= this need human approval
