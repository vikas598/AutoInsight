// Navigation — the five top-level destinations, in sidebar order.

import {
  Bot,
  Database,
  LayoutDashboard,
  ShieldCheck,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

export type RouteId = "overview" | "analyst" | "insights" | "actions" | "data";

export interface NavItem {
  id: RouteId;
  label: string;
  icon: LucideIcon;
  /** One line shown under the page title in the topbar. */
  description: string;
}

export const NAV_ITEMS: readonly NavItem[] = [
  {
    id: "overview",
    label: "Overview",
    icon: LayoutDashboard,
    description: "A clear view of your dealership’s performance",
  },
  {
    id: "analyst",
    label: "AI Analyst",
    icon: Bot,
    description: "Ask about sales, inventory, customers, leads and service",
  },
  {
    id: "insights",
    label: "Insights & Forecasts",
    icon: TrendingUp,
    description: "Forecasts, customer segments and anomalies",
  },
  {
    id: "actions",
    label: "Action Center",
    icon: ShieldCheck,
    description: "Approvals and the audit trail of data changes",
  },
  {
    id: "data",
    label: "Data & Settings",
    icon: Database,
    description: "Connected database, schema and configuration",
  },
];

export const DEFAULT_ROUTE: RouteId = "analyst";

export function isRouteId(value: string): value is RouteId {
  return NAV_ITEMS.some((item) => item.id === value);
}

export function getNavItem(id: RouteId): NavItem {
  return NAV_ITEMS.find((item) => item.id === id)!;
}
