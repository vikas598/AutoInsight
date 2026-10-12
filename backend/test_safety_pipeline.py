"""
AutoInsight — Smoke test for the Safety Pipeline
==================================================
Exercises every stage with representative SQL statements.
Reads your live Postgres (preview counts come from COUNT(*)), writes to the
audit log, and prints a readable per-case report.

By default, nothing destructive runs — the test calls .assess() but only
calls .execute() when you set EXECUTE_WRITES=1 in the environment:

    # Dry run (default — writes nothing to the DB):
    python test_safety_pipeline.py

    # Actually execute low-risk writes + show the audit log:
    EXECUTE_WRITES=1 python test_safety_pipeline.py

The destructive-sample cases (bulk DELETE / UPDATE) are blocked by the
pipeline anyway, so EXECUTE_WRITES does not run them.
"""

from __future__ import annotations

import os
import uuid

from app.services.audit_log import get_audit_logger
from app.services.safety_pipeline import RISK_THRESHOLD, get_safety_pipeline

BAR = "=" * 72
EXECUTE_WRITES = os.environ.get("EXECUTE_WRITES") == "1"


# ---------------------------------------------------------------------------
# Test cases: (label, sql, expected_decision)
# expected_decision is one of: blocked, needs_approval, auto_approved
# ---------------------------------------------------------------------------
CASES = [
    # ---- Should pass validation and be targeted enough to get executed ----
    (
        "Targeted UPDATE on vehicles by PK",
        "UPDATE vehicles SET status = 'reserved' WHERE id = 1",
        "needs_approval",   # all mutative ops require approval at threshold 30
    ),
    (
        "Single-row INSERT into leads",
        "INSERT INTO leads (customer_id, source, status) VALUES (1, 'website', 'new')",
        "needs_approval",
    ),
    (
        "Targeted DELETE from leads by PK",
        "DELETE FROM leads WHERE id = 1",
        "needs_approval",
    ),

    # ---- High-risk — unbounded DELETE / UPDATE ----
    (
        "Unbounded DELETE (no WHERE)",
        "DELETE FROM leads",
        "needs_approval",
    ),
    (
        "Generic UPDATE on sales (no PK in WHERE)",
        "UPDATE sales SET discount = 10000 WHERE payment_method = 'cash'",
        "needs_approval",
    ),

    # ---- Should be BLOCKED by validation (stages 1-2) ----
    (
        "DROP TABLE — blocked at stage 1",
        "DROP TABLE sales",
        "blocked",
    ),
    (
        "TRUNCATE — blocked at stage 1",
        "TRUNCATE TABLE leads",
        "blocked",
    ),
    (
        "SELECT via write path — blocked at stage 1",
        "SELECT * FROM sales",
        "blocked",
    ),
    (
        "UPDATE non-existent table — blocked at stage 2",
        "UPDATE phantom_table SET x = 1 WHERE id = 1",
        "blocked",
    ),
    (
        "UPDATE existing table + nonexistent column — blocked at stage 2",
        "UPDATE sales s SET s.not_a_column = 1 WHERE s.id = 1",
        "blocked",
    ),
    (
        "Syntax garbage — blocked at stage 1",
        "DELETE WHERE FROM 123",
        "blocked",
    ),
]


def report_case(idx: int, label: str, sql: str, expected: str) -> None:
    print(f"\n{BAR}")
    print(f"[{idx+1:02d}] {label}")
    print(f"  SQL     : {sql}")
    print(f"  Expect  : {expected}")
    print(BAR)

    pipeline = get_safety_pipeline()
    session_id = f"test-{uuid.uuid4().hex[:8]}"

    assessment = pipeline.assess(
        sql, session_id=session_id, user_query=label,
    )

    actual = assessment.decision
    verdict = "PASS" if actual == expected else "FAIL"
    print(f"  Actual  : {actual}         [{verdict}]")

    print(f"  Op      : {assessment.operation} on {assessment.target_table!r}")
    print(f"  Risk    : {assessment.risk_score}/100 (threshold {RISK_THRESHOLD})")
    for k, v in assessment.risk_factors.items():
        print(f"              {k:<22} {v}")

    if assessment.error:
        print(f"  Error   : {assessment.error}")

    if assessment.affected_rows:
        print(f"  Preview : {assessment.affected_rows} row(s) would be affected")
        if assessment.preview_rows:
            print(f"            columns: {assessment.preview_columns}")
            for row in assessment.preview_rows[:3]:
                print(f"            {row}")
            if len(assessment.preview_rows) > 3:
                print(f"            ... {len(assessment.preview_rows) - 3} more")

    # Optionally execute (only for low-risk cases that passed validation)
    if (
        EXECUTE_WRITES
        and actual == "needs_approval"
        and assessment.target_table in ("leads", "inventory_log")
        and assessment.operation == "INSERT"
    ):
        print(f"  EXECUTE : simulating user approval and executing...")
        result = pipeline.execute(
            assessment,
            session_id=session_id,
            user_query=label,
            approved_by="test-script",
        )
        print(f"            executed={result['executed']}, affected={result['affected_rows']}")
        if result.get("error"):
            print(f"            error: {result['error']}")


def main() -> None:
    print(f"\n{BAR}")
    print("SAFETY PIPELINE — SMOKE TEST")
    print(BAR)
    print(f"RISK_THRESHOLD = {RISK_THRESHOLD}")
    print(f"EXECUTE_WRITES = {EXECUTE_WRITES}")
    if not EXECUTE_WRITES:
        print("(set EXECUTE_WRITES=1 to execute low-risk INSERT cases)")

    for idx, (label, sql, expected) in enumerate(CASES):
        try:
            report_case(idx, label, sql, expected)
        except Exception as e:
            print(f"\n  UNEXPECTED CRASH: {type(e).__name__}: {e}")

    print(f"\n{BAR}")
    print("Audit log tail (last 5 entries):")
    print(BAR)
    for entry in get_audit_logger().tail(5):
        print(
            f"  {entry['timestamp']} "
            f"{entry['decision']:<14} "
            f"risk={entry['risk_score']:<3} "
            f"{entry['operation']} {entry['target_table']}  "
            f"({entry['affected_rows']} rows)"
        )

    print(f"\n{BAR}")
    print("Done.")
    print(BAR)


if __name__ == "__main__":
    main()
