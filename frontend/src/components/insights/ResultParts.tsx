// Building blocks shared by the three analysis result views.

import type { ReactNode } from "react";
import { ArrowRight, Info, TriangleAlert } from "lucide-react";

export interface Stat {
  label: string;
  value: string;
  hint?: string;
}

/** Row of model-returned metrics. */
export function StatStrip({ stats }: { stats: Stat[] }) {
  return (
    <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-card border border-line bg-line lg:grid-cols-4">
      {stats.map((s) => (
        <div key={s.label} className="bg-surface px-4 py-3">
          <dt className="text-xs text-ink-muted">{s.label}</dt>
          <dd className="mt-0.5 text-lg font-semibold tabular-nums text-ink">{s.value}</dd>
          {s.hint && <dd className="mt-0.5 text-2xs leading-snug text-ink-muted">{s.hint}</dd>}
        </div>
      ))}
    </dl>
  );
}

export function SectionTitle({ children, sub }: { children: ReactNode; sub?: string }) {
  return (
    <div className="mb-3">
      <h3 className="text-sm font-semibold text-ink">{children}</h3>
      {sub && <p className="text-xs text-ink-muted">{sub}</p>}
    </div>
  );
}

/** A limitation or caveat that applies to this specific result. */
export function Caveat({ children }: { children: ReactNode }) {
  return (
    <div role="note" className="flex gap-2.5 rounded-control border border-warning/30 bg-warning-soft px-4 py-3 text-sm text-ink">
      <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
      <div className="space-y-1">{children}</div>
    </div>
  );
}

/** How to read the result, and what it does not tell you. */
export function Interpretation({ points }: { points: ReactNode[] }) {
  return (
    <section className="rounded-card border border-line bg-surface-sunken/60 px-5 py-4" aria-label="How to interpret this result">
      <h3 className="flex items-center gap-1.5 text-sm font-semibold text-ink">
        <Info className="h-4 w-4 text-ink-muted" aria-hidden />
        How to read this
      </h3>
      <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-ink-secondary marker:text-ink-muted">
        {points.map((p, i) => <li key={i}>{p}</li>)}
      </ul>
    </section>
  );
}

/** Questions that continue the investigation in the AI Analyst. */
export function FollowUps({ questions, onAsk }: { questions: string[]; onAsk: (q: string) => void }) {
  return (
    <section aria-label="Continue in the AI Analyst">
      <SectionTitle sub="Opens the AI Analyst and asks the question about your data">Continue exploring</SectionTitle>
      <ul className="flex flex-wrap gap-2">
        {questions.map((q) => (
          <li key={q}>
            <button
              type="button"
              onClick={() => onAsk(q)}
              className="focus-ring group inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1.5 text-left text-xs font-medium text-ink-secondary shadow-card transition-colors hover:border-primary/40 hover:text-ink"
            >
              {q}
              <ArrowRight className="h-3.5 w-3.5 shrink-0 text-primary transition-transform group-hover:translate-x-0.5" aria-hidden />
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
