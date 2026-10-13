"""
AutoInsight — End-to-end test for the Visualization Service
=============================================================
Runs 6 queries through the full graph, generates chart configs, and
builds a PDF report containing all of them.

Prerequisites:
    * Steps 1-7 all working
    * pip install reportlab matplotlib

Run from backend/:
    python test_visualization.py
"""

from __future__ import annotations

import uuid
from pathlib import Path

from app.graph import build_graph
from app.services.visualization_service import get_visualization_service
from app.state import new_state


BAR = "=" * 72


QUERIES = [
    "how many sales did we make in 2024?",                        # KPI (1 number)
    "monthly total revenue over the last 2 years",                # time-series line
    "top 5 car models by units sold",                             # bar chart
    "forecast sales for the next 3 months",                       # forecast_line
    "cluster our customers by spending behavior",                 # scatter (cluster)
    "find anomalies in sales transactions",                       # scatter (anomaly)
]


def run_turn(graph, query: str) -> dict:
    """Invoke the graph for one query and return a session entry."""
    print(f"\n{BAR}")
    print(f"Q: {query}")
    print(BAR)

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    state = new_state(user_query=query, session_id=thread_id)
    final = graph.invoke(state, config=config)

    viz_service = get_visualization_service()
    viz_config = viz_service.generate_chart_config(final)

    print(f"  intent     : {final.get('intent')}")
    print(f"  chart_type : {viz_config.get('chart_type')}")
    print(f"  x_key      : {viz_config.get('x_key')}")
    print(f"  y_keys     : {viz_config.get('y_keys')}")
    print(f"  title      : {viz_config.get('title')}")
    print(f"  data points: {len(viz_config.get('data') or [])}")
    if viz_config.get("data"):
        print(f"  first row  : {viz_config['data'][0]}")

    print(f"\n  Response:")
    for line in (final.get("response") or "")[:400].split("\n"):
        print(f"    {line}")

    # Build session entry for the PDF
    qr = final.get("query_result") or {}
    return {
        "user_query": query,
        "response":   final.get("response") or "",
        "sql_query":  final.get("sql_query") or "",
        "viz_config": viz_config,
        "row_count":  qr.get("row_count"),
    }


def main() -> None:
    print(f"{BAR}\nVISUALIZATION SERVICE — SMOKE TEST\n{BAR}")

    graph = build_graph()

    sessions = []
    for q in QUERIES:
        try:
            entry = run_turn(graph, q)
            sessions.append(entry)
        except Exception as e:
            print(f"\n  CRASHED: {type(e).__name__}: {e}")

    # ------------------------------------------------------------
    # Build the PDF
    # ------------------------------------------------------------
    print(f"\n{BAR}")
    print("Building PDF report...")
    print(BAR)
    try:
        output = Path("reports") / "autoinsight-session-report.pdf"
        viz_service = get_visualization_service()
        path = viz_service.build_pdf_report(sessions, output)
        size_kb = path.stat().st_size / 1024
        print(f"  PDF written: {path.resolve()} ({size_kb:.0f} KB)")
    except Exception as e:
        print(f"  PDF build FAILED: {type(e).__name__}: {e}")

    print(f"\n{BAR}\nDone.\n{BAR}")


if __name__ == "__main__":
    main()
