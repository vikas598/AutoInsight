// ForecastResult — SARIMA/ARIMA forecast exactly as returned. Negative
// predictions or bounds are shown as-is and called out, never clipped.

import { ChartRenderer, chartCaption } from "../ChartRenderer";
import { RichText } from "../RichText";
import { formatINRShort, formatValue, isNumeric, monthLabel, type ValueKind } from "../../lib/format";
import type { ChatResponse, ForecastSummary } from "../../types";
import { Caveat, FollowUps, Interpretation, SectionTitle, StatStrip } from "./ResultParts";

interface Row { month: string; actual: number | null; forecast: number | null; lower: number | null; upper: number | null }

interface Props {
  response: ChatResponse;
  summary: ForecastSummary;
  onAsk: (q: string) => void;
}

export function ForecastResult({ response, summary, onAsk }: Props) {
  const revenue = summary.metric === "revenue";
  const kind: ValueKind = revenue ? "currency" : "number";
  const fmt = (v: number) => (revenue ? formatINRShort(v) : formatValue(v, "number"));
  const unit = revenue ? "Revenue (₹)" : "Units sold";

  const rows = (response.chart_config?.data ?? []) as unknown as Row[];
  const history = rows.filter((r) => isNumeric(r.actual));
  const future = rows.filter((r) => isNumeric(r.forecast));
  const negative = future.filter((r) => (r.forecast ?? 0) < 0 || (r.lower ?? 0) < 0);

  const span = (rs: Row[]) => (rs.length ? `${monthLabel(rs[0].month)} – ${monthLabel(rs[rs.length - 1].month)}` : "—");

  return (
    <div className="space-y-6">
      {response.response && <RichText text={response.response} />}

      <StatStrip stats={[
        { label: "Forecasting", value: unit, hint: `${summary.horizon_months} months: ${span(future)}` },
        { label: "Model", value: summary.model.startsWith("SARIMA") ? "Seasonal ARIMA" : "ARIMA", hint: summary.model },
        { label: "History used", value: `${summary.n_training} months`, hint: span(history) },
        {
          label: "In-sample RMSE",
          value: revenue ? formatINRShort(summary.rmse) : `${formatValue(summary.rmse, "number")} units`,
          hint: "Typical error on the history the model was fitted to",
        },
      ]} />

      {negative.length > 0 && (
        <Caveat>
          <p className="font-medium">
            The forecast range falls below zero for {negative.map((r) => monthLabel(r.month)).join(", ")}.
          </p>
          <p className="text-ink-secondary">
            Sales cannot be negative. This reflects how uncertain the model is with {summary.n_training} months
            of history ({Math.floor(summary.n_training / 12)} seasonal cycles). Values are shown exactly as the model
            returned them; treat the lower end of these ranges as “very low”, not as a real figure.
          </p>
        </Caveat>
      )}

      <section className="card px-2 pb-3 pt-4 sm:px-3" aria-label="Forecast chart">
        <div className="px-3 pb-2"><SectionTitle sub={chartCaption(response.chart_config!) ?? undefined}>{unit}: recorded and forecast</SectionTitle></div>
        <ChartRenderer config={response.chart_config} forecastKind={kind} />
      </section>

      <section aria-label="Forecast values">
        <SectionTitle sub="Predicted value and 80% range for each forecast month">Forecast by month</SectionTitle>
        <div className="card overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-surface-sunken text-xs text-ink-secondary">
              <tr>
                <th scope="col" className="px-4 py-2.5 text-left font-semibold">Month</th>
                <th scope="col" className="px-4 py-2.5 text-right font-semibold">Forecast</th>
                <th scope="col" className="px-4 py-2.5 text-right font-semibold">80% range — low</th>
                <th scope="col" className="px-4 py-2.5 text-right font-semibold">80% range — high</th>
              </tr>
            </thead>
            <tbody>
              {future.map((r) => (
                <tr key={r.month} className="border-t border-line/70">
                  <td className="whitespace-nowrap px-4 py-2.5 text-ink">{monthLabel(r.month)}</td>
                  <td className="whitespace-nowrap px-4 py-2.5 text-right font-medium tabular-nums text-ink">{fmt(r.forecast!)}</td>
                  {[r.lower, r.upper].map((v, i) => (
                    <td key={i} className={`whitespace-nowrap px-4 py-2.5 text-right tabular-nums ${isNumeric(v) && v < 0 ? "text-warning" : "text-ink-secondary"}`}>
                      {isNumeric(v) ? fmt(v) : "—"}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <Interpretation points={[
        <>The model ({summary.model}) learns the trend and the 12-month seasonal pattern from {summary.n_training} months of recorded {revenue ? "revenue" : "sales"} and projects it forward.</>,
        <>The 80% range means that, if the model’s assumptions hold, the actual value would fall inside it about 8 times in 10. Wider ranges mean more uncertainty.</>,
        <>RMSE is measured on the same history the model was fitted to, not on held-out months, so it does not establish how accurate the forecast will be.</>,
        <>The forecast starts after the last recorded month ({history.length ? monthLabel(history[history.length - 1].month) : "—"}), not from today. It assumes past patterns continue and cannot account for prices, stock, promotions or market changes.</>,
      ]} />

      <FollowUps onAsk={onAsk} questions={revenue
        ? ["Show monthly revenue for 2024 compared with 2023.", "Which months had the highest revenue in each year?", "Which vehicle models brought in the most revenue in 2024?"]
        : ["Show me the monthly sales trend.", "Which months had the most sales in each year?", "Which vehicle models sold the most in 2024?"]} />
    </div>
  );
}
