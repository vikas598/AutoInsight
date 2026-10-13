// ResultCard — the analytical result attached to an answer: a KPI, a chart
// (with a toggle to the underlying data) or a table. Only renders what the
// response actually contains.

import { useState } from "react";
import { BarChart3, Table2 } from "lucide-react";
import { chartCaption, chartTitle, chartVariant, ChartRenderer } from "./ChartRenderer";
import { DataTable, recordsToTable } from "./DataTable";
import { plural } from "../lib/format";
import type { ChatResponse } from "../types";

type View = "chart" | "table";

function metaLine(res: ChatResponse, variant: ReturnType<typeof chartVariant>): string | null {
  const data = res.chart_config?.data ?? [];
  if (variant === "segments") return plural(data.length, "segment");
  if (variant === "anomalies") return `${plural(data.length, "sale")} flagged`;
  if (variant === "forecast") {
    const ahead = data.filter((r) => r.forecast !== null && r.forecast !== undefined).length;
    return `${plural(ahead, "month")} ahead`;
  }
  if (res.query_result) return plural(res.query_result.row_count, "row");
  return null;
}

export function ResultCard({ response }: { response: ChatResponse }) {
  const config = response.chart_config;
  const qr = response.query_result;
  const variant = chartVariant(config);
  const [view, setView] = useState<View>("chart");

  // Write responses reuse query_result for affected-row counts, not data;
  // the outcome is shown by the message itself.
  if (response.intent === "sql_write") return null;

  // An executed query that matched nothing
  if (qr && qr.row_count === 0) {
    return (
      <div className="rounded-card border border-dashed border-line-strong bg-surface px-4 py-3 text-sm text-ink-secondary">
        The query ran successfully but returned no matching records.
      </div>
    );
  }

  // Prefer the raw query result for the data view; ML results only have chart data
  const table = qr?.rows?.length
    ? { columns: qr.columns, rows: qr.rows, truncated: qr.truncated }
    : config?.data?.length
      ? { ...recordsToTable(config.data), truncated: false }
      : null;

  if (variant === "none" && !table) return null;

  if (variant === "kpi" && config) {
    return (
      <div className="inline-block min-w-[220px] rounded-card border border-line bg-surface shadow-card">
        <ChartRenderer config={config} />
      </div>
    );
  }

  const hasChart = variant !== "table" && variant !== "none";
  const showing: View = hasChart ? view : "table";
  const title = config && hasChart ? chartTitle(config) : "Results";
  const caption = config && showing === "chart" ? chartCaption(config) : null;
  const meta = metaLine(response, variant);

  return (
    <section className="card overflow-hidden" aria-label={title}>
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-ink">{title}</h3>
          {meta && <p className="text-xs text-ink-muted">{meta}</p>}
        </div>
        {hasChart && table && (
          <div role="group" aria-label="Result view" className="inline-flex rounded-control border border-line bg-surface-sunken p-0.5">
            {([["chart", "Chart", BarChart3], ["table", "Data", Table2]] as const).map(([id, label, Icon]) => (
              <button
                key={id}
                type="button"
                onClick={() => setView(id)}
                aria-pressed={showing === id}
                className={`focus-ring inline-flex items-center gap-1.5 rounded-[6px] px-2.5 py-1 text-xs font-medium transition-colors ${
                  showing === id ? "bg-surface text-ink shadow-card" : "text-ink-muted hover:text-ink"
                }`}
              >
                <Icon className="h-3.5 w-3.5" aria-hidden />
                {label}
              </button>
            ))}
          </div>
        )}
      </header>

      {showing === "chart" ? (
        <div className="px-2 pb-3 pt-4 sm:px-3">
          <ChartRenderer config={config} />
          {caption && <p className="px-2 pt-2 text-xs leading-relaxed text-ink-muted">{caption}</p>}
        </div>
      ) : table ? (
        <DataTable columns={table.columns} rows={table.rows} truncated={table.truncated} />
      ) : null}
    </section>
  );
}
