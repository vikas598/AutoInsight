// Suggested questions for the AI Analyst. Each maps to a capability the
// backend actually implements (SQL read, forecast, clustering, anomalies).

import {
  BarChart3,
  Filter,
  LineChart,
  ScanSearch,
  TrendingUp,
  Users,
  type LucideIcon,
} from "lucide-react";

export interface SuggestedPrompt {
  category: string;
  question: string;
  icon: LucideIcon;
}

/**
 * Period covered by the dealership records (database/generate_seed_data.py
 * generates Jan 2022 – Dec 2024). Prompts name explicit years so they don't
 * silently assume current-period data exists.
 */
export const DATA_COVERAGE = "January 2022 – December 2024";

export const SUGGESTED_PROMPTS: readonly SuggestedPrompt[] = [
  { category: "Sales",        icon: BarChart3,  question: "Which vehicle models sold the most in 2024?" },
  { category: "Trends",       icon: LineChart,  question: "Show me the monthly sales trend." },
  { category: "Forecast",     icon: TrendingUp, question: "Forecast sales for the next 3 months." },
  { category: "Segmentation", icon: Users,      question: "Segment customers by spending behavior." },
  { category: "Anomalies",    icon: ScanSearch, question: "Find unusual sales transactions." },
  { category: "Leads",        icon: Filter,     question: "Analyze lead conversion by source." },
];
