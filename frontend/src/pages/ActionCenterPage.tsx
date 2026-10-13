// ActionCenterPage — review and decide AI-proposed data changes, and inspect
// the audit trail. Pending items come from the LangGraph checkpointer via
// GET /api/approvals/pending; decisions use POST /api/approve/{session_id};
// history is GET /api/audit.

import { CircleAlert, CircleCheck, CircleX, Info, RefreshCw, X } from "lucide-react";
import { AuditLog } from "../components/actions/AuditLog";
import { PendingApprovals } from "../components/actions/PendingApprovals";
import { PageContainer } from "../components/layout/PageContainer";
import { RichText } from "../components/RichText";
import { Button } from "../components/ui/Button";
import type { ActionCenterState, DecisionFeedback } from "../hooks/useActionCenter";
import { outcomeOf, type OutcomeGroup } from "../lib/actions";
import { plural } from "../lib/format";

interface Props {
  state: ActionCenterState;
  analystSessionId: string | null;
}

export function ActionCenterPage({ state, analystSessionId }: Props) {
  return (
    <PageContainer>
      <div className="space-y-6">
        <header className="flex flex-wrap items-start justify-between gap-3">
          <p className="max-w-2xl text-sm text-ink-secondary">
            Review data changes proposed by the AI Analyst before they run, and check what happened to past ones.
            Every decision is executed by the server’s safety pipeline and written to the audit log.
          </p>
          <Button size="sm" icon={RefreshCw} onClick={state.refresh} disabled={state.busy} aria-label="Refresh Action Center">
            {state.busy ? "Refreshing…" : "Refresh"}
          </Button>
        </header>

        <Summary state={state} />

        {state.feedback && <FeedbackBanner feedback={state.feedback} onDismiss={state.dismissFeedback} />}

        <PendingApprovals state={state} analystSessionId={analystSessionId} />

        <AuditLog state={state} />
      </div>
    </PageContainer>
  );
}

/** Counts derived only from what was loaded — and labelled with that scope. */
function Summary({ state }: { state: ActionCenterState }) {
  const { pending, audit } = state;
  if (pending.status !== "ready" && audit.status !== "ready") return null;

  const groups: Record<OutcomeGroup, number> = { executed: 0, rejected: 0, blocked: 0, failed: 0, other: 0 };
  if (audit.status === "ready") for (const e of audit.data) groups[outcomeOf(e).group] += 1;
  const n = audit.status === "ready" ? audit.data.length : 0;

  const tiles = [
    ...(pending.status === "ready" ? [{ label: "Awaiting approval", value: pending.data.length, hint: "Since the server last started" }] : []),
    ...(audit.status === "ready" && n > 0 ? [
      { label: "Executed", value: groups.executed, hint: `In the latest ${plural(n, "audit entry", "audit entries")}` },
      { label: "Rejected", value: groups.rejected, hint: "Not executed" },
      { label: "Blocked or failed", value: groups.blocked + groups.failed, hint: "Not executed" },
    ] : []),
  ];
  if (!tiles.length) return null;

  return (
    <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-card border border-line bg-line md:grid-cols-4">
      {tiles.map((t) => (
        <div key={t.label} className="bg-surface px-4 py-3">
          <dt className="text-xs text-ink-muted">{t.label}</dt>
          <dd className="mt-0.5 text-2xl font-semibold tabular-nums text-ink">{t.value}</dd>
          <dd className="text-2xs text-ink-muted">{t.hint}</dd>
        </div>
      ))}
    </dl>
  );
}

/** The server's confirmed result of the last decision made here. */
function FeedbackBanner({ feedback, onDismiss }: { feedback: DecisionFeedback; onDismiss: () => void }) {
  let tone: string, Icon: typeof CircleCheck, title: string, body: string | null;

  if (feedback.kind === "done") {
    const r = feedback.response;
    const rows = r.query_result?.row_count;
    if (r.status === "error") {
      tone = "border-danger/25 bg-danger-soft"; Icon = CircleAlert;
      title = feedback.decision === "approved" ? "Approved, but execution failed" : "The decision could not be completed";
      body = r.response || r.error;
    } else if (feedback.decision === "rejected") {
      tone = "border-line bg-surface"; Icon = CircleX;
      title = `Rejected — ${feedback.operation} on ${feedback.table} was not executed`;
      body = r.response;
    } else {
      tone = "border-success/25 bg-success-soft"; Icon = CircleCheck;
      title = `Approved and executed — ${feedback.operation} on ${feedback.table}${typeof rows === "number" ? `, ${plural(rows, "row")} affected` : ""}`;
      body = r.response;
    }
  } else if (feedback.kind === "conflict") {
    tone = "border-warning/30 bg-warning-soft"; Icon = Info;
    title = "This change is no longer awaiting approval";
    body = `${feedback.message} Check the audit log below for what happened.`;
  } else {
    tone = "border-danger/25 bg-danger-soft"; Icon = CircleAlert;
    title = "The server did not confirm the decision";
    body = `${feedback.message} The queue and audit log below show the server’s current state — check them before trying again.`;
  }

  return (
    <div role={feedback.kind === "done" && feedback.response.status !== "error" ? "status" : "alert"}
         className={`flex items-start gap-3 rounded-card border px-4 py-3 ${tone}`}>
      <Icon className="mt-0.5 h-5 w-5 shrink-0 text-ink-secondary" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-ink">{title}</p>
        {body && <RichText text={body} className="mt-0.5 !text-sm text-ink-secondary" />}
      </div>
      <button type="button" onClick={onDismiss} aria-label="Dismiss" className="focus-ring -m-1 rounded p-1 text-ink-muted hover:text-ink">
        <X className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );
}
