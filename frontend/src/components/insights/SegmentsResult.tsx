// SegmentsResult — K-Means customer segments exactly as returned. Segments
// are identified by the model's cluster number; no names or personas are
// invented. Values per cluster are the cluster centre (the average customer).

import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ChartRenderer } from "../ChartRenderer";
import { RichText } from "../RichText";
import { formatINRShort, formatValue, humanize, isNumeric } from "../../lib/format";
import type { ChatResponse, ClusterSummary } from "../../types";
import { Caveat, FollowUps, Interpretation, SectionTitle, StatStrip } from "./ResultParts";

interface Props {
  response: ChatResponse;
  summary: ClusterSummary;
  onAsk: (q: string) => void;
}

const money = (k: string) => /spend|price/.test(k);

// Readable names for the clustering features (ml_agent: num_purchases,
// total_spend, avg_sale_price); anything else falls back to humanize()
const FEATURE_LABEL: Record<string, string> = {
  num_purchases: "purchases",
  total_spend: "total spend",
  avg_sale_price: "sale price",
};
const label = (f: string) => FEATURE_LABEL[f] ?? humanize(f).toLowerCase();

export function SegmentsResult({ response, summary, onAsk }: Props) {
  const rows = (response.chart_config?.data ?? []) as Record<string, unknown>[];
  const features = rows.length ? Object.keys(rows[0]).filter((k) => k !== "cluster" && k !== "size") : [];
  const total = rows.reduce((s, r) => s + (isNumeric(r.size) ? r.size : 0), 0);

  const scores = Object.entries(summary.all_scores ?? {})
    .map(([k, v]) => ({ k: Number(k), score: v }))
    .sort((a, b) => a.k - b.k);
  const spread = scores.length > 1 ? Math.max(...scores.map((s) => s.score)) - Math.min(...scores.map((s) => s.score)) : null;
  const runnerUp = [...scores].sort((a, b) => b.score - a.score)[1];
  const closeCall = runnerUp && summary.silhouette_score - runnerUp.score < 0.02;

  return (
    <div className="space-y-6">
      {response.response && <RichText text={response.response} />}

      <StatStrip stats={[
        { label: "Segments found", value: String(summary.k), hint: `Best of k = ${scores[0]?.k ?? "?"}–${scores[scores.length - 1]?.k ?? "?"} tried` },
        { label: "Customers grouped", value: formatValue(summary.n_customers, "count"), hint: "Customers with at least one purchase" },
        { label: "Silhouette score", value: summary.silhouette_score.toFixed(3), hint: "−1 to 1; higher means better-separated groups" },
        { label: "Based on", value: `${features.length} measures`, hint: features.map(label).join(", ") },
      ]} />

      {closeCall && (
        <Caveat>
          <p className="font-medium">The number of segments is not clear-cut.</p>
          <p className="text-ink-secondary">
            k = {summary.k} scored {summary.silhouette_score.toFixed(3)} and k = {runnerUp.k} scored {runnerUp.score.toFixed(3)}
            {spread !== null && <> (all options were within {spread.toFixed(3)} of each other)</>}. The model picks the highest score,
            but a different number of segments would describe the customers almost as well.
          </p>
        </Caveat>
      )}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <section className="card px-2 pb-3 pt-4 sm:px-3 xl:col-span-2" aria-label="Segment chart">
          <div className="px-3 pb-2">
            <SectionTitle sub="Each bubble is a segment’s average customer; size shows how many customers it has">Segments by spend and purchases</SectionTitle>
          </div>
          <ChartRenderer config={response.chart_config} />
        </section>

        {scores.length > 0 && (
          <section className="card p-4" aria-label="Silhouette score by number of segments">
            <SectionTitle sub="How well-separated the groups are for each k tried">Choosing the number of segments</SectionTitle>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={scores} margin={{ top: 4, right: 4, left: -8, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke="#e9eef5" />
                  <XAxis dataKey="k" tick={{ fontSize: 11, fill: "#64748b" }} tickLine={false} axisLine={{ stroke: "#e9eef5" }}
                         label={{ value: "Segments (k)", position: "insideBottom", offset: -2, fontSize: 11, fill: "#64748b" }} height={36} />
                  <YAxis tick={{ fontSize: 11, fill: "#64748b" }} tickLine={false} axisLine={false} width={44}
                         domain={[0, "auto"]} tickFormatter={(v) => Number(v).toFixed(2)} />
                  <Tooltip formatter={(v) => [Number(v).toFixed(3), "Silhouette"]} labelFormatter={(k) => `k = ${k}`}
                           cursor={{ fill: "rgba(37, 99, 235, 0.06)" }} />
                  <Bar dataKey="score" radius={[3, 3, 0, 0]} maxBarSize={28}>
                    {scores.map((s) => <Cell key={s.k} fill={s.k === summary.k ? "#2563eb" : "#cbd5e1"} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <p className="mt-1 text-2xs text-ink-muted">Blue: the k the model chose.</p>
          </section>
        )}
      </div>

      <section aria-label="Segment details">
        <SectionTitle sub="Cluster numbers are arbitrary labels from the model">Segment details</SectionTitle>
        <div className="card overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-surface-sunken text-xs text-ink-secondary">
              <tr>
                <th scope="col" className="px-4 py-2.5 text-left font-semibold">Segment</th>
                <th scope="col" className="px-4 py-2.5 text-right font-semibold">Customers</th>
                <th scope="col" className="px-4 py-2.5 text-right font-semibold">Share</th>
                {features.map((f) => (
                  <th key={f} scope="col" className="whitespace-nowrap px-4 py-2.5 text-right font-semibold">Avg. {label(f)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...rows].sort((a, b) => Number(b.size) - Number(a.size)).map((r) => (
                <tr key={String(r.cluster)} className="border-t border-line/70">
                  <td className="whitespace-nowrap px-4 py-2.5 font-medium text-ink">Cluster {String(r.cluster)}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-ink">{formatValue(r.size, "count")}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-ink-secondary">
                    {total && isNumeric(r.size) ? `${((r.size / total) * 100).toFixed(1)}%` : "—"}
                  </td>
                  {features.map((f) => (
                    <td key={f} className="whitespace-nowrap px-4 py-2.5 text-right tabular-nums text-ink-secondary">
                      {isNumeric(r[f]) ? (money(f) ? formatINRShort(r[f] as number) : formatValue(r[f], "number")) : "—"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <Interpretation points={[
        <>K-Means places customers into groups whose {features.map(label).join(", ")} are similar. It uses only these measures — not location, demographics or which vehicles were bought.</>,
        <>The figures for each segment are its average customer (the cluster centre). Individual customers in a segment can differ from it.</>,
        <>The number of segments is the one with the highest silhouette score among those tried; it is a statistical choice, not a business definition. Segment numbers carry no meaning or order.</>,
        <>Customers with no purchases are not included.</>,
      ]} />

      <FollowUps onAsk={onAsk} questions={[
        "Which 10 customers have the highest total spend?",
        "How many customers have made more than one purchase?",
        "What is the average sale price by vehicle make?",
      ]} />
    </div>
  );
}
