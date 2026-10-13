// App — wires routing, the shell and the pages together.

import { useCallback } from "react";
import { AppShell } from "./components/layout/AppShell";
import { useAnalystSession } from "./hooks/useAnalystSession";
import { useHashRoute } from "./hooks/useHashRoute";
import { useOverview } from "./hooks/useOverview";
import { getNavItem, type RouteId } from "./navigation";
import { AnalystActions, AnalystPage } from "./pages/AnalystPage";
import { OverviewPage } from "./pages/OverviewPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";

// What each unbuilt destination will provide. Shown on its placeholder page.
const PLACEHOLDER_SUMMARIES: Record<Exclude<RouteId, "analyst" | "overview">, string> = {
  insights:
    "A home for sales forecasts, customer segmentation and anomaly detection. These analyses already run from the AI Analyst; ask it to forecast sales or find anomalies.",
  actions:
    "Review data changes awaiting approval and browse the audit trail of every write the system has made.",
  data:
    "Browse the connected database's tables, columns and relationships, and view system configuration.",
};

export default function App() {
  const [route, navigate] = useHashRoute();
  const analyst = useAnalystSession();
  // Loads on first visit to Overview, then keeps its data across navigation
  const overview = useOverview(route === "overview");

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
