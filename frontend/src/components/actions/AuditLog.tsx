// AuditLog — entries from GET /api/audit?limit=N (newest first), filterable
// by the fields the JSONL entries actually contain. The server returns only
// the latest N (max 200); this view says so rather than implying a full history.

import { Fragment, useMemo, useState } from "react";
import { ChevronRight, CircleAlert, CircleCheck, CircleSlash, CircleX, Search, ShieldX } from "lucide-react";
import { explainFactor, outcomeOf, type OutcomeGroup } from "../../lib/actions";
import { plural } from "../../lib/format";
import { AUDIT_LIMITS, type ActionCenterState, type AuditLimit } from "../../hooks/useActionCenter";
import type { AuditEntry } from "../../types";

const OUTCOME_ICON: Record<OutcomeGroup, { icon: typeof CircleCheck; tone: string }> = {
  executed: { icon: CircleCheck, tone: "text-success" },
  rejected: { icon: CircleX, tone: "text-ink-secondary" },
  blocked: { icon: ShieldX, tone: "text-warning" },
  failed: { icon: CircleAlert, tone: "text-danger" },
  other: { icon: CircleSlash, tone: "text-ink-secondary" },
};

const OUTCOME_FILTERS: { id: OutcomeGroup | "all"; label: string }[] = [
  { id: "all", label: "All outcomes" },
  { id: "executed", label: "Executed" },
  { id: "rejected", label: "Rejected" },
  { id: "blocked", label: "Blocked" },
  { id: "failed", label: "Failed / not executed" },
];

const when = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
};

const selectCls = "focus-ring h-9 rounded-control border border-line-strong bg-surface px-2.5 pr-8 text-sm text-ink";

