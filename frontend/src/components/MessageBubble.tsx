// MessageBubble — one conversation turn.
//   user:      compact right-aligned bubble (+ delivery failure note)
//   assistant: summary → outcome / result → technical details, laid out on
//              the canvas rather than inside one oversized card

import type { ReactNode } from "react";
import { CircleAlert, CircleCheck, CircleX, Gauge, ShieldCheck } from "lucide-react";
import { ResultCard } from "./ResultCard";
import { RichText } from "./RichText";
import { TechnicalDetails } from "./TechnicalDetails";
import { plural } from "../lib/format";
import type { AssistantMessage, Message } from "../types";

/** Business-language name for each kind of analysis (no agent names). */
const ANALYSIS_LABEL: Record<string, string> = {
  sql_read: "Data query",
  sql_write: "Data change",
  ml_forecast: "Forecast",
  ml_cluster: "Customer segmentation",
  ml_anomaly: "Anomaly detection",
  clarification: "Clarification",
  unsupported: "Outside scope",
};

interface Props {
  message: Message;
  /** Approval controls, passed only for the proposal awaiting a decision. */
  approval?: ReactNode;
}

export function MessageBubble({ message, approval }: Props) {
  if (message.role === "user") {
    return (
      <div className="flex flex-col items-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-navy-800 px-4 py-2.5 text-[15px] leading-relaxed text-white sm:max-w-[75%]">
          <p className="whitespace-pre-wrap break-words">{message.text}</p>
        </div>
        {message.deliveryError && (
          <p role="alert" className="mt-1.5 inline-flex max-w-[85%] items-start gap-1.5 text-right text-xs text-danger">
            <CircleAlert className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
            <span>Not sent — {message.deliveryError} Your question is back in the input box.</span>
          </p>
        )}
      </div>
    );
  }
  return <AssistantTurn message={message} approval={approval} />;
}

function AssistantTurn({ message, approval }: { message: AssistantMessage; approval?: ReactNode }) {
  const res = message.response;
  const isError = res.status === "error";
  const isProposal = res.status === "needs_approval" && !!res.assessment;
  const label = res.intent ? ANALYSIS_LABEL[res.intent] : null;
  const text = res.response?.trim();

  return (
    <article className="flex gap-3">
      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-control bg-navy-950" aria-hidden>
        <Gauge className="h-4 w-4 text-white" />
      </div>

      <div className="min-w-0 flex-1 space-y-3">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="font-semibold text-ink">AutoInsight</span>
          {label && (
            <span className="rounded-full border border-line bg-surface px-2 py-0.5 font-medium text-ink-muted">
              {label}
            </span>
          )}
        </div>

        {isError ? (
          <div role="alert" className="rounded-card border border-danger/25 bg-danger-soft px-4 py-3">
            <p className="flex items-center gap-1.5 text-sm font-semibold text-danger">
              <CircleAlert className="h-4 w-4" aria-hidden />
              This request couldn't be completed
            </p>
            {text && <RichText text={text} className="mt-1.5 !text-sm text-ink-secondary" />}
            <p className="mt-2 text-xs text-ink-secondary">Try rephrasing the question or making it more specific.</p>
          </div>
        ) : text ? (
          <RichText text={text} />
        ) : (
          <p className="text-sm italic text-ink-muted">No summary was returned for this request.</p>
        )}

        <WriteOutcome message={message} />

        {isProposal && (approval ?? <ResolvedProposal message={message} />)}

        {!isError && !isProposal && <ResultCard response={res} />}

        <TechnicalDetails response={res} isProposal={isProposal} answersDecision={message.answersDecision} />
      </div>
    </article>
  );
}

/** Outcome of a data change, derived from the server's response status. */
function WriteOutcome({ message }: { message: AssistantMessage }) {
  const res = message.response;
  if (res.intent !== "sql_write" || res.status !== "complete") return null;

  if (message.answersDecision === "rejected") {
    return (
      <Outcome tone="neutral" icon={CircleX}>Change rejected — the database was not modified.</Outcome>
    );
  }
  const affected = res.query_result?.row_count;
  const rows = typeof affected === "number" ? ` · ${plural(affected, "row")} affected` : "";
  return message.answersDecision === "approved" ? (
    <Outcome tone="success" icon={CircleCheck}>Change applied after your approval{rows}</Outcome>
  ) : (
    <Outcome tone="success" icon={ShieldCheck}>Change applied automatically (assessed as low risk){rows}</Outcome>
  );
}

function Outcome({ tone, icon: Icon, children }: { tone: "success" | "neutral"; icon: typeof CircleCheck; children: ReactNode }) {
  const style = tone === "success"
    ? "border-success/25 bg-success-soft text-success"
    : "border-line bg-surface-sunken text-ink-secondary";
  return (
    <p className={`inline-flex items-center gap-1.5 rounded-control border px-3 py-1.5 text-sm font-medium ${style}`}>
      <Icon className="h-4 w-4 shrink-0" aria-hidden />
      {children}
    </p>
  );
}

/** A proposal that has been decided — compact record in place of the card. */
function ResolvedProposal({ message }: { message: AssistantMessage }) {
  const a = message.response.assessment!;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-card border border-line bg-surface px-4 py-2.5 text-sm">
      <span className="font-mono text-xs font-semibold text-ink-secondary">{a.operation}</span>
      <span className="text-ink">on <code className="font-mono">{a.target_table}</code></span>
      <span className="text-ink-muted">Risk {a.risk_score}/100</span>
      <span className="ml-auto text-xs font-medium text-ink-secondary">
        {message.decision === "approved" ? "You approved this change"
          : message.decision === "rejected" ? "You rejected this change"
          : message.decision === "elsewhere" ? "Decided outside this conversation — see the Action Center audit log"
          : "Awaiting decision"}
      </span>
    </div>
  );
}
