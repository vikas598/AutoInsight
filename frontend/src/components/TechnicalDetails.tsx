// TechnicalDetails — collapsed, secondary view of the SQL behind an answer.
// The label states exactly what happened to the statement, so a generated or
// proposed query is never presented as executed.

import { ChevronRight } from "lucide-react";
import type { ChatResponse, Decision } from "../types";

interface SqlInfo { label: string; note?: string; sql: string }

function describeSql(res: ChatResponse, isProposal: boolean, answersDecision?: Decision): SqlInfo | null {
  const executed = res.query_result?.executed_sql;
  const sql = executed || res.sql_query;
  if (!sql) return null;

  if (isProposal) {
    return { label: "Proposed change", note: "Not executed unless you approve it.", sql };
  }
  if (res.intent === "sql_read") {
    return executed
      ? { label: "Executed read-only query", note: "Includes the row limit the server applies.", sql }
      : { label: "Generated query", note: "This query did not complete.", sql };
  }
  if (res.intent === "sql_write") {
    if (res.status === "complete" && answersDecision === "rejected") {
      return { label: "Rejected change", note: "Not executed.", sql };
    }
    if (res.status === "complete") return { label: "Executed change", sql };
    return { label: "Data-change statement", note: "The request failed; see the summary above.", sql };
  }
  return { label: "Generated SQL", sql };
}

interface Props {
  response: ChatResponse;
  isProposal?: boolean;
  answersDecision?: Decision;
}

export function TechnicalDetails({ response, isProposal = false, answersDecision }: Props) {
  const sql = describeSql(response, isProposal, answersDecision);
  const errorDetail = response.status === "error" && response.error && response.error !== response.response
    ? response.error
    : null;
  if (!sql && !errorDetail) return null;

  return (
    <details className="group text-sm">
      <summary className="focus-ring inline-flex cursor-pointer list-none items-center gap-1 rounded text-xs font-medium text-ink-muted hover:text-ink [&::-webkit-details-marker]:hidden">
        <ChevronRight className="h-3.5 w-3.5 transition-transform group-open:rotate-90" aria-hidden />
        Technical details
      </summary>
      <div className="mt-2 space-y-3">
        {sql && (
          <div>
            <div className="mb-1 flex flex-wrap items-baseline gap-x-2 text-xs">
              <span className="font-semibold text-ink-secondary">{sql.label}</span>
              {sql.note && <span className="text-ink-muted">{sql.note}</span>}
            </div>
            <pre className="max-h-72 overflow-auto rounded-control bg-navy-950 px-3.5 py-3 font-mono text-[12px] leading-relaxed text-navy-100">
              <code className="whitespace-pre-wrap break-words">{sql.sql}</code>
            </pre>
          </div>
        )}
        {errorDetail && (
          <div>
            <div className="mb-1 text-xs font-semibold text-ink-secondary">Error detail</div>
            <pre className="overflow-auto rounded-control border border-line bg-surface-sunken px-3.5 py-3 font-mono text-[12px] text-ink-secondary">
              <code className="whitespace-pre-wrap break-words">{errorDetail}</code>
            </pre>
          </div>
        )}
      </div>
    </details>
  );
}
