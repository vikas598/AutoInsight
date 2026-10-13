// Formatting helpers for analytical values. Column semantics are inferred from
// names only — values are never altered, just displayed appropriately.

/**
 * percent: already on a 0–100 scale (column named "...percent...").
 * ratio:   a fraction like discount_pct = 0.12; shown ×100. Values above 1
 *          are assumed to be pre-scaled, since a ratio can't exceed 1 here.
 */
export type ValueKind = "currency" | "percent" | "ratio" | "count" | "number" | "date" | "text";

const CURRENCY_RE = /(price|revenue|amount|cost|spend|salary|income|expense|discount$|value$|profit|margin_amount)/i;
const PERCENT_RE = /(percent|percentage)/i;
const RATIO_RE = /(_pct$|^pct_|_rate$|^rate$|_ratio$|share$)/i;
const COUNT_RE = /(^num_|_count$|^count$|units|quantity|qty|^size$|^n_|total_leads|leads$|sales$|purchases)/i;
const ID_RE = /(^id$|_id$|^label$|^sale_id$|^cluster$)/i;

const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const num = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
const int = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

/** "units_sold" → "Units sold" */
export function humanize(key: string): string {
  const spaced = key.replace(/^__/, "").replace(/_/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export function isNumeric(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

/** Infer how a column should be displayed from its name and a sample value. */
export function kindOf(column: string, sample: unknown): ValueKind {
  if (typeof sample === "string" && /^\d{4}-\d{2}(-\d{2})?/.test(sample)) return "date";
  if (!isNumeric(sample)) return "text";
  if (ID_RE.test(column)) return "text";
  if (PERCENT_RE.test(column)) return "percent";
  if (RATIO_RE.test(column)) return "ratio";
  if (CURRENCY_RE.test(column)) return "currency";
  if (COUNT_RE.test(column)) return "count";
  return "number";
}

function percent(v: number, kind: "percent" | "ratio"): string {
  const scaled = kind === "ratio" && Math.abs(v) <= 1 ? v * 100 : v;
  return `${num.format(Math.round(scaled * 10) / 10)}%`;
}

export function formatDate(v: string): string {
  const m = /^(\d{4})-(\d{2})(?:-(\d{2}))?/.exec(v);
  if (!m) return v;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3] ?? 1));
  return m[3] && m[3] !== "01"
    ? d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })
    : d.toLocaleDateString("en-IN", { month: "short", year: "numeric" });
}

/** Full-precision display value for tables and tooltips. */
export function formatValue(v: unknown, kind: ValueKind): string {
  if (v === null || v === undefined || v === "") return "—";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (kind === "date" && typeof v === "string") return formatDate(v);
  if (!isNumeric(v)) return String(v);
  switch (kind) {
    case "currency": return inr.format(v);
    case "percent":
    case "ratio":    return percent(v, kind);
    case "count":    return int.format(v);
    default:         return num.format(v);
  }
}

/** Compact value for chart axes: ₹12.5L, ₹1.2Cr, 3.4K. */
export function formatCompact(v: unknown, kind: ValueKind): string {
  if (!isNumeric(v)) return typeof v === "string" && kind === "date" ? formatDate(v) : String(v ?? "");
  if (kind === "percent" || kind === "ratio") return percent(v, kind);
  const abs = Math.abs(v);
  const prefix = kind === "currency" ? "₹" : "";
  if (abs >= 1e7) return `${prefix}${num.format(Math.round((v / 1e7) * 10) / 10)}Cr`;
  if (abs >= 1e5) return `${prefix}${num.format(Math.round((v / 1e5) * 10) / 10)}L`;
  if (abs >= 1e3 && kind !== "currency") return `${num.format(Math.round((v / 1e3) * 10) / 10)}K`;
  return kind === "currency" ? inr.format(v) : num.format(v);
}

/**
 * Numeric columns that identify a group rather than measure something
 * (a model year, a month number). The backend's chart picker treats every
 * numeric column as a series; these are better shown as part of the label.
 */
const DIMENSION_RE = /^(year|month|quarter|week|day|model_year|[a-z_]*_year|[a-z_]*_id|id)$/i;

export function isDimension(column: string): boolean {
  return DIMENSION_RE.test(column);
}

export function plural(n: number, word: string): string {
  return `${int.format(n)} ${word}${n === 1 ? "" : "s"}`;
}

/** Headline INR value in Indian units: ₹36.06 Cr, ₹12.02 L, ₹48,500. */
export function formatINRShort(v: number): string {
  const abs = Math.abs(v);
  const two = (x: number) => x.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (abs >= 1e7) return `₹${two(v / 1e7)} Cr`;
  if (abs >= 1e5) return `₹${two(v / 1e5)} L`;
  return inr.format(v);
}

/** "2024-03" → "Mar 2024"; "2024-03" short → "Mar". */
export function monthLabel(ym: string, short = false): string {
  const [y, m] = ym.split("-").map(Number);
  const d = new Date(y, m - 1, 1);
  return d.toLocaleDateString("en-IN", short ? { month: "short" } : { month: "short", year: "numeric" });
}

/** ISO date → "31 Dec 2024". */
export function longDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}
