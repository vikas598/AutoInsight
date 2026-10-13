// AnalysisSelector — the three analyses, plus the options and Run action for
// the selected one.

import { Play, ScanSearch, TrendingUp, Users, type LucideIcon } from "lucide-react";
import { Button } from "../ui/Button";
import {
  FORECAST_HORIZONS,
  type AnalysisKind,
  type ForecastHorizon,
  type ForecastMetric,
  type InsightsState,
} from "../../hooks/useInsights";

export const ANALYSES: Record<AnalysisKind, { title: string; icon: LucideIcon; description: string; method: string; action: string }> = {
  forecast: {
    title: "Sales forecast",
    icon: TrendingUp,
    description: "Estimate future sales or revenue from historical monthly totals.",
    method: "Seasonal ARIMA, with an ARIMA fallback · needs at least 24 months of history",
    action: "Run forecast",
  },
  segments: {
    title: "Customer segmentation",
    icon: Users,
    description: "Group customers with similar purchase counts and spending.",
    method: "K-Means, choosing 2–8 segments by silhouette score · needs at least 100 customers",
    action: "Run segmentation",
  },
  anomalies: {
    title: "Anomaly detection",
    icon: ScanSearch,
    description: "Find sales whose prices and discounts differ markedly from the rest.",
    method: "Isolation Forest on five price and discount measures · needs at least 50 sales",
    action: "Run anomaly detection",
  },
};

const KINDS: AnalysisKind[] = ["forecast", "segments", "anomalies"];

export function AnalysisSelector({ state }: { state: InsightsState }) {
  const { selected, select, runs, inFlight, run, forecastOptions, setForecastOptions } = state;
  const meta = ANALYSES[selected];
  const busyElsewhere = inFlight && inFlight.kind !== selected;

  return (
    <section aria-label="Choose an analysis" className="space-y-4">
      <div role="group" aria-label="Analyses" className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {KINDS.map((k) => {
          const a = ANALYSES[k];
          const last = runs.find((r) => r.kind === k);
          const active = k === selected;
          return (
            <button
              key={k}
              type="button"
              aria-pressed={active}
              onClick={() => select(k)}
              className={`focus-ring flex flex-col rounded-card border p-4 text-left transition-colors ${
                active
                  ? "border-primary bg-surface shadow-raised ring-1 ring-primary"
                  : "border-line bg-surface shadow-card hover:border-line-strong"
              }`}
            >
              <span className="flex items-center gap-2.5">
                <span className={`flex h-8 w-8 items-center justify-center rounded-control ${active ? "bg-primary text-white" : "bg-primary-soft text-primary"}`}>
                  <a.icon className="h-4 w-4" aria-hidden />
                </span>
                <span className="text-sm font-semibold text-ink">{a.title}</span>
              </span>
              <span className="mt-2 text-sm leading-snug text-ink-secondary">{a.description}</span>
              <span className="mt-3 text-2xs text-ink-muted">
                {inFlight?.kind === k ? "Running…"
                  : last ? `Last run ${new Date(last.finishedAt).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })} · ${last.outcome.status === "ok" ? "completed" : "failed"}`
                  : "Not run yet"}
              </span>
            </button>
          );
        })}
      </div>

      <div className="card flex flex-wrap items-end justify-between gap-4 px-5 py-4">
        <div className="min-w-0 space-y-3">
          <p className="text-xs text-ink-muted">{meta.method}</p>
          {selected === "forecast" && (
            <div className="flex flex-wrap items-end gap-4">
              <div>
                <span id="fc-metric" className="mb-1 block text-xs font-medium text-ink-secondary">Forecast</span>
                <div role="group" aria-labelledby="fc-metric" className="inline-flex rounded-control border border-line bg-surface-sunken p-0.5">
                  {([["count", "Units sold"], ["revenue", "Revenue"]] as [ForecastMetric, string][]).map(([m, label]) => (
                    <button key={m} type="button" aria-pressed={forecastOptions.metric === m}
                            onClick={() => setForecastOptions((o) => ({ ...o, metric: m }))}
                            className={`focus-ring rounded-[6px] px-3 py-1 text-xs font-medium transition-colors ${
                              forecastOptions.metric === m ? "bg-surface text-ink shadow-card" : "text-ink-muted hover:text-ink"
                            }`}>
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label htmlFor="fc-horizon" className="mb-1 block text-xs font-medium text-ink-secondary">Horizon</label>
                <select id="fc-horizon" value={forecastOptions.horizon}
                        onChange={(e) => setForecastOptions((o) => ({ ...o, horizon: Number(e.target.value) as ForecastHorizon }))}
                        className="focus-ring h-8 rounded-control border border-line-strong bg-surface px-2.5 pr-8 text-xs font-medium text-ink">
                  {FORECAST_HORIZONS.map((h) => <option key={h} value={h}>{h} months</option>)}
                </select>
              </div>
            </div>
          )}
          {busyElsewhere && (
            <p className="text-xs text-ink-muted" aria-live="polite">Another analysis is running. You can run this one when it finishes.</p>
          )}
        </div>
        <Button variant="primary" icon={Play} onClick={run} disabled={!!inFlight} aria-busy={inFlight?.kind === selected}>
          {inFlight?.kind === selected ? "Running…" : meta.action}
        </Button>
      </div>
    </section>
  );
}
