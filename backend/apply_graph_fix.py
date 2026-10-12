"""
Self-applying patch — writes the fixed app/graph.py in place.

Usage (from backend/ folder):
    python apply_graph_fix.py

Then re-run:
    python test_write_flow.py
"""

from __future__ import annotations

import importlib.util
import inspect
import os
import shutil
import sys
from pathlib import Path


NEW_GRAPH_PY = '''"""
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
'''


def main() -> None:
    cwd = Path.cwd()
    target = cwd / "app" / "graph.py"
    backup = cwd / "app" / "graph.py.bak"

    print(f"Current working directory : {cwd}")
    print(f"Target file               : {target}")
    print()

    # Sanity checks
    if not (cwd / "app").is_dir():
        print(f"  ERROR: no 'app/' folder here. Run this script from backend/.")
        sys.exit(1)

    if not target.exists():
        print(f"  ERROR: {target} does not exist. Are you in the right folder?")
        sys.exit(1)

    # Backup
    shutil.copy2(target, backup)
    print(f"Backup written            : {backup}")

    # Write new content
    target.write_text(NEW_GRAPH_PY, encoding="utf-8")
    print(f"New graph.py written      : {len(NEW_GRAPH_PY)} bytes")
    print()

    # Clear bytecode caches
    cleaned = 0
    for p in cwd.rglob("__pycache__"):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
            cleaned += 1
    print(f"Cleaned __pycache__ dirs  : {cleaned}")
    print()

    # Verify by importing and inspecting
    print("Verifying the function Python will load...")
    print("-" * 60)
    spec = importlib.util.find_spec("app.graph")
    if spec is None or spec.origin is None:
        print("  ERROR: can't find app.graph after writing — PYTHONPATH issue?")
        sys.exit(1)

    print(f"  Python will load from   : {spec.origin}")
    print()

    import app.graph as graph_module
    src = inspect.getsource(graph_module.wait_approval_node)
    print("  wait_approval_node source:")
    print("  " + "\\n  ".join(src.splitlines()))
    print()

    if "_handle_approval" in src:
        print("  Fix verified: wait_approval_node now calls _handle_approval.")
    else:
        print("  FIX NOT VISIBLE: Python is loading a different file than it wrote.")
        print(f"  Written to: {target}")
        print(f"  Python loaded from: {spec.origin}")
        print("  → Check whether these paths are the same.")

    print()
    print("Done. Now re-run:  python test_write_flow.py")


if __name__ == "__main__":
    main()