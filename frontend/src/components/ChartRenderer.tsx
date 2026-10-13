// ChartRenderer — renders a backend chart_config with Recharts.
// Supports every chart_type the visualization service emits: kpi, table,
// line, bar, grouped_bar, forecast_line and scatter (segments / anomalies).
// The data is drawn as returned; only labels and number formats are adapted.

import { useMemo, type ReactNode } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
  type TooltipProps,
} from "recharts";
import { formatCompact, formatValue, humanize, isDimension, isNumeric, kindOf, type ValueKind } from "../lib/format";
import type { ChartConfig } from "../types";

// Mirrors the design tokens in index.css (SVG attributes can't read CSS vars)
const C = {
  primary: "#2563eb",
  navy: "#1c294d",
  grid: "#e9eef5",
  axis: "#64748b",
  warning: "#d97706",
  series: ["#2563eb", "#0f766e", "#d97706", "#7c3aed", "#db2777", "#475569", "#0891b2", "#65a30d"],
};

const AXIS = { fontSize: 11, fill: C.axis };
const MARGIN = { top: 8, right: 16, left: 4, bottom: 4 };

type Row = Record<string, any>;

export type ChartVariant = "kpi" | "table" | "line" | "bar" | "forecast" | "segments" | "anomalies" | "scatter" | "none";

/** Which renderer a config maps to; "table" means no chart, show the data. */
export function chartVariant(config: ChartConfig | null): ChartVariant {
  if (!config || !config.data?.length) return "none";
  const first = config.data[0];
  switch (config.chart_type) {
    case "kpi": return "kpi";
    case "line": case "area": return "line";
    case "bar": case "grouped_bar": return "bar";
    case "forecast_line": return "forecast";
    case "scatter":
      if ("cluster" in first) return "segments";
      if ("score" in first) return "anomalies";
      return "scatter";
    default: return "table";
  }
}

/** Most bars drawn in one chart; the Data view always has every row. */
const MAX_BARS = 20;

/**
 * Plot only measures: drop identifier-like numeric columns (model year,
 * month number) from y_keys, keeping at least one series.
 */
function normalize(config: ChartConfig): ChartConfig {
  const measures = config.y_keys.filter((k) => !isDimension(k));
  return measures.length && measures.length !== config.y_keys.length ? { ...config, y_keys: measures } : config;
}

/** Columns that identify each bar, in result order (x_key first). */
function labelColumns(config: ChartConfig): string[] {
  const keys = Object.keys(config.data[0] ?? {}).filter((k) => !config.y_keys.includes(k));
  return [config.x_key, ...keys.filter((k) => k !== config.x_key)];
}

/** Plain-language title for a chart. */
export function chartTitle(raw: ChartConfig): string {
  const config = normalize(raw);
  const ys = config.y_keys.map(humanize).join(", ");
  const x = humanize(config.x_key).toLowerCase();
  switch (chartVariant(config)) {
    case "line": return `${ys} over ${x}`;
    case "bar": {
      const by = labelColumns(config).filter((k) => typeof config.data[0]?.[k] === "string");
      return `${ys} by ${(by.length ? by : [config.x_key]).map((k) => humanize(k).toLowerCase()).join(" and ")}`;
    }
    case "kpi": return humanize(config.y_keys[0] ?? config.x_key);
    case "forecast": return "Sales forecast";
    case "segments": return "Customer segments";
    case "anomalies": return "Sales flagged for review";
    default: return config.title;
  }
}

