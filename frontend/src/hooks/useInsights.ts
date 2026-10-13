// useInsights — runs ML analyses for the Insights & Forecasts page.
//
// Each run is one POST /api/chat with a fixed question. The backend parses
// forecast metric and horizon from the question text deterministically
// (ml_agent._parse_forecast_metric / _parse_horizon), so these phrasings
// select the options reliably; the response is still validated against the
// analysis that was asked for.
//
// History holds only runs made in this browser session (in memory). Nothing
// is persisted server-side for listing, so nothing older is shown.

import { useCallback, useState } from "react";
import { api, errorMessage } from "../api";
import type { ChatResponse, MLResult } from "../types";

export type AnalysisKind = "forecast" | "segments" | "anomalies";
export type ForecastMetric = "count" | "revenue";
export const FORECAST_HORIZONS = [3, 6, 12] as const;
export type ForecastHorizon = (typeof FORECAST_HORIZONS)[number];

export interface ForecastOptions { metric: ForecastMetric; horizon: ForecastHorizon }

const EXPECTED: Record<AnalysisKind, { intent: string; technique: MLResult["technique"] }> = {
  forecast:  { intent: "ml_forecast", technique: "forecast" },
  segments:  { intent: "ml_cluster",  technique: "cluster" },
  anomalies: { intent: "ml_anomaly",  technique: "anomaly" },
};

export function questionFor(kind: AnalysisKind, f: ForecastOptions): string {
  if (kind === "forecast") {
    return f.metric === "revenue"
      ? `Forecast sales revenue for the next ${f.horizon} months.`
      : `Forecast the number of sales for the next ${f.horizon} months.`;
  }
  return kind === "segments" ? "Segment customers by spending behavior." : "Find unusual sales transactions.";
}

export type RunOutcome =
  | { status: "ok"; response: ChatResponse; ml: MLResult }
  | { status: "failed"; message: string; response?: ChatResponse };

export interface AnalysisRun {
  id: string;
  kind: AnalysisKind;
  question: string;
  forecast?: ForecastOptions;
  startedAt: number;
  finishedAt: number;
  outcome: RunOutcome;
}

/** Check that the server ran the analysis we asked for and returned its result. */
function interpret(kind: AnalysisKind, res: ChatResponse): RunOutcome {
  if (res.status === "error") {
    return { status: "failed", response: res, message: res.response || res.error || "The analysis could not be completed." };
  }
  const want = EXPECTED[kind];
  const ml = res.ml_result;
  if (res.intent !== want.intent || !ml || ml.technique !== want.technique || !ml.summary) {
    return {
      status: "failed",
      response: res,
      message: "The server did not return the expected analysis result, so nothing is shown. Try running it again.",
    };
  }
  return { status: "ok", response: res, ml };
}

export function useInsights() {
  const [selected, setSelected] = useState<AnalysisKind>("forecast");
  const [forecastOptions, setForecastOptions] = useState<ForecastOptions>({ metric: "count", horizon: 3 });
  const [inFlight, setInFlight] = useState<{ kind: AnalysisKind; question: string } | null>(null);
  const [runs, setRuns] = useState<AnalysisRun[]>([]);         // newest first
  const [viewing, setViewing] = useState<Partial<Record<AnalysisKind, string>>>({});

  const run = useCallback(async () => {
    if (inFlight) return;                                       // no duplicate submissions
    const kind = selected;
    const forecast = kind === "forecast" ? forecastOptions : undefined;
    const question = questionFor(kind, forecastOptions);
    const startedAt = Date.now();
    setInFlight({ kind, question });

    let outcome: RunOutcome;
    try {
      // Fresh session per run: analyses stay independent of the AI Analyst
      // conversation and of each other.
      outcome = interpret(kind, await api.chat(null, question));
    } catch (e) {
      outcome = { status: "failed", message: errorMessage(e) };
    }

    const entry: AnalysisRun = {
      id: crypto.randomUUID(), kind, question, forecast, startedAt, finishedAt: Date.now(), outcome,
    };
    setRuns((r) => [entry, ...r]);
    setViewing((v) => ({ ...v, [kind]: entry.id }));
    setInFlight(null);
  }, [inFlight, selected, forecastOptions]);

  const show = useCallback((id: string) => {
    const r = runs.find((x) => x.id === id);
    if (!r) return;
    setSelected(r.kind);
    setViewing((v) => ({ ...v, [r.kind]: id }));
  }, [runs]);

  const current = runs.find((r) => r.id === viewing[selected]) ?? null;

  return {
    selected, select: setSelected,
    forecastOptions, setForecastOptions,
    inFlight, run,
    runs, current, show,
  };
}

export type InsightsState = ReturnType<typeof useInsights>;
