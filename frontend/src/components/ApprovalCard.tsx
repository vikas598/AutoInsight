// ApprovalCard — the Safety Pipeline's assessment of a proposed write, with
// approve / reject controls. Nothing is executed until the server confirms a
// decision; the card stays in place (and usable) if that request fails.

import { Check, ShieldAlert, X } from "lucide-react";
import { DataTable } from "./DataTable";
import { Button } from "./ui/Button";
import { explainFactor, riskBand } from "../lib/actions";
import { plural } from "../lib/format";
import type { Assessment, Decision } from "../types";

interface Props {
  assessment: Assessment;
  onDecide: (decision: Decision) => void;
  /** The decision currently being submitted, if any. */
  submitting: Decision | null;
  /** Any request is in flight (disables both buttons). */
  disabled: boolean;
  error: string | null;
}

const OPERATION_STYLE: Record<string, string> = {
  INSERT: "bg-success-soft text-success",
  UPDATE: "bg-warning-soft text-warning",
  DELETE: "bg-danger-soft text-danger",
};

export function ApprovalCard({ assessment, onDecide, submitting, disabled, error }: Props) {
  const { operation, target_table, risk_score, risk_factors,
          preview_columns, preview_rows, affected_rows, sql } = assessment;

  // This card only appears for writes that require approval, so the badge is
  // never shown as "safe": high risk is red, everything else amber — and the
  // band is always spelled out in text, not conveyed by colour alone.
  const high = risk_score >= 70;
  const band = riskBand(risk_score);

  return (
    <section
      aria-labelledby="approval-heading"
      className="overflow-hidden rounded-card border border-warning/40 bg-surface shadow-card"
    >
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-warning/25 bg-warning-soft px-4 py-3">
        <div className="flex items-start gap-2.5">
          <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-warning" aria-hidden />
          <div>
            <p className="text-2xs font-semibold uppercase tracking-wider text-warning">
              Proposed change · not yet executed
            </p>
            <h3 id="approval-heading" className="mt-0.5 text-[15px] font-semibold text-ink">
              <span className={`mr-1.5 rounded px-1.5 py-0.5 font-mono text-xs ${OPERATION_STYLE[operation] ?? "bg-surface-sunken text-ink-secondary"}`}>
                {operation}
              </span>
              on <code className="font-mono text-[14px]">{target_table}</code>
              <span className="ml-1 font-normal text-ink-secondary">· {plural(affected_rows, "row")} affected</span>
            </h3>
          </div>
        </div>
        <span className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold tabular-nums ${
          high ? "border-danger/30 bg-danger-soft text-danger" : "border-warning/30 bg-surface text-warning"
        }`}>
          {band.label} · {risk_score}/100
        </span>
      </header>

      <div className="space-y-4 px-4 py-4">
        <div>
          <div className="eyebrow mb-1.5">Statement</div>
          <pre className="max-h-48 overflow-auto rounded-control bg-navy-950 px-3.5 py-3 font-mono text-[12px] leading-relaxed text-navy-100">
            <code className="whitespace-pre-wrap break-words">{sql}</code>
          </pre>
        </div>

        {Object.keys(risk_factors ?? {}).length > 0 && (
          <div>
            <div className="eyebrow mb-1.5">Why it needs approval</div>
            <ul className="divide-y divide-line/70 rounded-control border border-line">
              {Object.entries(risk_factors).map(([k, v]) => {
                const f = explainFactor(k, v, assessment);
                return (
                  <li key={k} className="flex items-start justify-between gap-3 px-3 py-2">
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-ink">{f.label}</div>
                      {f.detail && <div className="text-xs text-ink-muted">{f.detail}</div>}
                    </div>
                    <div className="shrink-0 text-right text-sm font-semibold tabular-nums text-ink">
                      +{v}
                      {f.max !== undefined && <span className="ml-0.5 text-2xs font-normal text-ink-muted">/ {f.max}</span>}
                    </div>
                  </li>
                );
              })}
            </ul>
            <p className="mt-1.5 text-2xs text-ink-muted">The risk score is the sum of these points (0–100).</p>
          </div>
        )}

        {preview_columns?.length > 0 && (
          <div>
            <div className="eyebrow mb-1.5">Rows that would be affected</div>
            <div className="overflow-hidden rounded-control border border-line">
              <DataTable
                columns={preview_columns}
                rows={preview_rows ?? []}
                initialRows={5}
                maxHeightClass="max-h-64"
                emptyMessage="No existing rows to preview."
              />
            </div>
          </div>
        )}

        {error && (
          <div role="alert" className="rounded-control border border-danger/30 bg-danger-soft px-3 py-2.5 text-sm text-danger">
            {error}
          </div>
        )}
      </div>

      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-line bg-surface-sunken/60 px-4 py-3">
        <p className="text-xs text-ink-muted">The database is unchanged until you approve.</p>
        <div className="flex gap-2">
          <Button icon={X} onClick={() => onDecide("rejected")} disabled={disabled} aria-busy={submitting === "rejected"}>
            {submitting === "rejected" ? "Rejecting…" : "Reject"}
          </Button>
          <Button variant="primary" icon={Check} onClick={() => onDecide("approved")} disabled={disabled} aria-busy={submitting === "approved"}>
            {submitting === "approved" ? "Applying…" : "Approve & apply"}
          </Button>
        </div>
      </footer>
    </section>
  );
}
