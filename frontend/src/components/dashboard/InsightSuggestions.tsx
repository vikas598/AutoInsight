// InsightSuggestions — suggested analyses (not findings). Each opens the AI
// Analyst and asks the question through the normal chat request.

import { ArrowRight } from "lucide-react";
import { SUGGESTED_PROMPTS } from "../../analystPrompts";

// The analyses most useful from an overview; same wording as the Analyst's
// own suggestions so they behave identically
const CATEGORIES = ["Trends", "Forecast", "Segmentation", "Anomalies", "Leads"];

const WHY: Record<string, string> = {
  Trends: "See how monthly sales have moved over time.",
  Forecast: "Project the next three months from recorded history.",
  Segmentation: "Group customers by how much and how often they buy.",
  Anomalies: "Surface sales with unusual prices or discounts to review.",
  Leads: "Compare which lead sources convert best.",
};

export function InsightSuggestions({ onAsk }: { onAsk: (question: string) => void }) {
  const items = SUGGESTED_PROMPTS.filter((p) => CATEGORIES.includes(p.category));

  return (
    <section aria-labelledby="explore-heading">
      <header className="mb-3">
        <h2 id="explore-heading" className="text-base font-semibold text-ink">Analyses to explore</h2>
        <p className="text-xs text-ink-muted">Suggested questions — each opens the AI Analyst and runs the analysis on your data.</p>
      </header>
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {items.map(({ category, question, icon: Icon }) => (
          <li key={question}>
            <button
              type="button"
              onClick={() => onAsk(question)}
              className="focus-ring group flex h-full w-full flex-col rounded-card border border-line bg-surface p-4 text-left shadow-card transition-colors hover:border-primary/40 hover:bg-primary-soft/40"
            >
              <span className="inline-flex items-center gap-2 text-xs font-medium text-ink-muted">
                <Icon className="h-4 w-4 text-primary" aria-hidden />
                {category}
              </span>
              <span className="mt-2 text-sm font-medium leading-snug text-ink">{question}</span>
              <span className="mt-1 text-xs leading-snug text-ink-muted">{WHY[category]}</span>
              <span className="mt-auto inline-flex items-center gap-1 pt-3 text-xs font-medium text-primary">
                Ask the analyst
                <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
