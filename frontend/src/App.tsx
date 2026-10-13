// App — wires routing, the shell and the pages together.

import { useCallback } from "react";
import { AppShell } from "./components/layout/AppShell";
import { useActionCenter } from "./hooks/useActionCenter";
import { useAnalystSession } from "./hooks/useAnalystSession";
import { useHashRoute } from "./hooks/useHashRoute";
import { useInsights } from "./hooks/useInsights";
import { useOverview } from "./hooks/useOverview";
import { getNavItem, type RouteId } from "./navigation";
import type { Decision } from "./types";
import { ActionCenterPage } from "./pages/ActionCenterPage";
import { AnalystActions, AnalystPage } from "./pages/AnalystPage";
import { InsightsPage } from "./pages/InsightsPage";
import { OverviewPage } from "./pages/OverviewPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";

// What each unbuilt destination will provide. Shown on its placeholder page.
const PLACEHOLDER_SUMMARIES: Record<Exclude<RouteId, "analyst" | "overview" | "insights" | "actions">, string> = {
  data:
    "Browse the connected database's tables, columns and relationships, and view system configuration.",
};

export default function App() {
  const [route, navigate] = useHashRoute();
  const analyst = useAnalystSession();
  // Loads on first visit to Overview or Insights (which shows the dataset's
  // date range), then keeps its data across navigation
  const overview = useOverview(route === "overview" || route === "insights");
  const insights = useInsights();

  // A proposal from this tab's AI Analyst conversation is decided through the
  // Analyst session, so the conversation and the Action Center stay in step.
  const { pendingApproval, sessionId: analystSessionId, decide: analystDecideFn } = analyst;
  const analystDecide = useCallback(
    (sessionId: string, decision: Decision) =>
      pendingApproval && analystSessionId === sessionId ? analystDecideFn(decision) : null,
    [pendingApproval, analystSessionId, analystDecideFn],
  );
  const actions = useActionCenter({ enabled: route === "actions", analystDecide });

  /** Open the AI Analyst with a question: run it now, or — if the analyst
   *  is busy or awaiting an approval — leave it in the input box. */
  const askAnalyst = useCallback((question: string) => {
    navigate("analyst");
    if (analyst.inputLocked) analyst.setDraft(question);
    else void analyst.send(question);
  }, [analyst, navigate]);

  return (
    <AppShell
      route={route}
      onNavigate={navigate}
      actions={route === "analyst" ? <AnalystActions session={analyst} /> : undefined}
    >
      {route === "analyst" ? (
        <AnalystPage session={analyst} />
      ) : route === "overview" ? (
        <OverviewPage state={overview} onAsk={askAnalyst} />
      ) : route === "insights" ? (
        <InsightsPage state={insights} dataset={overview} onAsk={askAnalyst} />
      ) : route === "actions" ? (
        <ActionCenterPage state={actions} analystSessionId={analyst.sessionId} />
      ) : (
        <PlaceholderPage
          item={getNavItem(route)}
          summary={PLACEHOLDER_SUMMARIES[route]}
          onNavigate={navigate}
        />
      )}
    </AppShell>
  );
}
