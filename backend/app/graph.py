"""
AutoInsight — LangGraph StateGraph  (approval handling inline in wait_approval)
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents import ml_agent_node, sql_agent_node, supervisor_node
from app.agents.sql_agent import _handle_approval
from app.routing import route_after_agent, route_from_supervisor
from app.state import AutoInsightState


def respond_node(state: AutoInsightState) -> dict:
    """Terminal node — the response is already in state."""
    return {"response": state.get("response") or "No response generated."}


def wait_approval_node(state: AutoInsightState) -> dict:
    """
    Resume point for the approval interrupt.
    Reads approval_status (set by graph.update_state before resume) and
    calls _handle_approval directly, which audits + updates state.
    """
    status = state.get("approval_status")
    if status in ("approved", "rejected"):
        return _handle_approval(state)
    return {}


def _after_wait_approval(_state: AutoInsightState) -> str:
    return "respond"


def build_graph(checkpointer=None):
    workflow = StateGraph(AutoInsightState)

    workflow.add_node("supervisor",    supervisor_node)
    workflow.add_node("sql_agent",     sql_agent_node)
    workflow.add_node("ml_agent",      ml_agent_node)
    workflow.add_node("wait_approval", wait_approval_node)
    workflow.add_node("respond",       respond_node)

    workflow.add_edge(START, "supervisor")

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
    workflow.add_conditional_edges(
        "sql_agent",
        route_after_agent,
        {
            "supervisor":    "supervisor",
            "wait_approval": "wait_approval",
            "respond":       "respond",
            END:             END,
        },
    )
    workflow.add_conditional_edges(
        "ml_agent",
        route_after_agent,
        {
            "supervisor":    "supervisor",
            "wait_approval": "wait_approval",
            "respond":       "respond",
            END:             END,
        },
    )
    workflow.add_conditional_edges(
        "wait_approval",
        _after_wait_approval,
        {"respond": "respond"},
    )

    workflow.add_edge("respond", END)

    checkpointer = checkpointer or MemorySaver()
    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["wait_approval"],
    )


graph = build_graph()
