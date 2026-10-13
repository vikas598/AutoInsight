// Shared types mirroring the FastAPI response shapes (backend/app/api/main.py).

export type ChatStatus = "complete" | "needs_approval" | "error";

export type Intent =
  | "sql_read" | "sql_write"
  | "ml_forecast" | "ml_cluster" | "ml_anomaly"
  | "clarification" | "unsupported";

export interface QueryResult {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  truncated: boolean;
  executed_sql: string;
}

export interface ChartConfig {
  chart_type: "line" | "bar" | "grouped_bar" | "pie" | "scatter"
            | "area" | "table" | "kpi" | "forecast_line" | "empty";
  data: Record<string, any>[];
  x_key: string;
  y_keys: string[];
  title: string;
}

export interface Assessment {
  sql: string;
  operation: string;              // INSERT | UPDATE | DELETE
  target_table: string;
  risk_score: number;
  risk_factors: Record<string, number>;
  requires_approval: boolean;
  preview_columns: string[];
  preview_rows: unknown[][];
  affected_rows: number;
  decision?: string;
  error?: string | null;
}

export interface ChatResponse {
  session_id: string;
  status: ChatStatus;
  intent: Intent | string | null;
  response: string | null;
  sql_query: string | null;
  query_result: QueryResult | null;
  chart_config: ChartConfig | null;
  assessment: Assessment | null;
  error: string | null;
}

export interface ReportInfo {
  filename: string;
  url: string;
  size_kb: number;
  entries: number;
}

export type Decision = "approved" | "rejected";

export interface UserMessage {
  id: string;
  role: "user";
  text: string;
  /** Set when the request never got a response (network / HTTP failure). */
  deliveryError?: string;
}

export interface AssistantMessage {
  id: string;
  role: "assistant";
  response: ChatResponse;
  /** For approval proposals: the decision the server confirmed receiving. */
  decision?: Decision;
  /** For the server's reply to a decision: which decision it answers. */
  answersDecision?: Decision;
}

export type Message = UserMessage | AssistantMessage;

// ---------------------------------------------------------------------------
// Overview dashboard — GET /api/dashboard/overview
// (backend/app/services/dashboard_service.py documents every definition)
// ---------------------------------------------------------------------------

export interface ReportingPeriod {
  id: string;                 // "2024" | "all"
  label: string;
  start: string;              // ISO date, inclusive
  end_exclusive: string;      // ISO date, exclusive
  complete?: boolean;         // dataset's sale dates span the whole period
}

export interface MetricValue {
  value: number | null;
  previous: number | null;
}

export interface OverviewResponse {
  generated_at: string;
  data_extent: { first_sale_date: string; last_sale_date: string; total_sales: number } | null;
  periods: ReportingPeriod[];
  period: ReportingPeriod | null;
  comparison: ReportingPeriod | null;
  comparison_unavailable_reason: string | null;
  kpis: {
    total_revenue: MetricValue;
    units_sold: MetricValue;
    average_sale_value: MetricValue;
    total_discount: MetricValue;
    available_inventory: MetricValue;
  };
  monthly: { month: string; units: number; revenue: number }[];
  top_models: { make: string; model: string; units: number; revenue: number }[];
  inventory: {
    total: number;
    available: number;
    allowed_statuses: string[];
    by_status: { status: string; count: number }[];
  };
}

// ---------------------------------------------------------------------------
// Audit log — GET /api/audit (backend/app/services/audit_log.py)
// ---------------------------------------------------------------------------

export type AuditDecision = "auto_approved" | "approved" | "rejected" | "blocked" | "error";

export interface AuditEntry {
  timestamp: string;
  session_id: string;
  user_query: string;
  sql: string;
  operation: string;
  target_table: string;
  risk_score: number;
  affected_rows: number;
  decision: AuditDecision | string;
  executed: boolean;
  approved_by: string | null;
  error: string | null;
}
