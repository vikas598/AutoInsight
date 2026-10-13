// API client — thin wrapper over fetch. Endpoints and payloads mirror
// backend/app/api/main.py exactly; this layer only adds readable errors.

import type { AuditEntry, ChatResponse, OverviewResponse, PendingApproval, ReportInfo } from "./types";

/** A failed request. `status` is 0 when the server could not be reached. */
export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, init);
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError("Can't reach the AutoInsight server. Check that the backend is running.", 0);
  }
  if (!res.ok) {
    // FastAPI errors arrive as {"detail": "..."}; fall back to the status line
    let detail = "";
    try {
      const body = await res.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail ?? "");
    } catch { /* non-JSON body */ }
    throw new ApiError(detail || `${res.status} ${res.statusText}`, res.status);
  }
  return res.json();
}

const post = <T>(url: string, body: unknown) =>
  request<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const api = {
  chat: (sessionId: string | null, userQuery: string) =>
    post<ChatResponse>("/api/chat", {
      session_id: sessionId,
      user_query: userQuery,
    }),

  approve: (sessionId: string, decision: "approved" | "rejected", approvedBy = "user") =>
    post<ChatResponse>(`/api/approve/${sessionId}`, {
      decision,
      approved_by: approvedBy,
    }),

  buildReport: (sessionId: string) => post<ReportInfo>(`/api/report/${sessionId}`, {}),

  health: () => request<{ status: string }>("/api/health"),

  /** Deterministic dashboard aggregates; `period` is a year or "all". */
  overview: (period: string | null, signal?: AbortSignal) =>
    request<OverviewResponse>(
      period ? `/api/dashboard/overview?period=${encodeURIComponent(period)}` : "/api/dashboard/overview",
      { signal },
    ),

  audit: (limit: number, signal?: AbortSignal) =>
    request<{ entries: AuditEntry[]; count: number }>(`/api/audit?limit=${limit}`, { signal }),

  /** Writes currently paused for a decision, across all sessions in this API process. */
  pendingApprovals: (signal?: AbortSignal) =>
    request<{ pending: PendingApproval[]; count: number }>("/api/approvals/pending", { signal }),
};

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
