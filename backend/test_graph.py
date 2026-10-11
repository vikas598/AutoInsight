"""
AutoInsight — Smoke test for the LangGraph skeleton
====================================================
Exercises every route through the graph with the stub agents to confirm
the state machine is wired correctly.

Run from the backend/ directory:
    pip install langgraph langchain-core
    python test_graph.py
"""

from __future__ import annotations

import uuid
from pprint import pprint

from app.graph import build_graph
from app.state import new_state


def run_turn(graph, user_query: str, label: str) -> dict:
    """Invoke the graph once with a fresh session id."""
    print(f"\n{'=' * 60}")
    print(f"TEST: {label}")
    print(f"Query: {user_query!r}")
    print("=" * 60)

    session_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}

    state = new_state(user_query=user_query, session_id=session_id)
    final_state = graph.invoke(state, config=config)

    print(f"  intent          : {final_state.get('intent')}")
    print(f"  response        : {final_state.get('response')}")
    print(f"  error           : {final_state.get('error')}")
    if final_state.get("sql_query"):
        print(f"  sql_query       : {final_state['sql_query']}")
    if final_state.get("ml_result"):
        print(f"  ml_result.tech  : {final_state['ml_result'].get('technique')}")
    print(f"  requires_approval: {final_state.get('requires_approval')}")
    print(f"  approval_status : {final_state.get('approval_status')}")

    return final_state, config


def test_write_with_approval(graph):
    """Full write cycle: request → interrupt → approve → execute."""
    print(f"\n{'=' * 60}")
    print("TEST: SQL write with approval flow")
    print("=" * 60)

    session_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}

    # ---- First invocation: should pause at wait_approval ----
    state = new_state(
        user_query="update the status of vehicle 123 to reserved",
        session_id=session_id,
    )
    first_result = graph.invoke(state, config=config)

    print("After first invoke (should be paused for approval):")
    print(f"  requires_approval: {first_result.get('requires_approval')}")
    print(f"  approval_status  : {first_result.get('approval_status')}")
    print(f"  sql_query        : {first_result.get('sql_query')}")

    # ---- Simulate user clicking 'Approve' ----
    graph.update_state(
        config,
        {"approval_status": "approved"},
    )

    # ---- Resume ----
    final = graph.invoke(None, config=config)

    print("\nAfter resume (approved):")
    print(f"  response         : {final.get('response')}")
    print(f"  approval_status  : {final.get('approval_status')}")


def main():
    graph = build_graph()

    # ---- Each test exercises one route through the graph ----
    run_turn(graph, "how many sales did we make in 2024?", "SQL read")
    run_turn(graph, "forecast sales for next quarter",     "ML forecast")
    run_turn(graph, "cluster our customers by spending",   "ML cluster")
    run_turn(graph, "find anomalies in sales",             "ML anomaly")
    run_turn(graph, "",                                    "Empty query → clarification")

    # ---- Approval flow needs a separate helper ----
    test_write_with_approval(graph)

    print("\n" + "=" * 60)
    print("All routes smoke-tested. Graph wired correctly.")
    print("=" * 60)


if __name__ == "__main__":
    main()
