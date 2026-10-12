"""
AutoInsight — LangGraph Routing Functions
==========================================
Conditional edges in LangGraph are plain functions that read the current state
and return the NAME of the next node (or END to terminate).

Three routers:
  * route_from_supervisor  — fires right after the Supervisor classifies intent
  * route_after_agent      — fires after SQL / ML agent finishes
  * route_after_approval   — fires after the wait_approval interrupt resumes
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
    intent = state.get("intent")

    if intent in ("sql_read", "sql_write"):
        return "sql_agent"

    if intent in ("ml_forecast", "ml_cluster", "ml_anomaly"):
        return "ml_agent"

    if intent in ("clarification", "unsupported"):
        return "respond"

    return "respond"


# ---------------------------------------------------------------------------
# Agent → supervisor OR wait_approval OR respond
# ---------------------------------------------------------------------------
def route_after_agent(
    state: AutoInsightState,
) -> Literal["supervisor", "respond", "wait_approval", "__end__"]:
    # Approval gate (writes with risk_score above threshold)
    if state.get("requires_approval") and state.get("approval_status") == "pending":
        return "wait_approval"

    # Error → retry via supervisor (bounded)
    err = state.get("error")
    retries = state.get("retry_count", 0)

    if err and retries < MAX_RETRIES:
        return "supervisor"

    if err and retries >= MAX_RETRIES:
        return "respond"

    # Happy path
    return "respond"


# ---------------------------------------------------------------------------
# After wait_approval — FIX: both approved AND rejected re-enter sql_agent
# ---------------------------------------------------------------------------
def route_after_approval(
    state: AutoInsightState,
) -> Literal["sql_agent", "respond"]:
    """
    Resume path after the user clicks Approve or Reject.

    BOTH decisions route back through sql_agent so that `_handle_approval`
    runs: on 'approved' it calls pipeline.execute() + audits; on 'rejected'
    it calls pipeline.reject() + audits and writes the "Change rejected"
    narrative. Only "approved"/"rejected" trigger this re-entry; any other
    status (shouldn't happen) short-circuits to respond.
    """
    status = state.get("approval_status")
    if status in ("approved", "rejected"):
        return "sql_agent"
    return "respond"