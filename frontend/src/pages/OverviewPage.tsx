// OverviewPage — dealership performance at a glance. Every figure comes from
// GET /api/dashboard/overview (deterministic SQL, no LLM); recent activity
// from GET /api/audit. See backend/app/services/dashboard_service.py for the
// exact metric definitions.

import { Boxes, CalendarRange, CarFront, CircleAlert, History, IndianRupee, ReceiptIndianRupee, RefreshCw } from "lucide-react";
import { InsightSuggestions } from "../components/dashboard/InsightSuggestions";
import { InventoryOverview } from "../components/dashboard/InventoryOverview";
import { MetricCard, type MetricDelta } from "../components/dashboard/MetricCard";
import { RecentActivity } from "../components/dashboard/RecentActivity";
import { SalesTrendChart } from "../components/dashboard/SalesTrendChart";
import { VehiclePerformance } from "../components/dashboard/VehiclePerformance";
import { PageContainer } from "../components/layout/PageContainer";
import { Button } from "../components/ui/Button";
import type { OverviewState } from "../hooks/useOverview";
import { formatINRShort, formatValue, longDate } from "../lib/format";
import type { MetricValue, OverviewResponse, ReportingPeriod } from "../types";

/** Data whose latest sale is older than this is labelled historical. */
const HISTORICAL_AFTER_DAYS = 60;

interface Props {
  state: OverviewState;
  onAsk: (question: string) => void;
}

export function OverviewPage({ state, onAsk }: Props) {
  const { overview, activity, busy, refresh, choosePeriod, shownPeriod } = state;
  const data = overview.status === "ready" ? overview.data : null;
  const loading = overview.status === "loading" || overview.status === "idle";

  return (
    <PageContainer>
      <div className="space-y-6">
        <DashboardHeader
          data={data}
          busy={busy}
          shownPeriod={shownPeriod}
          onPeriod={choosePeriod}
          onRefresh={refresh}
        />

        {overview.status === "error" ? (
          <div role="alert" className="card flex flex-wrap items-center justify-between gap-4 border-danger/30 px-5 py-4">
            <div className="flex items-start gap-3">
              <CircleAlert className="mt-0.5 h-5 w-5 shrink-0 text-danger" aria-hidden />
              <div>
                <p className="text-sm font-semibold text-ink">The dashboard could not be loaded</p>
                <p className="text-sm text-ink-secondary">{overview.message}</p>
              </div>
            </div>
            <Button icon={RefreshCw} onClick={refresh}>Try again</Button>
          </div>
        ) : (
          <>
            <KpiGrid data={data} loading={loading} />

            {loading ? (
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-3" aria-hidden>
                <div className="card h-[420px] animate-pulse bg-surface lg:col-span-2" />
                <div className="card h-[420px] animate-pulse bg-surface" />
              </div>
            ) : data && data.period ? (
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                <div className="min-w-0 lg:col-span-2">
                  <SalesTrendChart monthly={data.monthly} periodLabel={periodText(data.period)} />
                </div>
                <VehiclePerformance models={data.top_models} periodLabel={periodText(data.period)} />
              </div>
            ) : (
              <p className="card px-5 py-8 text-center text-sm text-ink-muted">
                There are no sales records yet, so sales trends and model rankings are not available.
              </p>
            )}

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
              {data ? <InventoryOverview inventory={data.inventory} /> : <div className="card h-72 animate-pulse" aria-hidden />}
              <div className="min-w-0 lg:col-span-2">
                <RecentActivity activity={activity} />
              </div>
            </div>
          </>
        )}

        <InsightSuggestions onAsk={onAsk} />
      </div>
    </PageContainer>
  );
}

// ---------------------------------------------------------------------------

function periodText(p: ReportingPeriod): string {
  // end_exclusive is a calendar date; step back one day in UTC (timezone-safe)
  const [y, m, d] = p.end_exclusive.split("-").map(Number);
  const lastDay = new Date(Date.UTC(y, m - 1, d - 1)).toISOString().slice(0, 10);
  return `${longDate(p.start)} – ${longDate(lastDay)}`;
}