export function AuditLog({ state }: { state: ActionCenterState }) {
  const { audit, limit, setLimit } = state;
  const entries = audit.status === "ready" ? audit.data : [];

  const [q, setQ] = useState("");
  const [outcome, setOutcome] = useState<OutcomeGroup | "all">("all");
  const [op, setOp] = useState("all");
  const [table, setTable] = useState("all");
  const [open, setOpen] = useState<number | null>(null);

  const ops = useMemo(() => [...new Set(entries.map((e) => e.operation))].sort(), [entries]);
  const tables = useMemo(() => [...new Set(entries.map((e) => e.target_table))].sort(), [entries]);

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return entries
      .map((e, i) => ({ e, i, o: outcomeOf(e) }))
      .filter(({ e, o }) =>
        (outcome === "all" || o.group === outcome) &&
        (op === "all" || e.operation === op) &&
        (table === "all" || e.target_table === table) &&
        (!needle || [e.user_query, e.sql, e.session_id, e.approved_by ?? ""].some((s) => s?.toLowerCase().includes(needle))));
  }, [entries, q, outcome, op, table]);

  return (
    <section aria-labelledby="audit-heading" className="card overflow-hidden">
      <header className="border-b border-line px-5 py-4">
        <h2 id="audit-heading" className="text-base font-semibold text-ink">Audit log</h2>
        <p className="text-xs text-ink-muted">
          Every decided data change — executed, rejected, blocked or failed — as recorded by the server.
        </p>

        <div className="mt-3 flex flex-wrap items-end gap-2">
          <label className="relative min-w-[12rem] flex-1">
            <span className="sr-only">Search requests, SQL, approver or session</span>
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-ink-muted" aria-hidden />
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search request, SQL, approver…"
              className="focus-ring h-9 w-full rounded-control border border-line-strong bg-surface pl-8 pr-3 text-sm text-ink placeholder:text-ink-muted"
            />
          </label>
          <label>
            <span className="sr-only">Outcome</span>
            <select value={outcome} onChange={(e) => setOutcome(e.target.value as OutcomeGroup | "all")} className={selectCls}>
              {OUTCOME_FILTERS.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}
            </select>
          </label>
          <label>
            <span className="sr-only">Operation</span>
            <select value={op} onChange={(e) => setOp(e.target.value)} className={selectCls}>
              <option value="all">All operations</option>
              {ops.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </label>
          <label>
            <span className="sr-only">Table</span>
            <select value={table} onChange={(e) => setTable(e.target.value)} className={selectCls}>
              <option value="all">All tables</option>
              {tables.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1.5 text-xs text-ink-muted">
            Load latest
            <select value={limit} onChange={(e) => setLimit(Number(e.target.value) as AuditLimit)} className={selectCls}>
              {AUDIT_LIMITS.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </label>
        </div>
      </header>

      {audit.status === "loading" || audit.status === "idle" ? (
        <div className="space-y-2 p-5" aria-hidden>
          {[0, 1, 2, 3].map((i) => <div key={i} className="h-10 animate-pulse rounded bg-surface-sunken" />)}
        </div>
      ) : audit.status === "error" ? (
        <p role="alert" className="px-5 py-6 text-sm text-danger">The audit log could not be loaded. {audit.message}</p>
      ) : entries.length === 0 ? (
        <p className="px-5 py-8 text-center text-sm text-ink-muted">No data changes have been recorded yet.</p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-surface-sunken text-left text-xs text-ink-secondary">
                <tr>
                  <th scope="col" className="w-8 px-3 py-2.5"><span className="sr-only">Details</span></th>
                  <th scope="col" className="whitespace-nowrap px-3 py-2.5 font-semibold">When</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold">Change</th>
                  <th scope="col" className="px-3 py-2.5 font-semibold">Outcome</th>
                  <th scope="col" className="whitespace-nowrap px-3 py-2.5 text-right font-semibold">Rows changed</th>
                  <th scope="col" className="whitespace-nowrap px-3 py-2.5 text-right font-semibold">Risk</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 && (
                  <tr><td colSpan={6} className="px-5 py-6 text-center text-sm text-ink-muted">No entries match these filters.</td></tr>
                )}
                {rows.map(({ e, i, o }) => {
                  const { icon: Icon, tone } = OUTCOME_ICON[o.group];
                  const expanded = open === i;
                  return (
                    <Fragment key={`${e.timestamp}-${i}`}>
                      <tr className="border-t border-line/70 align-top">
                        <td className="px-3 py-2.5">
                          <button
                            type="button"
                            onClick={() => setOpen(expanded ? null : i)}
                            aria-expanded={expanded}
                            aria-label={expanded ? "Hide details" : "Show details"}
                            className="focus-ring rounded p-0.5 text-ink-muted hover:text-ink"
                          >
                            <ChevronRight className={`h-4 w-4 transition-transform ${expanded ? "rotate-90" : ""}`} aria-hidden />
                          </button>
                        </td>
                        <td className="whitespace-nowrap px-3 py-2.5 text-xs tabular-nums text-ink-secondary">{when(e.timestamp)}</td>
                        <td className="min-w-[14rem] px-3 py-2.5">
                          <div className="text-ink"><span className="font-mono text-xs font-semibold">{e.operation}</span> on <span className="font-mono text-xs">{e.target_table}</span></div>
                          <div className="max-w-[28rem] truncate text-xs text-ink-muted" title={e.user_query}>“{e.user_query}”</div>
                        </td>
                        <td className="min-w-[12rem] px-3 py-2.5">
                          <div className={`flex items-center gap-1.5 font-medium ${tone}`}>
                            <Icon className="h-4 w-4 shrink-0" aria-hidden />
                            {o.label}
                          </div>
                          <div className="text-xs text-ink-muted">{o.detail}</div>
                        </td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-ink">{e.executed ? e.affected_rows.toLocaleString("en-IN") : "—"}</td>
                        <td className="px-3 py-2.5 text-right tabular-nums text-ink-secondary">{e.risk_score}</td>
                      </tr>
                      {expanded && (
                        <tr className="bg-surface-sunken/50">
                          <td />
                          <td colSpan={5} className="px-3 pb-4 pt-1">
                            {/* On narrow screens the table scrolls sideways; keep the
                                details pinned to the visible width instead */}
                            <div className="sticky left-3 max-w-[calc(100vw-5.5rem)] sm:static sm:max-w-none">
                              <AuditDetails e={e} />
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="border-t border-line px-5 py-3 text-xs text-ink-muted">
            Showing {rows.length} of the latest {plural(entries.length, "entry", "entries")} returned by the server
            {entries.length >= limit ? ` (limit ${limit}; older entries exist and are not shown)` : ""}.
            The log is an append-only file kept by the server; this view does not verify its integrity.
          </p>
        </>
      )}
    </section>
  );
}

function AuditDetails({ e }: { e: AuditEntry }) {
  const factors = Object.entries(e.risk_factors ?? {});
  return (
    <div className="grid grid-cols-1 gap-4 text-xs lg:grid-cols-2">
      <div className="space-y-2">
        <div>
          <div className="eyebrow mb-1">Request</div>
          <p className="text-sm text-ink">“{e.user_query}”</p>
        </div>
        <div>
          <div className="eyebrow mb-1">Statement</div>
          <pre className="max-h-40 overflow-auto rounded-control bg-navy-950 px-3 py-2 font-mono text-[12px] text-navy-100">
            <code className="whitespace-pre-wrap break-words">{e.sql}</code>
          </pre>
        </div>
        {e.error && (
          <div>
            <div className="eyebrow mb-1">Database error</div>
            <p className="rounded-control border border-danger/25 bg-danger-soft px-3 py-2 font-mono text-[12px] text-danger">{e.error}</p>
          </div>
        )}
      </div>
      <div className="space-y-2">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1">
          <dt className="text-ink-muted">Decision recorded</dt><dd className="font-mono text-ink">{e.decision}</dd>
          <dt className="text-ink-muted">Executed</dt><dd className="text-ink">{e.executed ? "Yes — committed" : "No"}</dd>
          <dt className="text-ink-muted">Decided by</dt><dd className="text-ink">{e.approved_by ?? (e.decision === "auto_approved" ? "System (auto-approval)" : "—")}</dd>
          <dt className="text-ink-muted">Session</dt><dd className="truncate font-mono text-ink" title={e.session_id}>{e.session_id}</dd>
          <dt className="text-ink-muted">Timestamp (UTC)</dt><dd className="font-mono text-ink">{e.timestamp}</dd>
        </dl>
        {factors.length > 0 && (
          <div>
            <div className="eyebrow mb-1">Risk score {e.risk_score}</div>
            <ul className="space-y-0.5">
              {factors.map(([k, v]) => (
                <li key={k} className="flex justify-between gap-3">
                  <span className="text-ink-secondary">{explainFactor(k, v).label}</span>
                  <span className="tabular-nums text-ink">+{v}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