/** One-line explanation shown under ML charts. */
export function chartCaption(config: ChartConfig): string | null {
  switch (chartVariant(config)) {
    case "forecast":
      return "Solid line: recorded history. Dashed line: model forecast. Shaded band: forecast range (80% interval).";
    case "segments":
      return "Each bubble is the average customer of one segment; bubble size reflects how many customers it contains.";
    case "anomalies":
      return "Each point is a sale the model flagged as unusual. Treat these as items to review, not confirmed errors or fraud.";
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------

function ChartFrame({ height = 300, children }: { height?: number; children: ReactNode }) {
  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        {children as React.ReactElement}
      </ResponsiveContainer>
    </div>
  );
}

interface TipLine { label: string; value: string; color?: string; dashed?: boolean }

function TooltipBox({ title, lines }: { title?: string; lines: TipLine[] }) {
  return (
    <div className="rounded-control border border-line bg-surface px-3 py-2 text-xs shadow-raised">
      {title && <div className="mb-1 font-semibold text-ink">{title}</div>}
      <div className="space-y-0.5">
        {lines.map((l) => (
          <div key={l.label} className="flex items-center justify-between gap-4">
            <span className="inline-flex items-center gap-1.5 text-ink-secondary">
              {l.color && <span className="h-2 w-2 rounded-full" style={{ background: l.color }} aria-hidden />}
              {l.label}
            </span>
            <span className="font-medium tabular-nums text-ink">{l.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const sampleOf = (data: Row[], key: string) => data.find((r) => r[key] !== null && r[key] !== undefined)?.[key];

// ---------------------------------------------------------------------------
// KPI
// ---------------------------------------------------------------------------
function Kpi({ config }: { config: ChartConfig }) {
  const key = config.y_keys[0] ?? config.x_key;
  const value = config.data[0]?.[key];
  return (
    <div className="px-5 py-5">
      <div className="text-sm text-ink-secondary">{humanize(key)}</div>
      <div className="mt-1 text-4xl font-semibold tracking-tight text-ink tabular-nums">
        {formatValue(value, kindOf(key, value))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Line / Bar — shared axis handling (second y axis when units differ)
// ---------------------------------------------------------------------------
function useSeries(config: ChartConfig) {
  return useMemo(() => {
    const kinds = Object.fromEntries(config.y_keys.map((k) => [k, kindOf(k, sampleOf(config.data, k))])) as Record<string, ValueKind>;
    const leftKind = kinds[config.y_keys[0]];
    const axisOf = (k: string) => (kinds[k] === leftKind ? 0 : "right");
    const rightKind = config.y_keys.map((k) => kinds[k]).find((k) => k !== leftKind);
    return { kinds, leftKind, rightKind, axisOf };
  }, [config]);
}

function SeriesTooltip({ active, payload, label, kinds, xKind }: TooltipProps<number, string> & { kinds: Record<string, ValueKind>; xKind: ValueKind }) {
  if (!active || !payload?.length) return null;
  return (
    <TooltipBox
      title={formatValue(label, xKind)}
      lines={payload.map((p) => ({
        label: humanize(String(p.dataKey)),
        value: formatValue(p.value, kinds[String(p.dataKey)]),
        color: p.color,
      }))}
    />
  );
}

function LineView({ config }: { config: ChartConfig }) {
  const { kinds, leftKind, rightKind, axisOf } = useSeries(config);
  const xKind = kindOf(config.x_key, sampleOf(config.data, config.x_key));
  return (
    <ChartFrame>
      <LineChart data={config.data} margin={MARGIN}>
        <CartesianGrid vertical={false} stroke={C.grid} />
        <XAxis dataKey={config.x_key} tick={AXIS} tickLine={false} axisLine={{ stroke: C.grid }}
               tickFormatter={(v) => formatCompact(v, xKind)} minTickGap={24} />
        <YAxis yAxisId={0} tick={AXIS} tickLine={false} axisLine={false} width={64}
               tickFormatter={(v) => formatCompact(v, leftKind)} />
        {rightKind && (
          <YAxis yAxisId="right" orientation="right" tick={AXIS} tickLine={false} axisLine={false} width={64}
                 tickFormatter={(v) => formatCompact(v, rightKind)} />
        )}
        <Tooltip content={<SeriesTooltip kinds={kinds} xKind={xKind} />} />
        {config.y_keys.length > 1 && <Legend iconType="plainline" wrapperStyle={{ fontSize: 12 }} formatter={(v) => humanize(String(v))} />}
        {config.y_keys.map((k, i) => (
          <Line key={k} yAxisId={axisOf(k)} type="monotone" dataKey={k} stroke={C.series[i % C.series.length]}
                strokeWidth={2} dot={config.data.length <= 24 ? { r: 2.5 } : false} activeDot={{ r: 4 }} />
        ))}
      </LineChart>
    </ChartFrame>
  );
}

function BarView({ config }: { config: ChartConfig }) {
  const { kinds, leftKind, rightKind, axisOf } = useSeries(config);

  // Build each bar's label from every identifying column in the row (e.g.
  // make + model, plus model year when it varies) — values as returned.
  const { data, labelKey, total } = useMemo((): { data: Row[]; labelKey: string; total: number } => {
    const cols = labelColumns(config);
    const varies = (k: string) => new Set(config.data.map((r) => r[k])).size > 1;
    const text = cols.filter((k) => !isNumeric(config.data[0][k]));
    const numericDims = cols.filter((k) => isNumeric(config.data[0][k]) && varies(k));
    const rows = config.data.slice(0, MAX_BARS);
    if (text.length <= 1 && numericDims.length === 0) {
      return { data: rows, labelKey: config.x_key, total: config.data.length };
    }
    return {
      data: rows.map((r) => {
        const main = text.map((k) => r[k]).filter((v) => v != null && v !== "").join(" ");
        const extra = numericDims.map((k) => r[k]).filter((v) => v != null).join(", ");
        return { ...r, __label: extra ? `${main} (${extra})` : main };
      }),
      labelKey: "__label",
      total: config.data.length,
    };
  }, [config]);

  const labels = data.map((r) => String(r[labelKey] ?? ""));
  const longest = Math.max(...labels.map((l) => l.length));
  const horizontal = data.length > 8 || longest > 14;
  const xKind = labelKey === "__label" ? "text" : kindOf(config.x_key, sampleOf(data, config.x_key));

  const tooltip = <Tooltip cursor={{ fill: "rgba(37, 99, 235, 0.06)" }} content={<SeriesTooltip kinds={kinds} xKind={xKind} />} />;
  const legend = config.y_keys.length > 1 && <Legend iconType="square" wrapperStyle={{ fontSize: 12 }} formatter={(v) => humanize(String(v))} />;
  const capped = total > data.length && (
    <p className="px-2 pt-2 text-xs text-ink-muted">
      Chart shows the first {data.length} of {total.toLocaleString("en-IN")} rows in result order. Switch to Data for all rows.
    </p>
  );

  if (horizontal) {
    // One value axis: mixed units side by side on a horizontal chart are unreadable
    return (
      <>
        <ChartFrame height={Math.max(220, data.length * (config.y_keys.length > 1 ? 44 : 30) + 56)}>
          <BarChart data={data} layout="vertical" margin={MARGIN}>
            <CartesianGrid horizontal={false} stroke={C.grid} />
            <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false}
                   tickFormatter={(v) => formatCompact(v, leftKind)} />
            <YAxis type="category" dataKey={labelKey} tick={AXIS} tickLine={false} axisLine={{ stroke: C.grid }}
                   width={Math.min(200, Math.max(80, longest * 6.4))} interval={0} />
            {tooltip}
            {legend}
            {config.y_keys.map((k, i) => (
              <Bar key={k} dataKey={k} fill={C.series[i % C.series.length]} radius={[0, 3, 3, 0]} maxBarSize={22} />
            ))}
          </BarChart>
        </ChartFrame>
        {capped}
      </>
    );
  }

  return (
    <>
      <ChartFrame>
        <BarChart data={data} margin={MARGIN}>
          <CartesianGrid vertical={false} stroke={C.grid} />
          <XAxis dataKey={labelKey} tick={AXIS} tickLine={false} axisLine={{ stroke: C.grid }} interval={0}
                 tickFormatter={(v) => formatCompact(v, xKind)} />
          <YAxis yAxisId={0} tick={AXIS} tickLine={false} axisLine={false} width={64}
                 tickFormatter={(v) => formatCompact(v, leftKind)} />
          {rightKind && (
            <YAxis yAxisId="right" orientation="right" tick={AXIS} tickLine={false} axisLine={false} width={64}
                   tickFormatter={(v) => formatCompact(v, rightKind)} />
          )}
          {tooltip}
          {legend}
          {config.y_keys.map((k, i) => (
            <Bar key={k} yAxisId={axisOf(k)} dataKey={k} fill={C.series[i % C.series.length]} radius={[3, 3, 0, 0]} maxBarSize={44} />
          ))}
        </BarChart>
      </ChartFrame>
      {capped}
    </>
  );
}

// ---------------------------------------------------------------------------
// Forecast — observed history, forecast and the interval band
// ---------------------------------------------------------------------------
function ForecastView({ config, kind }: { config: ChartConfig; kind: ValueKind }) {
  const xKey = config.x_key || "month";
  const data = useMemo<Row[]>(
    () => config.data.map((r) => ({
      ...r,
      __band: isNumeric(r.lower) && isNumeric(r.upper) ? [r.lower, r.upper] : null,
    })),
    [config],
  );
  const firstForecast = data.find((r) => isNumeric(r.forecast))?.[xKey];
  const hasBand = data.some((r) => r.__band);

  const tip = ({ active, payload, label }: TooltipProps<number, string>) => {
    if (!active || !payload?.length) return null;
    const r = payload[0].payload as Row;
    const lines: TipLine[] = [];
    if (isNumeric(r.actual)) lines.push({ label: "Recorded", value: formatValue(r.actual, kind), color: C.navy });
    if (isNumeric(r.forecast)) lines.push({ label: "Forecast", value: formatValue(r.forecast, kind), color: C.primary });
    if (isNumeric(r.lower) && isNumeric(r.upper)) {
      lines.push({ label: "Range (80%)", value: `${formatValue(r.lower, kind)} – ${formatValue(r.upper, kind)}` });
    }
    return <TooltipBox title={formatValue(label, "date")} lines={lines} />;
  };

  return (
    <ChartFrame height={320}>
      <ComposedChart data={data} margin={{ ...MARGIN, top: 22 }}>
        <CartesianGrid vertical={false} stroke={C.grid} />
        <XAxis dataKey={xKey} tick={AXIS} tickLine={false} axisLine={{ stroke: C.grid }}
               tickFormatter={(v) => formatCompact(v, "date")} minTickGap={24} />
        <YAxis tick={AXIS} tickLine={false} axisLine={false} width={64}
               tickFormatter={(v) => formatCompact(v, kind)} />
        <Tooltip content={tip} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {hasBand && (
          <Area type="monotone" dataKey="__band" name="Forecast range (80%)" stroke="none"
                fill={C.primary} fillOpacity={0.12} activeDot={false} isAnimationActive={false} />
        )}
        {firstForecast !== undefined && (
          <ReferenceLine x={firstForecast} stroke={C.axis} strokeDasharray="2 4"
                         label={{ value: "Forecast →", position: "top", fontSize: 11, fill: C.axis }} />
        )}
        <Line type="monotone" dataKey="actual" name="Recorded" stroke={C.navy} strokeWidth={2}
              dot={false} activeDot={{ r: 4 }} connectNulls={false} />
        <Line type="monotone" dataKey="forecast" name="Forecast" stroke={C.primary} strokeWidth={2}
              strokeDasharray="5 4" dot={{ r: 3 }} connectNulls={false} />
      </ComposedChart>
    </ChartFrame>
  );
}

// ---------------------------------------------------------------------------
// Scatter — customer segments, anomalies, or a generic x/y plot
// ---------------------------------------------------------------------------
function SegmentsView({ config }: { config: ChartConfig }) {
  const x = config.x_key;
  const y = config.y_keys[0];
  const xKind = kindOf(x, sampleOf(config.data, x));
  const yKind = kindOf(y, sampleOf(config.data, y));
  const extraKeys = Object.keys(config.data[0]).filter((k) => ![x, y, "cluster", "size"].includes(k));

  const tip = ({ active, payload }: TooltipProps<number, string>) => {
    if (!active || !payload?.length) return null;
    const r = payload[0].payload as Row;
    return (
      <TooltipBox
        title={`Cluster ${r.cluster}`}
        lines={[
          ...(isNumeric(r.size) ? [{ label: "Customers", value: formatValue(r.size, "count") }] : []),
          { label: humanize(x), value: formatValue(r[x], xKind) },
          { label: humanize(y), value: formatValue(r[y], yKind) },
          ...extraKeys.map((k) => ({ label: humanize(k), value: formatValue(r[k], kindOf(k, r[k])) })),
        ]}
      />
    );
  };

  return (
    <ChartFrame height={320}>
      <ScatterChart margin={{ ...MARGIN, top: 16 }}>
        <CartesianGrid stroke={C.grid} />
        <XAxis type="number" dataKey={x} name={humanize(x)} tick={AXIS} tickLine={false} axisLine={{ stroke: C.grid }}
               tickFormatter={(v) => formatCompact(v, xKind)}
               label={{ value: humanize(x), position: "insideBottom", offset: 0, fontSize: 11, fill: C.axis }} height={44} />
        <YAxis type="number" dataKey={y} name={humanize(y)} tick={AXIS} tickLine={false} axisLine={false} width={64}
               tickFormatter={(v) => formatCompact(v, yKind)}
               label={{ value: humanize(y), angle: -90, position: "insideLeft", fontSize: 11, fill: C.axis }} />
        <ZAxis type="number" dataKey="size" range={[80, 900]} name="Customers" />
        <Tooltip content={tip} cursor={{ strokeDasharray: "3 3" }} />
        {config.data.map((r, i) => (
          <Scatter key={String(r.cluster)} name={`Cluster ${r.cluster}`} data={[r]}
                   fill={C.series[i % C.series.length]} fillOpacity={0.75} />
        ))}
        <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
      </ScatterChart>
    </ChartFrame>
  );
}

function PointsView({ config, anomalies }: { config: ChartConfig; anomalies: boolean }) {
  const x = config.x_key;
  const y = config.y_keys[0] ?? "y";
  const xKind = kindOf(x, sampleOf(config.data, x));
  const yKind = kindOf(y, sampleOf(config.data, y));
  const others = Object.keys(config.data[0]).filter((k) => k !== x && k !== y);

  const tip = ({ active, payload }: TooltipProps<number, string>) => {
    if (!active || !payload?.length) return null;
    const r = payload[0].payload as Row;
    const idKey = others.find((k) => /(^id$|_id$|^label$)/.test(k));
    return (
      <TooltipBox
        title={anomalies && idKey ? `Sale #${r[idKey]}` : undefined}
        lines={[
          { label: humanize(x), value: formatValue(r[x], xKind) },
          { label: humanize(y), value: formatValue(r[y], yKind) },
          ...others.filter((k) => k !== idKey).map((k) => ({
            label: k === "score" ? "Anomaly score" : humanize(k),
            value: formatValue(r[k], k === "score" ? "number" : kindOf(k, r[k])),
          })),
        ]}
      />
    );
  };

  return (
    <ChartFrame height={320}>
      <ScatterChart margin={{ ...MARGIN, top: 16 }}>
        <CartesianGrid stroke={C.grid} />
        <XAxis type="number" dataKey={x} name={humanize(x)} tick={AXIS} tickLine={false} axisLine={{ stroke: C.grid }}
               tickFormatter={(v) => formatCompact(v, xKind)}
               label={{ value: humanize(x), position: "insideBottom", offset: 0, fontSize: 11, fill: C.axis }} height={44} />
        <YAxis type="number" dataKey={y} name={humanize(y)} tick={AXIS} tickLine={false} axisLine={false} width={64}
               tickFormatter={(v) => formatCompact(v, yKind)}
               label={{ value: humanize(y), angle: -90, position: "insideLeft", fontSize: 11, fill: C.axis }} />
        <ZAxis range={[56, 56]} />
        <Tooltip content={tip} cursor={{ strokeDasharray: "3 3" }} />
        <Scatter name={anomalies ? "Flagged sale" : config.title} data={config.data}
                 fill={anomalies ? C.warning : C.primary} fillOpacity={0.8} />
      </ScatterChart>
    </ChartFrame>
  );
}

// ---------------------------------------------------------------------------

export function ChartRenderer({ config: raw, forecastKind = "number" }: {
  config: ChartConfig | null;
  /** Unit of forecast values (the chart config doesn't carry it). */
  forecastKind?: ValueKind;
}) {
  const config = useMemo(() => (raw ? normalize(raw) : null), [raw]);
  const variant = chartVariant(config);
  if (!config) return null;
  switch (variant) {
    case "kpi":       return <Kpi config={config} />;
    case "line":      return <LineView config={config} />;
    case "bar":       return <BarView config={config} />;
    case "forecast":  return <ForecastView config={config} kind={forecastKind} />;
    case "segments":  return <SegmentsView config={config} />;
    case "anomalies": return <PointsView config={config} anomalies />;
    case "scatter":   return <PointsView config={config} anomalies={false} />;
    default:          return null;   // "table" / "none" — the caller shows data
  }
}
