"""
AutoInsight — Test for the Action Center backend
=================================================
Exercises the real approval path through the HTTP API:

  1. GET /api/approvals/pending reads paused writes from the LangGraph
     checkpointer, with the same assessment the chat response carried.
  2. Rejecting resumes the graph (update_state as_node="supervisor" +
     invoke(None)), audits "rejected", leaves the database unchanged and
     removes the item from the queue.
  3. A second decision on an already-decided session is refused (409) and
     executes nothing — previously it would have re-run the write.
  4. Two simultaneous approvals for one session: exactly one executes.
  5. Unknown session -> 404; invalid decision -> 400.

Database impact: the only write that is approved is a no-op — setting
vehicle 1 (already 'reserved') to 'reserved'. It is approved only if the
proposed SQL is exactly that single-row UPDATE; otherwise it is rejected.
The DB trigger refreshes that row's updated_at. Each run appends audit lines.

Requires a configured LLM and the database. Run from backend/:
    python test/test_action_center.py
"""

from __future__ import annotations

import re
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.main import app
from app.db import get_connection_manager
from app.services.audit_log import get_audit_logger

BAR = "=" * 72
failures: list[str] = []
client = TestClient(app)


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{' - ' + detail if detail else ''}")
    if not ok:
        failures.append(name)


def status_of(vehicle_id: int) -> str:
    with get_connection_manager().read_engine.connect() as c:
        return c.execute(text("SELECT status FROM vehicles WHERE id = :i"), {"i": vehicle_id}).scalar_one()


def audit_count() -> int:
    return len(list(get_audit_logger().iterate()))


def pending_ids() -> list[str]:
    r = client.get("/api/approvals/pending")
    assert r.status_code == 200, r.text
    return [p["session_id"] for p in r.json()["pending"]]


def propose(question: str) -> dict:
    r = client.post("/api/chat", json={"session_id": None, "user_query": question})
    assert r.status_code == 200, r.text
    return r.json()


def main() -> int:
    print(BAR, "\nAction Center - approval queue and decision guard\n", BAR, sep="")

    print("\nQueue starts empty in a fresh process")
    check("no pending approvals", pending_ids() == [])

    # ---- 1 + 2: propose, list, reject ----
    print("\nPropose a change to vehicle 2, then reject it")
    before_status = status_of(2)
    res = propose("Set the status of vehicle 2 to reserved")
    sid = res["session_id"]
    check("chat paused for approval", res["status"] == "needs_approval", res["status"])

    pending = client.get("/api/approvals/pending").json()["pending"]
    item = next((p for p in pending if p["session_id"] == sid), None)
    check("session listed as pending", item is not None)
    if item:
        a, b = item["assessment"], res["assessment"]
        same = all(a[k] == b[k] for k in ("sql", "operation", "target_table", "risk_score", "risk_factors", "affected_rows"))
        check("listed assessment equals chat assessment", same, f"{a['operation']} {a['target_table']} risk {a['risk_score']}")
        check("user question carried", item["user_query"] == "Set the status of vehicle 2 to reserved")
        check("proposed_at present", bool(item["proposed_at"]))

    n_audit = audit_count()
    r = client.post(f"/api/approve/{sid}", json={"decision": "rejected", "approved_by": "test-action-center"})
    check("reject -> 200", r.status_code == 200, r.text[:120] if r.status_code != 200 else "")
    check("reject response says rejected", "rejected" in (r.json().get("response") or "").lower())
    check("database unchanged", status_of(2) == before_status, status_of(2))
    tail = get_audit_logger().tail(1)[0]
    check("one audit line: rejected, not executed",
          audit_count() == n_audit + 1 and tail["decision"] == "rejected" and tail["executed"] is False and tail["session_id"] == sid)
    check("removed from queue", sid not in pending_ids())

    # ---- 3: repeated decision refused ----
    print("\nA second decision on the decided session")
    n_audit = audit_count()
    r = client.post(f"/api/approve/{sid}", json={"decision": "approved", "approved_by": "test-action-center"})
    check("second decision -> 409", r.status_code == 409, r.json().get("detail", ""))
    check("nothing executed or audited", audit_count() == n_audit and status_of(2) == before_status)

    # ---- 4: concurrent approvals execute once ----
    print("\nTwo simultaneous approvals for one session (no-op change)")
    res = propose("Set the status of vehicle 1 to reserved")
    sid = res["session_id"]
    a = res.get("assessment") or {}
    sql = re.sub(r"\s+", " ", (a.get("sql") or "")).strip().lower()
    is_noop = (
        res["status"] == "needs_approval"
        and a.get("operation") == "UPDATE" and a.get("target_table") == "vehicles"
        and a.get("affected_rows") == 1
        and re.fullmatch(r"update vehicles set status = 'reserved' where (vehicles\.)?id = 1;?", sql) is not None
        and status_of(1) == "reserved"
    )
    check("proposal is the expected no-op UPDATE", is_noop, a.get("sql", res["status"]))

    decision = "approved" if is_noop else "rejected"
    n_audit = audit_count()
    codes: list[int] = []
    barrier = threading.Barrier(2)

    def decide():
        barrier.wait()
        codes.append(client.post(f"/api/approve/{sid}", json={"decision": decision, "approved_by": "test-action-center"}).status_code)

    threads = [threading.Thread(target=decide) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    check("exactly one 200 and one 409", sorted(codes) == [200, 409], str(sorted(codes)))
    check("exactly one audit line", audit_count() == n_audit + 1)
    tail = get_audit_logger().tail(1)[0]
    if is_noop:
        check("approved + executed, 1 row", tail["decision"] == "approved" and tail["executed"] is True and tail["affected_rows"] == 1)
        check("vehicle 1 still reserved", status_of(1) == "reserved")

    # ---- 5: validation ----
    print("\nValidation")
    r = client.post("/api/approve/does-not-exist", json={"decision": "approved"})
    check("unknown session -> 404", r.status_code == 404)
    r = client.post(f"/api/approve/{sid}", json={"decision": "maybe"})
    check("invalid decision -> 400", r.status_code == 400)
    check("queue empty again", pending_ids() == [])

    print("\n" + BAR)
    print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
