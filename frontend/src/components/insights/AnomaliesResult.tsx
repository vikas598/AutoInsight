// AnomaliesResult — Isolation Forest output as returned: flagged sales with
// every feature the model used, so a reviewer can see why each stood out.
// "Price vs cost" is arithmetic on returned fields, labelled as such.
// Flagged records are statistical outliers for review — not errors or fraud.

import { ChartRenderer } from "../ChartRenderer";
import { RichText } from "../RichText";
import { formatValue, isNumeric } from "../../lib/format";
import type { AnomalySummary, ChatResponse } from "../../types";
import { FollowUps, Interpretation, SectionTitle, StatStrip } from "./ResultParts";

interface Row {
  sale_id: number | string;
  sale_price: number;
  listed_price: number;
  discount: number;
  discount_pct: number;
  cost_price: number;
  score: number;
}

interface Props {
  response: ChatResponse;
  summary: AnomalySummary;
  onAsk: (q: string) => void;
}

const inr = (v: unknown) => formatValue(v, "currency");
const pct = (v: number) => `${(v * 100).toLocaleString("en-IN", { maximumFractionDigits: 1 })}%`;

export function AnomaliesResult({ response, summary, onAsk }: Props) {
  const rows = (response.chart_config?.data ?? []) as unknown as Row[];
  const hasCost = rows.some((r) => isNumeric(r.cost_price));
  const belowCost = hasCost ? rows.filter((r) => r.sale_price < r.cost_price).length : null;
  const rate = summary.total_records ? summary.anomalies_found / summary.total_records : 0;
  const top = rows[0];

  return (
    <div className="space-y-6">
      {response.response && <RichText text={response.response} />}

      <StatStrip stats={[
        { label: "Sales flagged for review", value: formatValue(summary.anomalies_found, "count"), hint: `of ${formatValue(summary.total_records, "count")} sales analysed` },
        { label: "Share flagged", value: pct(rate), hint: `Model set to flag about ${pct(summary.contamination)}` },
        { label: "Flagged below cost", value: belowCost === null ? "—" : formatValue(belowCost, "count"), hint: "Sale price lower than the vehicle’s cost price" },
        { label: "Measures compared", value: "5", hint: "Sale, listed & cost price; discount (₹ and %)" },
      ]} />

      <section className="card px-2 pb-3 pt-4 sm:px-3" aria-label="Anomaly chart">
        <div className="px-3 pb-2">
          <SectionTitle sub="Flagged sales only — sale price against discount as a share of the listed price">Flagged sales</SectionTitle>
        </div>
        <ChartRenderer config={response.chart_config} />
      </section>

      <section aria-label="Flagged sales table">
        <SectionTitle sub="Most unusual first. Lower scores are more unusual.">Sales to review</SectionTitle>
        <div className="card max-h-[480px] overflow-auto">
          <table className="min-w-full border-separate border-spacing-0 text-sm">
            <thead className="text-xs text-ink-secondary">
              <tr>
                {["Sale #", "Sale price", "Listed price", "Discount", "Discount %", "Cost price", "Price vs cost", "Anomaly score"].map((h, i) => (
                  <th key={h} scope="col"
                      className={`sticky top-0 z-10 whitespace-nowrap border-b border-line bg-surface-sunken px-4 py-2.5 font-semibold ${i === 0 ? "text-left" : "text-right"}`}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const vsCost = isNumeric(r.cost_price) && r.cost_price ? (r.sale_price - r.cost_price) / r.cost_price : null;
                return (
                  <tr key={String(r.sale_id)} className="hover:bg-surface-sunken/60">
                    <td className="whitespace-nowrap border-b border-line/70 px-4 py-2.5 font-medium text-ink">{String(r.sale_id)}</td>
                    <td className="whitespace-nowrap border-b border-line/70 px-4 py-2.5 text-right tabular-nums text-ink">{inr(r.sale_price)}</td>
                    <td className="whitespace-nowrap border-b border-line/70 px-4 py-2.5 text-right tabular-nums text-ink-secondary">{inr(r.listed_price)}</td>
                    <td className="whitespace-nowrap border-b border-line/70 px-4 py-2.5 text-right tabular-nums text-ink-secondary">{inr(r.discount)}</td>
                    <td className="whitespace-nowrap border-b border-line/70 px-4 py-2.5 text-right tabular-nums text-ink-secondary">{isNumeric(r.discount_pct) ? pct(r.discount_pct) : "—"}</td>
                    <td className="whitespace-nowrap border-b border-line/70 px-4 py-2.5 text-right tabular-nums text-ink-secondary">{inr(r.cost_price)}</td>
                    <td className={`whitespace-nowrap border-b border-line/70 px-4 py-2.5 text-right tabular-nums ${vsCost !== null && vsCost < 0 ? "font-medium text-warning" : "text-ink-secondary"}`}>
                      {vsCost === null ? "—" : `${vsCost >= 0 ? "+" : ""}${pct(vsCost)}`}
                    </td>
                    <td className="whitespace-nowrap border-b border-line/70 px-4 py-2.5 text-right tabular-nums text-ink-secondary">{isNumeric(r.score) ? r.score.toFixed(3) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-2xs text-ink-muted">“Price vs cost” is calculated here from the sale price and cost price above.</p>
      </section>

      <Interpretation points={[
        <>Isolation Forest compares every sale on five measures and flags the ones that are easiest to separate from the rest. A flagged sale is statistically unusual — it is <strong className="font-semibold text-ink">not</strong> evidence of an error or wrongdoing.</>,
        <>The model is set to flag about {pct(summary.contamination)} of sales, so roughly this many will always be flagged, even in clean data.</>,
        <>Sales can be unusual for legitimate reasons — a premium vehicle, an approved promotion, a fleet deal. Each one needs checking against the original paperwork.</>,
        <>Scores only rank sales against each other within this dataset; they are not probabilities.</>,
      ]} />

      <FollowUps onAsk={onAsk} questions={[
        ...(top ? [`Show the full details of sale ${top.sale_id}, including the vehicle and salesperson.`] : []),
        "Which sales were made below the vehicle's cost price?",
        "List sales with a discount above 20% of the listed price.",
      ]} />
    </div>
  );
}
