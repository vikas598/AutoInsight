// VehiclePerformance — best-selling models (make + model) in the period,
// ranked by units sold, with revenue. Each row is one distinct make+model.

import { formatINRShort, formatValue } from "../../lib/format";
import type { OverviewResponse } from "../../types";

interface Props {
  models: OverviewResponse["top_models"];
  periodLabel: string;
}

export function VehiclePerformance({ models, periodLabel }: Props) {
  const max = Math.max(1, ...models.map((m) => m.units));

  return (
    <section className="card p-5" aria-labelledby="models-heading">
      <header>
        <h2 id="models-heading" className="text-base font-semibold text-ink">Top-selling models</h2>
        <p className="text-xs text-ink-muted">Ranked by units sold · {periodLabel}</p>
      </header>

      {models.length === 0 ? (
        <p className="mt-6 rounded-control border border-dashed border-line-strong px-4 py-10 text-center text-sm text-ink-muted">
          No vehicles were sold in this period.
        </p>
      ) : (
        <table className="mt-4 w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-ink-muted">
              <th scope="col" className="w-8 pb-2 font-medium">#</th>
              <th scope="col" className="pb-2 font-medium">Model</th>
              <th scope="col" className="pb-2 text-right font-medium">Units</th>
              <th scope="col" className="hidden pb-2 text-right font-medium sm:table-cell">Revenue</th>
            </tr>
          </thead>
          <tbody>
            {models.map((m, i) => (
              <tr key={`${m.make}|${m.model}`} className="border-t border-line/70">
                <td className="py-2.5 align-top text-xs tabular-nums text-ink-muted">{i + 1}</td>
                <td className="py-2.5 pr-3">
                  <div className="flex flex-wrap items-baseline gap-x-1.5">
                    <span className="font-medium text-ink">{m.model}</span>
                    <span className="text-xs text-ink-muted">{m.make}</span>
                  </div>
                  <div className="mt-1.5 h-1.5 rounded-full bg-surface-sunken" aria-hidden>
                    <div className="h-full rounded-full bg-primary/80" style={{ width: `${(m.units / max) * 100}%` }} />
                  </div>
                </td>
                <td className="whitespace-nowrap py-2.5 pl-2 text-right align-top font-semibold tabular-nums text-ink">{formatValue(m.units, "count")}</td>
                <td className="hidden whitespace-nowrap py-2.5 pl-3 text-right align-top tabular-nums text-ink-secondary sm:table-cell"
                    title={formatValue(m.revenue, "currency")}>
                  {formatINRShort(m.revenue)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
