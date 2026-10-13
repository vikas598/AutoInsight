// InventoryOverview — current vehicle records by status. Statuses come from
// the database's CHECK constraint (zero-filled), so the list is complete and
// each record is counted exactly once.

import { formatValue, humanize } from "../../lib/format";
import type { OverviewResponse } from "../../types";

// Semantic colour per allowed status; unknown statuses fall back to grey
const STATUS_COLOR: Record<string, string> = {
  available: "#059669",
  reserved: "#d97706",
  in_transit: "#2563eb",
  sold: "#94a3b8",
};

const STATUS_HELP: Record<string, string> = {
  available: "In stock and unsold",
  reserved: "Held for a customer",
  in_transit: "On the way to the dealership",
  sold: "Sold — no longer stock",
};

export function InventoryOverview({ inventory }: { inventory: OverviewResponse["inventory"] }) {
  const { total, available, by_status } = inventory;

  return (
    <section className="card p-5" aria-labelledby="inventory-heading">
      <header>
        <h2 id="inventory-heading" className="text-base font-semibold text-ink">Inventory</h2>
        <p className="text-xs text-ink-muted">Current vehicle records · not filtered by the reporting period</p>
      </header>

      {total === 0 ? (
        <p className="mt-6 rounded-control border border-dashed border-line-strong px-4 py-10 text-center text-sm text-ink-muted">
          There are no vehicle records.
        </p>
      ) : (
        <>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-2xl font-semibold tabular-nums text-ink">{formatValue(total, "count")}</span>
            <span className="text-sm text-ink-secondary">vehicle records</span>
          </div>

          {/* Distribution bar */}
          <div className="mt-3 flex h-2.5 overflow-hidden rounded-full bg-surface-sunken" role="img"
               aria-label={by_status.map((s) => `${humanize(s.status)}: ${s.count}`).join(", ")}>
            {by_status.filter((s) => s.count > 0).map((s) => (
              <div key={s.status} style={{ width: `${(s.count / total) * 100}%`, background: STATUS_COLOR[s.status] ?? "#64748b" }} />
            ))}
          </div>

          <ul className="mt-4 divide-y divide-line/70">
            {by_status.map((s) => (
              <li key={s.status} className="flex items-center justify-between gap-3 py-2 text-sm">
                <span className="flex min-w-0 items-center gap-2">
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: STATUS_COLOR[s.status] ?? "#64748b" }} aria-hidden />
                  <span className="font-medium text-ink">{humanize(s.status)}</span>
                  <span className="hidden truncate text-xs text-ink-muted sm:inline">{STATUS_HELP[s.status]}</span>
                </span>
                <span className="shrink-0 tabular-nums text-ink">
                  {formatValue(s.count, "count")}
                  <span className="ml-1.5 text-xs text-ink-muted">{((s.count / total) * 100).toLocaleString("en-IN", { maximumFractionDigits: 1 })}%</span>
                </span>
              </li>
            ))}
          </ul>

          {available === 0 && (
            <p className="mt-3 rounded-control bg-surface-sunken px-3 py-2 text-xs text-ink-secondary">
              No vehicle record currently has the status “available”.
            </p>
          )}
        </>
      )}
    </section>
  );
}
