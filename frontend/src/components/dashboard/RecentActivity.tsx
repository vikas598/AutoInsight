// RecentActivity — the latest data-change decisions from the audit log
// (GET /api/audit). Every row is a real audit entry; nothing is synthesised.
// Proposals still awaiting a decision are not written to the audit log, so
// they cannot appear here.

import type { ReactNode } from "react";
import { CircleAlert, CircleCheck, CircleX, ShieldCheck, ShieldX } from "lucide-react";
import { plural } from "../../lib/format";
import type { AuditEntry } from "../../types";
import type { Load } from "../../hooks/useOverview";

const DECISION: Record<string, { label: string; icon: typeof CircleCheck; tone: string }> = {
  auto_approved: { label: "Applied automatically", icon: ShieldCheck, tone: "text-success" },
  approved:      { label: "Approved and applied",  icon: CircleCheck, tone: "text-success" },
  rejected:      { label: "Rejected",              icon: CircleX,     tone: "text-ink-secondary" },
  blocked:       { label: "Blocked by safety checks", icon: ShieldX,  tone: "text-warning" },
  error:         { label: "Failed",                icon: CircleAlert, tone: "text-danger" },
};

function when(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function RecentActivity({ activity }: { activity: Load<AuditEntry[]> }) {
  let body: ReactNode;
  if (activity.status === "loading" || activity.status === "idle") {
    body = (
      <div className="space-y-3" aria-hidden>
        {[0, 1, 2].map((i) => <div key={i} className="h-10 animate-pulse rounded bg-surface-sunken" />)}
      </div>
    );
  } else if (activity.status === "error") {
    body = <p className="text-sm text-ink-muted">Activity could not be loaded. {activity.message}</p>;
  } else if (activity.data.length === 0) {
    body = <p className="text-sm text-ink-muted">No data changes have been recorded yet.</p>;
  } else {
    // Audit log is append-only; newest last on disk → newest first here
    const entries = [...activity.data].sort((a, b) => b.timestamp.localeCompare(a.timestamp));
    body = (
      <ul className="divide-y divide-line/70">
        {entries.map((e, i) => {
          const d = DECISION[e.decision] ?? { label: e.decision, icon: CircleAlert, tone: "text-ink-secondary" };
          const Icon = d.icon;
          return (
            <li key={`${e.timestamp}-${i}`} className="flex gap-3 py-2.5">
              <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${d.tone}`} aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="text-sm text-ink">
                  <span className={`font-medium ${d.tone}`}>{d.label}</span>
                  <span className="text-ink-secondary"> · </span>
                  <span className="font-mono text-xs">{e.operation}</span>{" "}
                  <span className="text-ink-secondary">on</span>{" "}
                  <span className="font-mono text-xs">{e.target_table}</span>
                </p>
                <p className="truncate text-xs text-ink-muted" title={e.user_query}>“{e.user_query}”</p>
                <p className="text-2xs text-ink-muted tabular-nums">
                  {when(e.timestamp)} · risk {e.risk_score}/100
                  {e.executed ? ` · ${plural(e.affected_rows, "row")} changed` : " · no rows changed"}
                </p>
              </div>
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <section className="card p-5" aria-labelledby="activity-heading">
      <header className="mb-3">
        <h2 id="activity-heading" className="text-base font-semibold text-ink">Recent data changes</h2>
        <p className="text-xs text-ink-muted">Latest decided changes from the audit log</p>
      </header>
      {body}
    </section>
  );
}
