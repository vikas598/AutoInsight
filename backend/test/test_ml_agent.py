"""
AutoInsight — End-to-end test for the ML Analytics Agent
==========================================================
Runs all three ML techniques through the full LangGraph:

    Supervisor → ML agent → respond

For each, prints:
    * the LLM-chosen intent
    * the technique's deterministic metrics
    * a preview of chart_data
    * the LLM-generated narrative

Prerequisites:
    * Steps 1-6 all working
    * pip install scikit-learn statsmodels pandas numpy

Run from backend/:
    python test_ml_agent.py
"""

from __future__ import annotations

import uuid

from app.graph import build_graph
from app.state import new_state


BAR = "=" * 72


QUESTIONS = [
    ("forecast sales for the next 3 months",            "ml_forecast"),
    ("predict total revenue for the next quarter",       "ml_forecast"),
    ("cluster our customers by their spending behavior", "ml_cluster"),
    ("find anomalies in sales transactions",             "ml_anomaly"),
    ("detect suspicious sales — any outliers to flag?",  "ml_anomaly"),
]


def run_turn(graph, query: str, expected_intent: str) -> None:
    print(f"\n{BAR}")
    print(f"Q: {query}")
    print(f"Expect intent: {expected_intent}")
    print(BAR)

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    state = new_state(user_query=query, session_id=thread_id)
    result = graph.invoke(state, config=config)

    actual = result.get("intent")
    verdict = "PASS" if actual == expected_intent else "FAIL"
    print(f"\n  intent: {actual}   [{verdict}]")

    if result.get("error"):
        print(f"  error: {result['error']}")
        return

    ml = result.get("ml_result") or {}
    print(f"  technique: {ml.get('technique')}")
    summary = ml.get("summary", {})
    print("  summary:")
    for k, v in summary.items():
        if isinstance(v, float):
            print(f"    {k}: {v:.4f}")
        else:
            print(f"    {k}: {v}")

    metrics = ml.get("metrics", {})
    if metrics:
        print(f"  metrics: {metrics}")

    chart_data = ml.get("chart_data") or []
    if chart_data:
        print(f"  chart_data: {len(chart_data)} point(s), first 3:")
        for row in chart_data[:3]:
            print(f"    {row}")

    print(f"\n  Response:")
    for line in (result.get("response") or "").split("\n"):
        print(f"    {line}")


def main() -> None:
    print(f"{BAR}\nML ANALYTICS AGENT — SMOKE TEST\n{BAR}")

    graph = build_graph()

    for query, intent in QUESTIONS:
        try:
            run_turn(graph, query, intent)
        except Exception as e:
            print(f"\n  CRASHED: {type(e).__name__}: {e}")

    print(f"\n{BAR}\nDone.\n{BAR}")


if __name__ == "__main__":
    main()
