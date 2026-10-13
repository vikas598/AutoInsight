// SalesTrendChart — monthly revenue or units sold for the reporting period.
// The server returns every month in the period (zero-filled), so gaps are
// real zero-sales months, not missing data.

import { useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipProps,
} from "recharts";
import { formatCompact, formatINRShort, formatValue, monthLabel } from "../../lib/format";
import type { OverviewResponse } from "../../types";

type Metric = "revenue" | "units";
type Month = OverviewResponse["monthly"][number];

const PRIMARY = "#2563eb";
const GRID = "#e9eef5";
const AXIS = { fontSize: 11, fill: "#64748b" };

const fmt = (m: Metric, v: number) => (m === "revenue" ? formatINRShort(v) : formatValue(v, "count"));

interface Props {
  monthly: Month[];
  periodLabel: string;
}

export function SalesTrendChart({ monthly, periodLabel }: Props) {
  const [metric, setMetric] = useState<Metric>("revenue");
  const multiYear = monthly.length > 12;

  const summary = useMemo(() => {
    if (!monthly.length) return null;
    const peak = monthly.reduce((a, b) => (b[metric] > a[metric] ? b : a));
    const total = monthly.reduce((s, m) => s + m[metric], 0);
    return { peak, average: total / monthly.length, total };
  }, [monthly, metric]);

  const empty = !summary || summary.total === 0;

  const tooltip = ({ active, payload }: TooltipProps<number, string>) => {
    if (!active || !payload?.length) return null;
    const m = payload[0].payload as Month;
    return (
      <div className="rounded-control border border-line bg-surface px-3 py-2 text-xs shadow-raised">
        <div className="mb-1 font-semibold text-ink">{monthLabel(m.month)}</div>
        <div className="flex justify-between gap-6"><span className="text-ink-secondary">Revenue</span><span className="font-medium tabular-nums">{formatValue(m.revenue, "currency")}</span></div>
        <div className="flex justify-between gap-6"><span className="text-ink-secondary">Units sold</span><span className="font-medium tabular-nums">{formatValue(m.units, "count")}</span></div>
      </div>
    );
  };

  const xTick = (v: string) => (multiYear ? monthLabel(v).replace(" 20", " ’") : monthLabel(v, true));

  return (
    <section className="card p-5" aria-labelledby="trend-heading">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="trend-heading" className="text-base font-semibold text-ink">Sales trend</h2>
          <p className="text-xs text-ink-muted">Monthly totals · {periodLabel}</p>
        </div>
        <div role="group" aria-label="Trend metric" className="inline-flex rounded-control border border-line bg-surface-sunken p-0.5">
          {(["revenue", "units"] as const).map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={metric === m}
              onClick={() => setMetric(m)}
              className={`focus-ring rounded-[6px] px-3 py-1 text-xs font-medium transition-colors ${
                metric === m ? "bg-surface text-ink shadow-card" : "text-ink-muted hover:text-ink"
              }`}
            >
              {m === "revenue" ? "Revenue" : "Units sold"}
            </button>
          ))}
        </div>
      </header>

      {empty ? (
        <p className="mt-6 rounded-control border border-dashed border-line-strong px-4 py-10 text-center text-sm text-ink-muted">
          No sales were recorded in this period.
        </p>
      ) : (
        <>
          <dl className="mt-4 flex flex-wrap gap-x-8 gap-y-2 text-sm">
            <div>
              <dt className="text-xs text-ink-muted">Best month</dt>
              <dd className="font-semibold text-ink tabular-nums">
                {monthLabel(summary!.peak.month)} · {fmt(metric, summary!.peak[metric])}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-ink-muted">Monthly average</dt>
              <dd className="font-semibold text-ink tabular-nums">
                {metric === "revenue" ? formatINRShort(summary!.average) : summary!.average.toLocaleString("en-IN", { maximumFractionDigits: 1 })}
              </dd>
            </div>
          </dl>

          <div className="mt-4 h-72">
            <ResponsiveContainer width="100%" height="100%">
              {metric === "revenue" ? (
                <AreaChart data={monthly} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke={GRID} />
                  <XAxis dataKey="month" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} tickFormatter={xTick} minTickGap={16} />
                  <YAxis tick={AXIS} tickLine={false} axisLine={false} width={64}
                         tickFormatter={(v) => formatCompact(v, "currency")}
                         label={{ value: "Revenue (₹)", angle: -90, position: "insideLeft", fontSize: 11, fill: "#64748b", dy: 40 }} />
                  <Tooltip content={tooltip} />
                  <Area type="monotone" dataKey="revenue" stroke={PRIMARY} strokeWidth={2} fill={PRIMARY} fillOpacity={0.08}
                        dot={monthly.length <= 12 ? { r: 2.5, fill: PRIMARY } : false} activeDot={{ r: 4 }} />
                </AreaChart>
              ) : (
                <BarChart data={monthly} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke={GRID} />
                  <XAxis dataKey="month" tick={AXIS} tickLine={false} axisLine={{ stroke: GRID }} tickFormatter={xTick} minTickGap={16} />
                  <YAxis tick={AXIS} tickLine={false} axisLine={false} width={64} allowDecimals={false}
                         label={{ value: "Units sold", angle: -90, position: "insideLeft", fontSize: 11, fill: "#64748b", dy: 30 }} />
                  <Tooltip content={tooltip} cursor={{ fill: "rgba(37, 99, 235, 0.06)" }} />
                  <Bar dataKey="units" fill={PRIMARY} radius={[3, 3, 0, 0]} maxBarSize={28} />
                </BarChart>
              )}
            </ResponsiveContainer>
          </div>
        </>
      )}
    </section>
  );
}
