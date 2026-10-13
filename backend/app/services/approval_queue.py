"""
AutoInsight — Approval Queue (read-only view over LangGraph state)
===================================================================
Pending approvals are not stored anywhere new. A write that needs approval
pauses the graph before `wait_approval` (interrupt_before), and the
checkpointer keeps that thread's state. This module simply asks the
checkpointer which threads are currently paused there.

So the queue can never disagree with LangGraph: a thread is "pending" exactly
when resuming it would run the approval handler.

Scope: the checkpointer is MemorySaver (in-process), so the queue covers this
API process only and is emptied by a restart — the same lifetime as the
paused graphs themselves.
"""

from __future__ import annotations

import threading
from typing import Any

WAIT_NODE = "wait_approval"

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def session_lock(session_id: str) -> threading.Lock:
    """One lock per session, so a decision can't be resumed twice concurrently."""
    with _locks_guard:
        return _locks.setdefault(session_id, threading.Lock())


def _config(session_id: str) -> dict:
    return {"configurable": {"thread_id": session_id}}


def pending_state(graph, session_id: str) -> dict[str, Any] | None:
    """
    The paused state for `session_id` if it is awaiting an approval decision,
    else None. "Awaiting" means all of: the graph's next node is
    wait_approval, the write requires approval, its status is still pending,
    and a stored assessment with SQL exists to execute.
    """
    snap = graph.get_state(_config(session_id))
    values = snap.values or {}
    assessment = values.get("write_assessment") or {}
    if (
        tuple(snap.next) == (WAIT_NODE,)
        and values.get("requires_approval")
        and values.get("approval_status") == "pending"
        and assessment.get("sql")
    ):
        return {"snapshot": snap, "values": values, "assessment": assessment}
    return None


def thread_exists(graph, session_id: str) -> bool:
    return bool(graph.get_state(_config(session_id)).values)


def list_pending(graph) -> list[dict[str, Any]]:
    """Every session currently paused for approval, oldest proposal first."""
    thread_ids: list[str] = []
    seen: set[str] = set()
    for cp in graph.checkpointer.list(None):
        tid = cp.config["configurable"]["thread_id"]
        if tid not in seen:
            seen.add(tid)
            thread_ids.append(tid)

    items = []
    for tid in thread_ids:
        p = pending_state(graph, tid)
        if not p:
            continue
        a = p["assessment"]
        items.append({
            "session_id":  tid,
            "proposed_at": p["snapshot"].created_at,
            "user_query":  p["values"].get("user_query", ""),
            "summary":     p["values"].get("response", ""),
            "assessment": {
                "sql":               a.get("sql"),
                "operation":         a.get("operation"),
                "target_table":      a.get("target_table"),
                "risk_score":        a.get("risk_score"),
                "risk_factors":      a.get("risk_factors") or {},
                "requires_approval": a.get("requires_approval", True),
                "preview_columns":   a.get("preview_columns") or [],
                "preview_rows":      a.get("preview_rows") or [],
                "affected_rows":     a.get("affected_rows", 0),
                "decision":          a.get("decision"),
                "error":             a.get("error"),
            },
        })
    items.sort(key=lambda i: i["proposed_at"] or "")
    return items
