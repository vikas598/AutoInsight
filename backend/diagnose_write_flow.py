"""
AutoInsight — Write flow diagnostic
=====================================
Streams the graph node-by-node to show exactly which nodes run and when.
Use this to prove whether wait_approval runs on resume (and if so, what it
returns).

Run from backend/:
    python diagnose_write_flow.py

Reads output. Writes nothing to the DB (sends a rejection, never approves).
"""

from __future__ import annotations

import uuid

from app.graph import build_graph
from app.state import new_state


BAR = "=" * 72


def main() -> None:
    graph = build_graph()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    state = new_state(
        user_query="set vehicle 2 status to reserved",
        session_id=thread_id,
    )

    # ----------------------------------------------------------------
    # FIRST INVOKE — streamed
    # ----------------------------------------------------------------
    print(f"\n{BAR}\nFIRST INVOKE — streaming every node that runs\n{BAR}")
    for i, chunk in enumerate(graph.stream(state, config=config)):
        for node_name, updates in chunk.items():
            print(f"\n  [{i:02d}] NODE: {node_name!r}")
            if isinstance(updates, dict):
                keys_changed = sorted(updates.keys())
                print(f"       returned keys: {keys_changed}")
                for k in ("intent", "requires_approval", "approval_status",
                         "sql_query", "response", "error"):
                    if k in updates:
                        val = updates[k]
                        if isinstance(val, str) and len(val) > 80:
                            val = val[:80] + "..."
                        print(f"       - {k}: {val!r}")
            else:
                print(f"       returned: {type(updates).__name__}")

    # ----------------------------------------------------------------
    # SNAPSHOT at interrupt
    # ----------------------------------------------------------------
    print(f"\n{BAR}\nSTATE SNAPSHOT after first invoke\n{BAR}")
    snap = graph.get_state(config)
    print(f"  next node(s)       : {snap.next}")
    print(f"  requires_approval  : {snap.values.get('requires_approval')}")
    print(f"  approval_status    : {snap.values.get('approval_status')}")
    print(f"  has write_assessment: {bool(snap.values.get('write_assessment'))}")

    # ----------------------------------------------------------------
    # UPDATE STATE with rejection
    # ----------------------------------------------------------------
    print(f"\n{BAR}\nUPDATING STATE to approval_status=rejected\n{BAR}")
    graph.update_state(config, {"approval_status": "rejected",
                                "approved_by": "diag-script"})
    snap = graph.get_state(config)
    print(f"  next node(s) after update : {snap.next}")
    print(f"  approval_status           : {snap.values.get('approval_status')}")

    # ----------------------------------------------------------------
    # RESUME — streamed
    # ----------------------------------------------------------------
    print(f"\n{BAR}\nRESUME (invoke(None)) — streaming every node that runs\n{BAR}")
    ran = []
    for i, chunk in enumerate(graph.stream(None, config=config)):
        for node_name, updates in chunk.items():
            ran.append(node_name)
            print(f"\n  [{i:02d}] NODE: {node_name!r}")
            if isinstance(updates, dict):
                keys_changed = sorted(updates.keys())
                print(f"       returned keys: {keys_changed}")
                for k in ("requires_approval", "approval_status",
                         "response", "query_result", "error"):
                    if k in updates:
                        val = updates[k]
                        if isinstance(val, str) and len(val) > 80:
                            val = val[:80] + "..."
                        print(f"       - {k}: {val!r}")

    print(f"\n{BAR}\nVerdict\n{BAR}")
    print(f"  Nodes that ran on resume: {ran}")
    print(f"  wait_approval ran?       {'YES' if 'wait_approval' in ran else 'NO'}")

    # ----------------------------------------------------------------
    # FINAL STATE
    # ----------------------------------------------------------------
    print(f"\n{BAR}\nFINAL STATE\n{BAR}")
    snap = graph.get_state(config)
    for k in ("requires_approval", "approval_status", "response"):
        v = snap.values.get(k)
        if isinstance(v, str) and len(v) > 150:
            v = v[:150] + "..."
        print(f"  {k:20s}: {v!r}")


if __name__ == "__main__":
    main()