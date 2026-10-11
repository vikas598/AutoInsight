"""
AutoInsight — LangGraph StateGraph
===================================
Wires the three agent nodes together via conditional edges.

Topology:

    START
      ↓
    supervisor ──┬──→ sql_agent ───┬──→ wait_approval ──→ sql_agent (resume)
                 │                 │
                 ├──→ ml_agent  ───┤
                 │                 ↓
                 └──→ respond    END
                       ↓
                      END

Error loops go back to supervisor (bounded by MAX_RETRIES).
Approval pauses the graph with an interrupt — the frontend's ApprovalCard
sends the user's decision, which resumes execution via the Checkpointer.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents import ml_agent_node, sql_agent_node, supervisor_node
from app.routing import (
    route_after_agent,
    route_after_approval,
    route_from_supervisor,
)
from app.state import AutoInsightState


# ---------------------------------------------------------------------------
# Terminal "respond" node — final narrative is already in state["response"].
# This node exists so the graph has a single exit point we can hook later
# (logging, telemetry, response formatting).
# ---------------------------------------------------------------------------
def respond_node(state: AutoInsightState) -> dict:
    """Terminal node — pass-through for now."""
    response = state.get("response") or "No response generated."
    return {"response": response}


# ---------------------------------------------------------------------------
# wait_approval node — a pure pause point.
# LangGraph pauses graph execution before this node runs (via interrupt_before)
# so the frontend can post the approval decision. Once resumed, the state
# already carries the updated approval_status.
# ---------------------------------------------------------------------------
def wait_approval_node(state: AutoInsightState) -> dict:
    """No-op — exists purely as an interrupt point."""
    return {}


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------
def build_graph(checkpointer=None):
    """
    Construct and compile the AutoInsight StateGraph.

    Args:
        checkpointer: Optional LangGraph checkpointer for persistence.
                      Defaults to an in-memory MemorySaver (fine for dev).
    """
    workflow = StateGraph(AutoInsightState)

    # ---- Register nodes ----
    workflow.add_node("supervisor",     supervisor_node)
    workflow.add_node("sql_agent",      sql_agent_node)
    workflow.add_node("ml_agent",       ml_agent_node)
    workflow.add_node("wait_approval",  wait_approval_node)
    workflow.add_node("respond",        respond_node)

    # ---- Entry ----
    workflow.add_edge(START, "supervisor")

    # ---- Supervisor → agents / respond ----
    workflow.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "sql_agent": "sql_agent",
            "ml_agent":  "ml_agent",
            "respond":   "respond",
            END:         END,
        },
    )

    # ---- SQL agent → supervisor (retry) / wait_approval / respond ----
    workflow.add_conditional_edges(
        "sql_agent",
        route_after_agent,
        {
            "supervisor":     "supervisor",
            "wait_approval":  "wait_approval",
            "respond":        "respond",
            END:              END,
        },
    )

    # ---- ML agent → supervisor (retry) / respond ----
    workflow.add_conditional_edges(
        "ml_agent",
        route_after_agent,
        {
            "supervisor":     "supervisor",
            "wait_approval":  "wait_approval",   # unused but valid
            "respond":        "respond",
            END:              END,
        },
    )

    # ---- wait_approval → sql_agent (execute) / respond (reject) ----
    workflow.add_conditional_edges(
        "wait_approval",
        route_after_approval,
        {
            "sql_agent":  "sql_agent",
            "respond":    "respond",
        },
    )

    # ---- Terminal ----
    workflow.add_edge("respond", END)

    # ---- Compile ----
    checkpointer = checkpointer or MemorySaver()
    return workflow.compile(
        checkpointer=checkpointer,
        # Pause BEFORE wait_approval runs — frontend posts the decision,
        # then we resume via graph.update_state() + graph.invoke(None, ...)
        interrupt_before=["wait_approval"],
    )


# ---------------------------------------------------------------------------
# Module-level singleton for the FastAPI layer to import
# ---------------------------------------------------------------------------
graph = build_graph()
