"""
AutoInsight — LangGraph Routing Functions
==========================================
Conditional edges in LangGraph are plain functions that read the current state
and return the NAME of the next node (or END to terminate).

Two routers:
  * route_from_supervisor  — fires right after the Supervisor classifies intent
  * route_after_agent      — fires after SQL / ML agent finishes, decides retry
                              vs continue vs end
"""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END

from app.state import MAX_RETRIES, AutoInsightState


# ---------------------------------------------------------------------------
# Supervisor → next node
# ---------------------------------------------------------------------------
def route_from_supervisor(
    state: AutoInsightState,
) -> Literal["sql_agent", "ml_agent", "respond", "__end__"]:
    """
    Decide which agent handles this intent (or whether we bail out).

    Supervisor must have populated state["intent"] before this fires.
    """
    intent = state.get("intent")

    # Hard-coded intent → node mapping
    if intent in ("sql_read", "sql_write"):
        return "sql_agent"

    if intent in ("ml_forecast", "ml_cluster", "ml_anomaly"):
        return "ml_agent"

    if intent in ("clarification", "unsupported"):
        # Supervisor itself produced the user-facing response; go straight to end
        return "respond"

    # Fallback: supervisor didn't classify — treat as unsupported
    return "respond"


# ---------------------------------------------------------------------------
# Agent → supervisor OR end
# ---------------------------------------------------------------------------
def route_after_agent(
    state: AutoInsightState,
) -> Literal["supervisor", "respond", "wait_approval", "__end__"]:
    """
    After an agent runs, decide:
      - loop back to supervisor if there's a recoverable error and retries left
      - pause for approval if a write needs human sign-off
      - otherwise respond and end
    """

    # ---- 1. Approval gate (writes with risk_score above threshold) ----
    if state.get("requires_approval") and state.get("approval_status") == "pending":
        return "wait_approval"

    # ---- 2. Error → retry via supervisor ----
    err = state.get("error")
    retries = state.get("retry_count", 0)

    if err and retries < MAX_RETRIES:
        # Supervisor will see the error in state and re-plan
        return "supervisor"

    if err and retries >= MAX_RETRIES:
        # Give up — fall through to respond with the error narrative
        return "respond"

    # ---- 3. Happy path ----
    return "respond"


# ---------------------------------------------------------------------------
# After wait_approval
# ---------------------------------------------------------------------------
def route_after_approval(
    state: AutoInsightState,
) -> Literal["sql_agent", "respond"]:
    """
    After the frontend posts an approval decision, the graph resumes here.
    """
    status = state.get("approval_status")
    if status == "approved":
        # Hand back to SQL agent to execute the write
        return "sql_agent"
    # rejected or anything else → respond with cancellation
    return "respond"
