// WelcomeState — first screen of an empty conversation. Every suggestion
// submits a real request; nothing here is a pre-baked result.

import { ArrowUpRight } from "lucide-react";
import { DATA_COVERAGE, SUGGESTED_PROMPTS } from "../analystPrompts";

interface Props {
  onAsk: (question: string) => void;
  disabled: boolean;
}

export function WelcomeState({ onAsk, disabled }: Props) {
  return (
    <section aria-labelledby="welcome-heading" className="mx-auto max-w-3xl py-6 sm:py-10">
      <p className="eyebrow">AI Analyst</p>
      <h2 id="welcome-heading" className="mt-2 text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">
        What would you like to know about your dealership?
      </h2>
      <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-ink-secondary">
        Ask in plain language about sales, inventory, customers, leads and service — or request
        forecasts, customer segments and anomaly checks. Proposed data changes always wait for
        your approval.
      </p>
      <p className="mt-3 text-xs text-ink-muted">Records available: {DATA_COVERAGE}</p>

      <h3 className="eyebrow mt-8">Try a question</h3>
      <ul className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {SUGGESTED_PROMPTS.map(({ category, question, icon: Icon }) => (
          <li key={question}>
            <button
              type="button"
              onClick={() => onAsk(question)}
              disabled={disabled}
              className="focus-ring group flex h-full w-full flex-col rounded-card border border-line bg-surface p-4 text-left shadow-card transition-colors hover:border-primary/40 hover:bg-primary-soft/40 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <span className="flex w-full items-center justify-between">
                <span className="inline-flex items-center gap-2 text-xs font-medium text-ink-muted">
                  <Icon className="h-4 w-4 text-primary" aria-hidden />
                  {category}
                </span>
                <ArrowUpRight
                  className="h-4 w-4 text-ink-muted opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100"
                  aria-hidden
                />
              </span>
              <span className="mt-2 text-sm font-medium leading-snug text-ink">{question}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
