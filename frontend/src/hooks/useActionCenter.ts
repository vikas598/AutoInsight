// useActionCenter — pending approvals and audit entries for the Action Center.
//
// * Pending approvals come from GET /api/approvals/pending (read from the
//   LangGraph checkpointer). Audit entries from GET /api/audit?limit=N.
// * Loaded each time the page is opened, on Refresh, and after a decision.
//   No polling.
// * Decisions go through POST /api/approve/{session_id}. When the proposal
//   belongs to this tab's AI Analyst conversation, the caller routes the
//   decision through the Analyst session instead, so both views stay in step.

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, errorMessage } from "../api";
import type { AuditEntry, ChatResponse, Decision, PendingApproval } from "../types";
import type { Load } from "./useOverview";
import type { DecisionResult } from "./useAnalystSession";

export const AUDIT_LIMITS = [25, 50, 100, 200] as const;   // server caps at 200
export type AuditLimit = (typeof AUDIT_LIMITS)[number];

/** Outcome of the last decision made from the Action Center. */
export type DecisionFeedback =
  | { kind: "done"; sessionId: string; decision: Decision; response: ChatResponse; operation: string; table: string }
  | { kind: "conflict"; sessionId: string; message: string }
  | { kind: "failed"; sessionId: string; message: string };

const isAbort = (e: unknown) => e instanceof DOMException && e.name === "AbortError";

interface Options {
  enabled: boolean;
  /** Decide via the AI Analyst when the session is its open proposal. */
  analystDecide: (sessionId: string, decision: Decision) => Promise<DecisionResult> | null;
}

export function useActionCenter({ enabled, analystDecide }: Options) {
  const [pending, setPending] = useState<Load<PendingApproval[]>>({ status: "idle" });
  const [audit, setAudit] = useState<Load<AuditEntry[]>>({ status: "idle" });
  const [limit, setLimit] = useState<AuditLimit>(50);
  const [reloadKey, setReloadKey] = useState(0);
  const [deciding, setDeciding] = useState<{ sessionId: string; decision: Decision } | null>(null);
  const [feedback, setFeedback] = useState<DecisionFeedback | null>(null);
  const decidingRef = useRef(false);

  useEffect(() => {
    if (!enabled) return;
    const ctrl = new AbortController();
    const keep = <T,>(prev: Load<T>): Load<T> =>
      prev.status === "ready" ? { ...prev, refreshing: true } : { status: "loading" };

    setPending(keep);
    api.pendingApprovals(ctrl.signal)
      .then((r) => setPending({ status: "ready", data: r.pending, refreshing: false }))
      .catch((e) => { if (!isAbort(e)) setPending({ status: "error", message: errorMessage(e) }); });

    setAudit(keep);
    api.audit(limit, ctrl.signal)
      .then((r) => setAudit({ status: "ready", data: r.entries, refreshing: false }))
      .catch((e) => { if (!isAbort(e)) setAudit({ status: "error", message: errorMessage(e) }); });

    return () => ctrl.abort();
  }, [enabled, limit, reloadKey]);

  const refresh = useCallback(() => setReloadKey((k) => k + 1), []);

  const decide = useCallback(async (item: PendingApproval, decision: Decision) => {
    if (decidingRef.current) return;                    // one decision at a time
    decidingRef.current = true;
    setDeciding({ sessionId: item.session_id, decision });
    setFeedback(null);

    const meta = { sessionId: item.session_id, operation: item.assessment.operation, table: item.assessment.target_table };
    try {
      const viaAnalyst = analystDecide(item.session_id, decision);
      if (viaAnalyst) {
        const r = await viaAnalyst;
        setFeedback(r.ok
          ? { kind: "done", decision, response: r.response, ...meta }
          : r.alreadyDecided
            ? { kind: "conflict", sessionId: item.session_id, message: r.message }
            : { kind: "failed", sessionId: item.session_id, message: r.message });
      } else {
        const response = await api.approve(item.session_id, decision);
        setFeedback({ kind: "done", decision, response, ...meta });
      }
    } catch (e) {
      setFeedback(e instanceof ApiError && e.status === 409
        ? { kind: "conflict", sessionId: item.session_id, message: e.message }
        : { kind: "failed", sessionId: item.session_id, message: errorMessage(e) });
    } finally {
      decidingRef.current = false;
      setDeciding(null);
      refresh();                                        // queue + audit reflect the server
    }
  }, [analystDecide, refresh]);

  const busy =
    pending.status === "loading" || audit.status === "loading" ||
    (pending.status === "ready" && pending.refreshing) || (audit.status === "ready" && audit.refreshing);

  return {
    pending, audit, limit, setLimit, refresh, busy,
    decide, deciding, feedback, dismissFeedback: () => setFeedback(null),
  };
}

export type ActionCenterState = ReturnType<typeof useActionCenter>;
