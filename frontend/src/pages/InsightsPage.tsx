// InsightsPage — run forecasting, segmentation and anomaly detection and
// read the results. Every run is a real POST /api/chat; results are the
// model's own output (response.ml_result + chart_config).

import { CircleAlert, Database, RotateCcw } from "lucide-react";
import { AgentActivityIndicator } from "../components/AgentActivityIndicator";
import { ANALYSES, AnalysisSelector } from "../components/insights/AnalysisSelector";
import { AnomaliesResult } from "../components/insights/AnomaliesResult";
import { ForecastResult } from "../components/insights/ForecastResult";
import { RunHistory } from "../components/insights/RunHistory";
import { SegmentsResult } from "../components/insights/SegmentsResult";
import { PageContainer } from "../components/layout/PageContainer";
import { RichText } from "../components/RichText";
import { Button } from "../components/ui/Button";
import type { InsightsState } from "../hooks/useInsights";
import type { OverviewState } from "../hooks/useOverview";
import { formatValue, longDate } from "../lib/format";

interface Props {
  state: InsightsState;
  /** Shared with the Overview page — supplies the dataset's date range. */
  dataset: OverviewState;
  onAsk: (question: string) => void;
}

export function InsightsPage({ state, dataset, onAsk }: Props) {
  return (
    <PageContainer>
      <div className="space-y-6">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <p className="max-w-2xl text-sm text-ink-secondary">
            Analyze historical performance and explore predictive patterns in your dealership data.
            Choose an analysis and run it — results come straight from the models.
          </p>
          <DatasetRange dataset={dataset} />
        </header>

        <AnalysisSelector state={state} />

        <Workspace state={state} onAsk={onAsk} />

        <RunHistory state={state} />
      </div>
    </PageContainer>
  );
}

function DatasetRange({ dataset }: { dataset: OverviewState }) {
  const o = dataset.overview;
  if (o.status !== "ready" || !o.data.data_extent) {
    return o.status === "error"
      ? <span className="text-xs text-ink-muted">Dataset range unavailable</span>
      : null;
  }
  const e = o.data.data_extent;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1 text-xs text-ink-secondary"
          title="Analyses use all recorded sales. These are historical records, not live activity.">
      <Database className="h-3.5 w-3.5 text-ink-muted" aria-hidden />
      Historical sales: {longDate(e.first_sale_date)} – {longDate(e.last_sale_date)} · {formatValue(e.total_sales, "count")} sales
    </span>
  );
}

/**
 * The ML service's guard errors read e.g. "Forecast needs ≥24 monthly points,
 * got 10" (ml_service.py). Recognise them so the page can say plainly that
 * the data is insufficient — and only then.
 */
function parseShortfall(message: string): { needed: number; got: number; unit: string } | null {
  const m = /needs\s*≥\s*(\d+)\s+([a-z ]+?),\s*got\s+(\d+)/i.exec(message);
  return m ? { needed: Number(m[1]), unit: m[2].trim(), got: Number(m[3]) } : null;
}

function Workspace({ state, onAsk }: { state: InsightsState; onAsk: (q: string) => void }) {
  const { selected, inFlight, current, run } = state;
  const meta = ANALYSES[selected];

  let body;
  if (inFlight?.kind === selected) {
    body = (
      <div className="px-5 py-10">
        <AgentActivityIndicator variant="panel" label={`Running ${meta.title.toLowerCase()}`} showElapsed />
      </div>
    );
  } else if (!current) {
    body = (
      <div className="px-5 py-12 text-center">
        <meta.icon className="mx-auto h-8 w-8 text-ink-muted" aria-hidden />
        <p className="mt-3 text-sm font-medium text-ink">No {meta.title.toLowerCase()} results yet</p>
        <p className="mt-1 text-sm text-ink-muted">Run the analysis above to see results here.</p>
      </div>
    );
  } else if (current.outcome.status === "failed") {
    const o = current.outcome;
    const shortfall = parseShortfall(o.message);
    body = (
      <div className="px-5 py-6">
        <div role="alert" className="rounded-control border border-danger/25 bg-danger-soft px-4 py-3">
          <p className="flex items-center gap-1.5 text-sm font-semibold text-danger">
            <CircleAlert className="h-4 w-4" aria-hidden />
            The {meta.title.toLowerCase()} could not be completed
          </p>
          <RichText text={o.message} className="mt-1 !text-sm text-ink-secondary" />
          {shortfall && (
            <p className="mt-2 text-sm text-ink">
              There is not enough data for this analysis yet: it needs at least {shortfall.needed} {shortfall.unit},
              and {shortfall.got} {shortfall.got === 1 ? "is" : "are"} available. It will become possible as more records are added.
            </p>
          )}
        </div>
        <div className="mt-4">
          <Button icon={RotateCcw} onClick={run} disabled={!!inFlight}>Try again</Button>
        </div>
      </div>
    );
  } else {
    const { response, ml } = current.outcome;
    body = (
      <div className="px-5 py-5">
        {ml.technique === "forecast" && <ForecastResult response={response} summary={ml.summary} onAsk={onAsk} />}
        {ml.technique === "cluster" && <SegmentsResult response={response} summary={ml.summary} onAsk={onAsk} />}
        {ml.technique === "anomaly" && <AnomaliesResult response={response} summary={ml.summary} onAsk={onAsk} />}
      </div>
    );
  }

  return (
    <section aria-labelledby="workspace-heading" className="card overflow-hidden">
      <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-5 py-3">
        <h2 id="workspace-heading" className="text-base font-semibold text-ink">{meta.title} results</h2>
        {current && inFlight?.kind !== selected && (
          <span className="text-xs text-ink-muted">
            Run at {new Date(current.finishedAt).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
            {" · "}took {Math.max(1, Math.round((current.finishedAt - current.startedAt) / 1000))}s
          </span>
        )}
      </header>
      {body}
    </section>
  );
}
