// RunHistory — analyses actually run in this browser session. In memory
// only; there is no server-side list of past runs, so nothing older appears.

import { CircleAlert, CircleCheck } from "lucide-react";
import type { AnalysisRun, InsightsState } from "../../hooks/useInsights";
import { formatINRShort, formatValue } from "../../lib/format";
import { ANALYSES } from "./AnalysisSelector";

function headline(r: AnalysisRun): string {
  if (r.outcome.status !== "ok") return r.outcome.message.slice(0, 90);
  const ml = r.outcome.ml;
  switch (ml.technique) {
    case "forecast":
      return `${ml.summary.metric === "revenue" ? "Revenue" : "Units"} · ${ml.summary.horizon_months} months · RMSE ${
        ml.summary.metric === "revenue" ? formatINRShort(ml.summary.rmse) : formatValue(ml.summary.rmse, "number")}`;
    case "cluster":
      return `${ml.summary.k} segments · silhouette ${ml.summary.silhouette_score.toFixed(3)}`;
    case "anomaly":
      return `${ml.summary.anomalies_found} of ${formatValue(ml.summary.total_records, "count")} sales flagged`;
  }
}

export function RunHistory({ state }: { state: InsightsState }) {
  const { runs, current, show } = state;
  if (!runs.length) return null;

  return (
    <section aria-labelledby="history-heading" className="card p-5">
      <header className="mb-2">
        <h2 id="history-heading" className="text-base font-semibold text-ink">Results from this session</h2>
        <p className="text-xs text-ink-muted">Kept in this browser tab only — cleared when the page reloads.</p>
      </header>
      <ul className="divide-y divide-line/70">
        {runs.map((r) => {
          const ok = r.outcome.status === "ok";
          const Icon = ok ? CircleCheck : CircleAlert;
          const viewing = current?.id === r.id;
          return (
            <li key={r.id}>
              <button
                type="button"
                onClick={() => show(r.id)}
                aria-current={viewing ? "true" : undefined}
                className={`focus-ring flex w-full items-start gap-3 rounded-control px-2 py-2.5 text-left hover:bg-surface-sunken/70 ${viewing ? "bg-primary-soft/50" : ""}`}
              >
                <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${ok ? "text-success" : "text-danger"}`} aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-ink">{ANALYSES[r.kind].title}</span>
                  <span className="block truncate text-xs text-ink-muted">{headline(r)}</span>
                </span>
                <span className="shrink-0 text-2xs tabular-nums text-ink-muted">
                  {new Date(r.finishedAt).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
                  {viewing && <span className="ml-1.5 font-medium text-primary">Viewing</span>}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
