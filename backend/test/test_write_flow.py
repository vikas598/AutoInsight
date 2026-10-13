"""
AutoInsight — End-to-end write-flow smoke test  (with as_node fix)
====================================================================
Fix: graph.update_state() must specify as_node="supervisor" so LangGraph
re-routes through sql_agent on resume instead of auto-advancing past the
wait_approval interrupt.

Run from backend/:
    python test_write_flow.py
"""

from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db import get_connection_manager
from app.graph import build_graph
from app.services.safety_pipeline import RISK_THRESHOLD
from app.state import new_state


BAR = "=" * 72


def section(title: str) -> None:
    print(f"\n{BAR}\n{title}\n{BAR}")


def show_state(state: dict, label: str) -> None:
    print(f"\n--- {label} ---")
    wa = state.get("write_assessment") or {}
    print(f"  intent           : {state.get('intent')}")
    print(f"  sql_query        : {state.get('sql_query')!r}")
    print(f"  operation        : {wa.get('operation')} on {wa.get('target_table')!r}")
    print(f"  risk_score       : {state.get('risk_score')}/100 (threshold {RISK_THRESHOLD})")
    print(f"  affected_rows    : {wa.get('affected_rows')}")
    print(f"  requires_approval: {state.get('requires_approval')}")
    print(f"  approval_status  : {state.get('approval_status')}")
    print(f"  error            : {state.get('error')}")
    if state.get("response"):
        print(f"  response         : {state['response'][:200]}")


def resume_if_paused(graph, config, first_state, decision: str, by: str = "test-script"):
    """
    If paused for approval, post the decision with as_node="supervisor"
    (so LangGraph re-routes to sql_agent instead of auto-advancing to respond),
    then resume with invoke(None).
    """
    if first_state.get("approval_status") == "pending":
        print(f"\n  → Simulating user decision: {decision!r}")
        graph.update_state(
            config,
            {"approval_status": decision, "approved_by": by},
            as_node="supervisor",      # ← THE FIX
        )
        return graph.invoke(None, config=config)
    print(f"\n  → Low risk, auto-approved. No pause.")
    return first_state


# ---------------------------------------------------------------------------
# Case 1 — Low-risk INSERT (auto-approved)
# ---------------------------------------------------------------------------
def test_insert_lead(graph) -> None:
    section("CASE 1 — INSERT a new lead (likely auto-approved)")

    marker = f"test-{uuid.uuid4().hex[:8]}"
    user_query = (
        f"add a new lead for customer 1 interested in vehicle 10 "
        f"from website source, status new, note '{marker}'"
    )

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    state = new_state(user_query=user_query, session_id=thread_id)
    first = graph.invoke(state, config=config)
    show_state(first, "After first invoke")

    final = resume_if_paused(graph, config, first, decision="approved")
    if final is not first:
        show_state(final, "After resume (approved)")

    qr = final.get("query_result") or {}
    print(f"\n  Rows affected: {qr.get('row_count')}")

    engine = get_connection_manager().read_engine
    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM leads WHERE notes LIKE :m"),
            {"m": f"%{marker}%"},
        ).scalar()
    print(f"  Verified rows in DB tagged with marker '{marker}': {count}")
    print(f"  Verdict: {'PASS' if count == 1 else 'FAIL — lead not persisted'}")


# ---------------------------------------------------------------------------
# Case 2 — UPDATE vehicle, REJECT
# ---------------------------------------------------------------------------
def test_reject_update(graph) -> None:
    section("CASE 2 — UPDATE vehicle status (pauses), REJECT")

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    engine = get_connection_manager().read_engine
    with engine.connect() as conn:
        before = conn.execute(text("SELECT status FROM vehicles WHERE id = 2")).scalar()
    print(f"\n  Before: vehicles.id=2 status = {before!r}")

    state = new_state(user_query="set vehicle 2 status to reserved", session_id=thread_id)
    first = graph.invoke(state, config=config)
    show_state(first, "After first invoke")

    final = resume_if_paused(graph, config, first, decision="rejected")
    if final is not first:
        show_state(final, "After resume (rejected)")

    with engine.connect() as conn:
        after = conn.execute(text("SELECT status FROM vehicles WHERE id = 2")).scalar()
    print(f"\n  After:  vehicles.id=2 status = {after!r}")
    print(f"  Verdict: {'PASS' if after == before else 'FAIL — mutated after rejection'}")


# ---------------------------------------------------------------------------
# Case 3 — Bulk DELETE, REJECT
# ---------------------------------------------------------------------------
def test_reject_bulk_delete(graph) -> None:
    section("CASE 3 — DELETE all lost leads (high risk), REJECT")

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    engine = get_connection_manager().read_engine
    with engine.connect() as conn:
        before = conn.execute(text("SELECT COUNT(*) FROM leads")).scalar()
    print(f"\n  Before: total leads = {before}")

    state = new_state(user_query="delete all leads with status 'lost'", session_id=thread_id)
    first = graph.invoke(state, config=config)
    show_state(first, "After first invoke")

    final = resume_if_paused(graph, config, first, decision="rejected")
    if final is not first:
        show_state(final, "After resume (rejected)")

    with engine.connect() as conn:
        after = conn.execute(text("SELECT COUNT(*) FROM leads")).scalar()
    print(f"\n  After:  total leads = {after}")
    print(f"  Verdict: {'PASS' if after == before else 'FAIL — leads deleted after rejection'}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print(f"{BAR}\nSQL AGENT — WRITE FLOW END-TO-END TEST\n{BAR}")
    print(f"RISK_THRESHOLD = {RISK_THRESHOLD}")

    graph = build_graph()

    for fn in (test_insert_lead, test_reject_update, test_reject_bulk_delete):
        try:
            fn(graph)
        except Exception as e:
            print(f"\n  {fn.__name__} CRASHED: {type(e).__name__}: {e}")

    section("Audit log tail (last 10 entries)")
    from app.services.audit_log import get_audit_logger
    for e in get_audit_logger().tail(10):
        approved = e.get("approved_by") or "—"
        print(
            f"  {e['timestamp'][:19]}  "
            f"{e['decision']:<14} risk={e['risk_score']:<3} "
            f"{e['operation']} {e['target_table']}  "
            f"affected={e['affected_rows']}  by={approved}"
        )

    print(f"\n{BAR}\nDone.\n{BAR}")


if __name__ == "__main__":
    main()