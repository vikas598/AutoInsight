// PendingApprovals — the approval queue (left) and the focused review panel
// (right). Items come from GET /api/approvals/pending; a decision removes an
// item only after the server confirms it and the queue is reloaded.

import { useEffect, useState } from "react";
import { MessageSquare, ShieldAlert } from "lucide-react";
import { ApprovalCard } from "../ApprovalCard";
import { describeChange, riskBand } from "../../lib/actions";
import { plural } from "../../lib/format";
import type { ActionCenterState } from "../../hooks/useActionCenter";
import type { Decision, PendingApproval } from "../../types";
import { ConfirmDialog } from "./ConfirmDialog";

const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—";

interface Props {
  state: ActionCenterState;
  /** Session id of this tab's AI Analyst conversation, if any. */
  analystSessionId: string | null;
}

export function PendingApprovals({ state, analystSessionId }: Props) {
  const { pending, deciding } = state;
  const items = pending.status === "ready" ? pending.data : [];
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Keep a valid selection as the queue changes
  useEffect(() => {
    if (!items.length) setSelectedId(null);
    else if (!items.some((i) => i.session_id === selectedId)) setSelectedId(items[0].session_id);
  }, [items, selectedId]);

  const selected = items.find((i) => i.session_id === selectedId) ?? null;

  return (
    <section aria-labelledby="pending-heading">
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 id="pending-heading" className="text-base font-semibold text-ink">Awaiting approval</h2>
          <p className="text-xs text-ink-muted">
            Changes the AI Analyst has prepared and paused for a decision. Nothing runs until it is approved.
          </p>
        </div>
      </header>

      {pending.status === "loading" || pending.status === "idle" ? (
        <div className="card h-40 animate-pulse" aria-hidden />
      ) : pending.status === "error" ? (
        <p role="alert" className="card px-5 py-4 text-sm text-danger">Pending approvals could not be loaded. {pending.message}</p>
      ) : items.length === 0 ? (
        <div className="card px-5 py-8 text-center">
          <ShieldAlert className="mx-auto h-7 w-7 text-ink-muted" aria-hidden />
          <p className="mt-2 text-sm font-medium text-ink">Nothing is waiting for approval</p>
          <p className="mx-auto mt-1 max-w-md text-xs text-ink-muted">
            When a request in the AI Analyst would change data and needs review, it appears here.
            Only proposals made since the server last started are tracked.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
          <ul className="space-y-2 lg:col-span-2" aria-label="Pending changes">
            {items.map((i) => {
              const r = riskBand(i.assessment.risk_score);
              const active = i.session_id === selectedId;
              return (
                <li key={i.session_id}>
                  <button
                    type="button"
                    aria-pressed={active}
                    onClick={() => setSelectedId(i.session_id)}
                    className={`focus-ring w-full rounded-card border bg-surface p-3.5 text-left transition-colors ${
                      active ? "border-primary shadow-raised ring-1 ring-primary" : "border-line shadow-card hover:border-line-strong"
                    }`}
                  >
                    <span className="flex items-start justify-between gap-2">
                      <span className="text-sm font-semibold text-ink">{describeChange(i.assessment)}</span>
                      <span className={`shrink-0 rounded-full border px-2 py-0.5 text-2xs font-semibold ${
                        r.band === "high" ? "border-danger/30 bg-danger-soft text-danger" : "border-warning/30 bg-warning-soft text-warning"
                      }`}>
                        {r.label} · {i.assessment.risk_score}
                      </span>
                    </span>
                    {i.user_query && <span className="mt-1 block truncate text-xs text-ink-secondary">“{i.user_query}”</span>}
                    <span className="mt-1.5 flex flex-wrap items-center gap-x-2 text-2xs text-ink-muted">
                      <span>Proposed {when(i.proposed_at)}</span>
                      {i.session_id === analystSessionId && (
                        <span className="inline-flex items-center gap-1 font-medium text-primary">
                          <MessageSquare className="h-3 w-3" aria-hidden /> Your current AI Analyst conversation
                        </span>
                      )}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>

          <div className="min-w-0 lg:col-span-3">
            {selected && (
              <ReviewPanel
                key={selected.session_id}
                item={selected}
                fromAnalyst={selected.session_id === analystSessionId}
                submitting={deciding?.sessionId === selected.session_id ? deciding.decision : null}
                disabled={deciding !== null}
                onDecide={(d) => state.decide(selected, d)}
              />
            )}
          </div>
        </div>
      )}
    </section>
  );
}

interface ReviewProps {
  item: PendingApproval;
  fromAnalyst: boolean;
  submitting: Decision | null;
  disabled: boolean;
  onDecide: (d: Decision) => void;
}

function ReviewPanel({ item, fromAnalyst, submitting, disabled, onDecide }: ReviewProps) {
  const a = item.assessment;
  const [confirming, setConfirming] = useState(false);
  const [ack, setAck] = useState(false);

  // Destructive or broad changes need an explicit acknowledgement
  const noFilter = (a.risk_factors?.where_specificity ?? 0) >= 20;
  const needsAck = a.operation === "DELETE" || noFilter || a.affected_rows > 10;

  const request = (d: Decision) => {
    if (d === "rejected") onDecide(d);       // rejecting changes nothing
    else { setAck(false); setConfirming(true); }
  };

  return (
    <article aria-labelledby="review-heading" className="space-y-3">
      <div className="card px-5 py-4">
        <p className="eyebrow">Review</p>
        <h3 id="review-heading" className="mt-1 text-lg font-semibold text-ink">{describeChange(a)}</h3>
        {item.user_query && (
          <p className="mt-1 text-sm text-ink-secondary">
            Requested as: <q className="text-ink">{item.user_query}</q>
          </p>
        )}
        <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs">
          <div><dt className="inline text-ink-muted">Proposed </dt><dd className="inline text-ink">{when(item.proposed_at)}</dd></div>
          <div>
            <dt className="inline text-ink-muted">Reference </dt>
            <dd className="inline font-mono text-ink" title={item.session_id}>{item.session_id.slice(0, 8)}</dd>
          </div>
          {fromAnalyst && <div className="font-medium text-primary">From your current AI Analyst conversation</div>}
        </dl>
      </div>

      <ApprovalCard
        assessment={a}
        onDecide={request}
        submitting={submitting}
        disabled={disabled}
        error={null}
      />

      <ConfirmDialog
        open={confirming}
        title={`Apply this ${a.operation}?`}
        confirmLabel={`Approve and apply`}
        onCancel={() => setConfirming(false)}
        onConfirm={() => { setConfirming(false); onDecide("approved"); }}
        acknowledge={needsAck ? {
          label: a.operation === "DELETE"
            ? `I understand ${plural(a.affected_rows, "row")} will be permanently deleted from ${a.target_table}.`
            : `I understand this changes ${plural(a.affected_rows, "row")} in ${a.target_table}${noFilter ? " — every row, with no filter" : ""}.`,
          checked: ack,
          onChange: setAck,
        } : undefined}
      >
        <p>
          This runs the statement against the database and changes {plural(a.affected_rows, "row")} in{" "}
          <code className="font-mono text-ink">{a.target_table}</code>. AutoInsight cannot undo it afterwards.
        </p>
        <p>The result — applied or failed — is shown once the server confirms it, and recorded in the audit log.</p>
      </ConfirmDialog>
    </article>
  );
}
