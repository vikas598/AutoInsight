"""
AutoInsight — Smoke test for the SQL Agent read path
======================================================
Runs the full generate → validate → execute → narrate pipeline against
your live Postgres + Groq LLM.

Prerequisites:
  * Postgres running, autoinsight DB seeded (Steps 1-6 of DB setup)
  * .env configured with DATABASE_URL_READ and LLM credentials
  * All backend deps installed:  pip install -r requirements.txt

Run from the backend/ directory:
    python test_sql_agent.py
"""

from __future__ import annotations

import time

from app.agents.sql_agent import sql_agent_node
from app.services.schema_service import get_schema_service
from app.state import new_state

BAR = "=" * 72


# A spread of question types — simple counts, aggregates, joins, time filters,
# top-N, grouping. Exercises every clause the LLM needs to emit.
TEST_QUESTIONS = [
    "how many total sales did we make in 2024?",
    "what is total revenue from vehicle sales in March 2024?",
    "which 5 car models sold the most units overall?",
    "list the top 10 customers by total amount spent",
    "which salespersons closed the most deals in the last 90 days?",
    "what is the average service cost by service_type, sorted highest first?",
    "break down lead conversion rate by source",
    "how many vehicles are currently available vs sold vs reserved?",
    "find the single most expensive sale ever recorded",
]


def run_turn(question: str) -> None:
    print(f"\n{BAR}")
    print(f"Q: {question}")
    print(BAR)

    state = new_state(user_query=question, session_id="test")
    state["intent"] = "sql_read"       # bypassing supervisor for this test

    t0 = time.perf_counter()
    result = sql_agent_node(state)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    sql = result.get("sql_query", "")
    if sql:
        print("\nGenerated SQL:")
        for line in sql.split("\n"):
            print(f"  {line}")

    if result.get("error"):
        print(f"\n  ERROR: {result['error']}")
        print(f"  Elapsed: {elapsed_ms:.0f} ms")
        return

    qr = result.get("query_result", {})
    rows = qr.get("rows", [])
    cols = qr.get("columns", [])

    print(f"\nResult: {qr.get('row_count', 0)} row(s), {len(cols)} column(s)")
    if cols:
        print(f"  columns: {cols}")
    for row in rows[:5]:
        print(f"  {row}")
    if len(rows) > 5:
        print(f"  ... {len(rows) - 5} more rows")

    print(f"\nAnswer: {result.get('response', '')}")
    print(f"\n  (round-trip: {elapsed_ms:.0f} ms)")


def main() -> None:
    print(f"{BAR}")
    print("SQL AGENT — READ PATH SMOKE TEST")
    print(BAR)

    # Warm the schema cache once so subsequent timings reflect agent cost only
    print("\nPre-warming schema cache...")
    svc = get_schema_service()
    schema = svc.introspect()
    print(f"  Cached {schema.table_count} tables, {schema.total_rows:,} rows total.")

    for q in TEST_QUESTIONS:
        try:
            run_turn(q)
        except Exception as e:
            print(f"\n  UNEXPECTED CRASH: {type(e).__name__}: {e}")

    print(f"\n{BAR}")
    print("All test cases attempted.")
    print(BAR)


if __name__ == "__main__":
    main()
