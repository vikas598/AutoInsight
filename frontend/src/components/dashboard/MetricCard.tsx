// MetricCard — one KPI. Never shows 0 for a value that failed to load:
// loading → skeleton, unavailable → "—" with the reason.

import type { LucideIcon } from "lucide-react";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

export interface MetricDelta {
  /** Percentage change vs. the comparison period. */
  pct: number;
  /** e.g. "vs 2023 (₹31.79 Cr)" */
  against: string;
  /** Whether a rise is good news. "neutral" colours nothing. */
  polarity: "higher-is-better" | "neutral";
}

interface Props {
  label: string;
  icon: LucideIcon;
  value: string | null;
  /** Precise definition / full value, shown under the number. */
  caption?: string;
  delta?: MetricDelta | null;
  /** Why there is no comparison (shown instead of a delta). */
  deltaNote?: string | null;
  loading?: boolean;
  unavailable?: string | null;
}

export function MetricCard({ label, icon: Icon, value, caption, delta, deltaNote, loading, unavailable }: Props) {
  return (
    <section className="card flex min-h-[148px] flex-col p-5" aria-label={label} aria-busy={loading}>
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-ink-secondary">{label}</h3>
        <Icon className="h-4 w-4 text-ink-muted" aria-hidden />
      </div>

      {loading ? (
        <div className="mt-3 space-y-2" aria-hidden>
          <div className="h-8 w-32 animate-pulse rounded bg-surface-sunken" />
          <div className="h-3 w-40 animate-pulse rounded bg-surface-sunken" />
        </div>
      ) : unavailable || value === null ? (
        <>
          <p className="mt-2 text-[28px] font-semibold leading-tight text-ink-muted">—</p>
          <p className="mt-1 text-xs text-ink-muted">{unavailable ?? "Not available"}</p>
        </>
      ) : (
        <>
          <p className="mt-2 text-[28px] font-semibold leading-tight tracking-tight text-ink tabular-nums">{value}</p>
          {caption && <p className="mt-1 text-xs leading-snug text-ink-muted">{caption}</p>}
          <div className="mt-auto pt-3">
            {delta ? <Delta {...delta} /> : deltaNote ? <p className="text-xs text-ink-muted">{deltaNote}</p> : null}
          </div>
        </>
      )}
    </section>
  );
}

function Delta({ pct, against, polarity }: MetricDelta) {
  const flat = Math.abs(pct) < 0.05;
  const up = pct > 0;
  const tone = flat || polarity === "neutral"
    ? "text-ink-secondary bg-surface-sunken"
    : up ? "text-success bg-success-soft" : "text-danger bg-danger-soft";
  const Arrow = flat ? Minus : up ? ArrowUpRight : ArrowDownRight;
  const sign = up && !flat ? "+" : "";
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
      <span className={`inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 font-semibold tabular-nums ${tone}`}>
        <Arrow className="h-3.5 w-3.5" aria-hidden />
        {sign}{pct.toLocaleString("en-IN", { maximumFractionDigits: 1 })}%
      </span>
      <span className="text-ink-muted">{against}</span>
    </p>
  );
}
