// PlaceholderPage — honest stand-in for destinations not yet built.
// Shows what the page is for; never shows sample data.

import { ArrowRight } from "lucide-react";
import { PageContainer } from "../components/layout/PageContainer";
import { Button } from "../components/ui/Button";
import type { NavItem, RouteId } from "../navigation";

interface Props {
  item: NavItem;
  /** What the page will do once built. */
  summary: string;
  onNavigate: (route: RouteId) => void;
}

export function PlaceholderPage({ item, summary, onNavigate }: Props) {
  const Icon = item.icon;
  return (
    <PageContainer>
      <section className="card mx-auto max-w-2xl px-6 py-12 text-center sm:px-10">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-card bg-primary-soft">
          <Icon className="h-6 w-6 text-primary" aria-hidden />
        </div>
        <span className="mt-5 inline-block rounded-full border border-line bg-surface-sunken px-2.5 py-0.5 text-2xs font-medium text-ink-muted">
          Not yet available
        </span>
        <h2 className="mt-3 text-xl font-semibold tracking-tight text-ink">{item.label}</h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-ink-secondary">{summary}</p>
        <div className="mt-8">
          <Button variant="primary" icon={ArrowRight} onClick={() => onNavigate("analyst")}>
            Open AI Analyst
          </Button>
        </div>
      </section>
    </PageContainer>
  );
}