function DashboardHeader({ data, busy, shownPeriod, onPeriod, onRefresh }: {
  data: OverviewResponse | null;
  busy: boolean;
  shownPeriod: string | null;
  onPeriod: (id: string) => void;
  onRefresh: () => void;
}) {
  const last = data?.data_extent?.last_sale_date;
  const historical = last
    ? (Date.now() - new Date(last).getTime()) / 86_400_000 > HISTORICAL_AFTER_DAYS
    : false;

  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        <p className="text-sm text-ink-secondary sm:hidden">A clear view of your dealership’s performance.</p>
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
          <label htmlFor="period" className="inline-flex items-center gap-1.5 text-xs font-medium text-ink-muted">
            <CalendarRange className="h-4 w-4" aria-hidden />
            Reporting period
          </label>
          <select
            id="period"
            value={shownPeriod ?? ""}
            onChange={(e) => onPeriod(e.target.value)}
            disabled={!data?.periods.length}
            className="focus-ring h-9 rounded-control border border-line-strong bg-surface px-3 pr-8 text-sm font-medium text-ink disabled:opacity-60"
          >
            {!data?.periods.length && <option value="">—</option>}
            {data?.periods.map((p) => (
              <option key={p.id} value={p.id}>{p.id === "all" ? `All data (${p.label})` : p.label}</option>
            ))}
          </select>
          {data?.period && (
            <span className="text-sm text-ink-secondary">
              {periodText(data.period)}
              {data.comparison && <span className="text-ink-muted"> · compared with {data.comparison.label}</span>}
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {historical && last && (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-warning/30 bg-warning-soft px-2.5 py-1 text-xs font-medium text-warning"
                title="These figures come from historical records, not live transactions.">
            <History className="h-3.5 w-3.5" aria-hidden />
            Historical data · latest sale {longDate(last)}
          </span>
        )}
        {data && (
          <span className="text-xs text-ink-muted" aria-live="polite">
            {busy ? "Refreshing…" : `Updated ${new Date(data.generated_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}`}
          </span>
        )}
        <Button size="sm" icon={RefreshCw} onClick={onRefresh} disabled={busy} aria-label="Refresh dashboard">
          Refresh
        </Button>
      </div>
    </header>
  );
}

// ---------------------------------------------------------------------------

function delta(m: MetricValue, comparison: ReportingPeriod | null, fmt: (v: number) => string): MetricDelta | null {
  if (!comparison || m.value === null || m.previous === null || m.previous === 0) return null;
  return {
    pct: ((m.value - m.previous) / m.previous) * 100,
    against: `vs ${comparison.label} (${fmt(m.previous)})`,
    polarity: "higher-is-better",
  };
}

function KpiGrid({ data, loading }: { data: OverviewResponse | null; loading: boolean }) {
  const k = data?.kpis;
  const cmp = data?.comparison ?? null;
  const noSales = data && !data.period ? "No sales records" : null;
  const note = data?.comparison_unavailable_reason ?? null;
  const count = (v: number) => formatValue(v, "count");

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <MetricCard
        label="Total revenue"
        icon={IndianRupee}
        loading={loading}
        unavailable={noSales}
        value={k?.total_revenue.value != null ? formatINRShort(k.total_revenue.value) : null}
        caption={k?.total_revenue.value != null
          ? `${formatValue(k.total_revenue.value, "currency")} · sum of sale prices, net of discounts`
          : undefined}
        delta={k ? delta(k.total_revenue, cmp, formatINRShort) : null}
        deltaNote={note}
      />
      <MetricCard
        label="Units sold"
        icon={CarFront}
        loading={loading}
        unavailable={noSales}
        value={k?.units_sold.value != null ? count(k.units_sold.value) : null}
        caption="Number of recorded sales"
        delta={k ? delta(k.units_sold, cmp, count) : null}
        deltaNote={note}
      />
      <MetricCard
        label="Average sale value"
        icon={ReceiptIndianRupee}
        loading={loading}
        unavailable={noSales ?? (k && k.average_sale_value.value === null ? "No sales in this period to average" : null)}
        value={k?.average_sale_value.value != null ? formatINRShort(k.average_sale_value.value) : null}
        caption="Total revenue ÷ units sold"
        delta={k ? delta(k.average_sale_value, cmp, formatINRShort) : null}
        deltaNote={note}
      />
      <MetricCard
        label="Available inventory"
        icon={Boxes}
        loading={loading}
        value={k?.available_inventory.value != null ? count(k.available_inventory.value) : null}
        caption={data ? `Vehicles with status “available”, of ${count(data.inventory.total)} records` : undefined}
        deltaNote="Current snapshot — not tied to the reporting period"
      />
    </div>
  );
}
