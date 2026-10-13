// Helpers for the Action Center: plain-language descriptions of proposed
// changes, risk factors and audit outcomes. Everything is derived from
// fields the backend returns; rules mirror backend/app/services/safety_pipeline.py.

import type { Assessment, AuditEntry } from "../types";
import { humanize, plural } from "./format";

/** "Delete 156 rows from leads" */
export function describeChange(a: Pick<Assessment, "operation" | "target_table" | "affected_rows">): string {
  const rows = plural(a.affected_rows ?? 0, "row");
  switch (a.operation) {
    case "INSERT": return `Add ${rows} to ${a.target_table}`;
    case "UPDATE": return `Update ${rows} in ${a.target_table}`;
    case "DELETE": return `Delete ${rows} from ${a.target_table}`;
    default:       return `${a.operation} on ${a.target_table} (${rows})`;
  }
}

// ---- Risk factors (safety_pipeline._score_risk) ----

const FACTOR_MAX: Record<string, number> = { op: 40, table_sensitivity: 25, where_specificity: 20, estimated_rows: 15 };

export function explainFactor(key: string, points: number, a?: Pick<Assessment, "operation" | "target_table" | "affected_rows">): { label: string; detail: string; max?: number } {
  switch (key) {
    case "op":
    case "operation":
      return {
        label: "Type of change",
        detail: a ? `${a.operation} — deletes score highest, then updates, then inserts` : "Deletes score highest, then updates, then inserts",
        max: 40,
      };
    case "table_sensitivity":
      return {
        label: "Table sensitivity",
        detail: a ? `${a.target_table} is rated ${points >= 25 ? "highly" : points >= 15 ? "moderately" : "less"} sensitive` : "How sensitive the affected table is",
        max: 25,
      };
    case "where_specificity":
      return {
        label: "How rows are targeted",
        detail: points >= 20 ? "No row filter — would affect every row"
          : points >= 10 ? "Filtered by a condition, not by specific record IDs"
          : a?.operation === "INSERT" ? "Not applicable to new rows"
          : "Targets specific record IDs",
        max: 20,
      };
    case "estimated_rows":
      return {
        label: "Rows affected",
        detail: a ? `${plural(a.affected_rows ?? 0, "row")} — more rows score higher` : "More rows score higher",
        max: 15,
      };
    default:
      return { label: humanize(key), detail: "", max: FACTOR_MAX[key] };
  }
}

export type RiskBand = "high" | "elevated" | "low";

/** Text label + band; colour is never the only signal. */
export function riskBand(score: number): { band: RiskBand; label: string } {
  if (score >= 70) return { band: "high", label: "High risk" };
  if (score >= 30) return { band: "elevated", label: "Elevated risk" };
  return { band: "low", label: "Low risk" };
}

// ---- Audit outcomes (audit_log.py / safety_pipeline.execute & reject) ----

export type OutcomeGroup = "executed" | "rejected" | "blocked" | "failed" | "other";

export interface Outcome {
  group: OutcomeGroup;
  /** Short status, e.g. "Executed". */
  label: string;
  /** How it got there, e.g. "Approved by user" / "Auto-approved (low risk)". */
  detail: string;
}

/**
 * Approval and execution are separate facts: `decision` records who/what
 * allowed it; `executed` records whether a COMMIT happened.
 */
export function outcomeOf(e: AuditEntry): Outcome {
  const by = e.approved_by ? `Approved by ${e.approved_by}` : "Auto-approved (low risk)";
  switch (e.decision) {
    case "auto_approved":
    case "approved":
      return e.executed
        ? { group: "executed", label: "Executed", detail: e.decision === "approved" ? `Approved by ${e.approved_by ?? "unknown"}` : "Auto-approved (low risk)" }
        : { group: "failed", label: "Not executed", detail: by };
    case "rejected":
      return { group: "rejected", label: "Rejected", detail: e.approved_by ? `Rejected by ${e.approved_by} · not executed` : "Not executed" };
    case "blocked":
      return { group: "blocked", label: "Blocked", detail: "Stopped by safety checks · not executed" };
    case "error":
      return { group: "failed", label: "Execution failed", detail: `${by} · database returned an error` };
    default:
      return { group: "other", label: humanize(String(e.decision)), detail: e.executed ? "Executed" : "Not executed" };
  }
}
