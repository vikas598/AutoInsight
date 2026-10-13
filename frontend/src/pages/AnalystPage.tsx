// AnalystPage — the AI Analyst workspace: conversation + composer, with the
// export / new-conversation controls rendered in the topbar.

import { useEffect, useLayoutEffect, useRef } from "react";
import { CircleAlert, CircleCheck, FileDown, MessageSquarePlus, X } from "lucide-react";
import { AgentActivityIndicator } from "../components/AgentActivityIndicator";
import { ApprovalCard } from "../components/ApprovalCard";
import { ChatInput } from "../components/ChatInput";
import { MessageBubble } from "../components/MessageBubble";
import { WelcomeState } from "../components/WelcomeState";
import { Button } from "../components/ui/Button";
import type { AnalystSession } from "../hooks/useAnalystSession";
import { plural } from "../lib/format";

const NEAR_BOTTOM_PX = 160;

const scrollBehavior = (): ScrollBehavior =>
  window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";

export function AnalystPage({ session }: { session: AnalystSession }) {
  const {
    messages, inFlight, busy, pendingApproval, approvalError,
    draft, setDraft, send, decide,
  } = session;

  const scrollRef = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);

  const onScroll = () => {
    const el = scrollRef.current;
    if (el) nearBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
  };

  // Scrolling rules: the user's own question and the pending indicator pull
  // the view to the bottom; a new answer is brought into view from its top
  // (so long charts aren't skipped past) — and only if the reader hasn't
  // scrolled up to look at something else.
  const lastId = messages[messages.length - 1]?.id;
  useLayoutEffect(() => {
    const el = scrollRef.current;
    const last = messages[messages.length - 1];
    if (!el || !last) return;
    if (last.role === "user") {
      el.scrollTo({ top: el.scrollHeight, behavior: scrollBehavior() });
    } else if (nearBottom.current) {
      el.querySelector<HTMLElement>(`[data-message-id="${last.id}"]`)
        ?.scrollIntoView({ block: "start", behavior: scrollBehavior() });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastId]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && inFlight?.kind === "chat") el.scrollTo({ top: el.scrollHeight, behavior: scrollBehavior() });
  }, [inFlight]);

  const empty = messages.length === 0;

  return (
    <div className="flex h-full flex-col">
      <ExportNotice session={session} />

      <div ref={scrollRef} onScroll={onScroll} className="chat-scroll min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl px-4 pb-8 pt-6 sm:px-6">
          {empty && !busy ? (
            <WelcomeState onAsk={send} disabled={busy} />
          ) : (
            <ol className="space-y-8" aria-label="Conversation">
              {messages.map((m) => (
                <li key={m.id} data-message-id={m.id} className="scroll-mt-4">
                  <MessageBubble
                    message={m}
                    approval={pendingApproval?.id === m.id && pendingApproval.response.assessment ? (
                      <ApprovalCard
                        assessment={pendingApproval.response.assessment}
                        onDecide={decide}
                        submitting={inFlight?.kind === "decision" ? inFlight.decision : null}
                        disabled={busy}
                        error={approvalError}
                      />
                    ) : undefined}
                  />
                </li>
              ))}

              {inFlight?.kind === "chat" && (
                <li className="flex gap-3 pl-10">
                  <AgentActivityIndicator label="Analyzing your request" showElapsed />
                </li>
              )}
            </ol>
          )}
        </div>
      </div>

      <ChatInput
        value={draft}
        onChange={setDraft}
        onSend={send}
        busy={busy}
        awaitingApproval={pendingApproval !== null}
        showSuggestions={!empty}
      />
    </div>
  );
}

/** Result of the last report export — success only once the download began. */
function ExportNotice({ session }: { session: AnalystSession }) {
  const { exportState, dismissExport } = session;
  if (exportState.status !== "done" && exportState.status !== "error") return null;

  const ok = exportState.status === "done";
  return (
    <div
      role={ok ? "status" : "alert"}
      className={`flex shrink-0 items-start gap-2 border-b px-4 py-2.5 text-sm sm:px-6 ${
        ok ? "border-success/20 bg-success-soft text-success" : "border-danger/20 bg-danger-soft text-danger"
      }`}
    >
      {ok ? <CircleCheck className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> : <CircleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />}
      <p className="min-w-0 flex-1">
        {ok ? (
          <>
            Report downloaded — {exportState.filename} ({exportState.sizeKb} KB).{" "}
            <a href={exportState.url} download={exportState.filename} className="focus-ring rounded font-medium underline underline-offset-2">
              Download again
            </a>
          </>
        ) : exportState.message}
      </p>
      <button
        type="button"
        onClick={dismissExport}
        aria-label="Dismiss"
        className="focus-ring -m-1 rounded p-1 opacity-70 hover:opacity-100"
      >
        <X className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );
}

/** Topbar controls: conversation indicator, new conversation, PDF export. */
export function AnalystActions({ session }: { session: AnalystSession }) {
  const { sessionId, questionCount, canExport, canReset, exportState, exportReport, reset } = session;
  const building = exportState.status === "building";

  return (
    <>
      {questionCount > 0 && (
        <span
          className="hidden whitespace-nowrap text-xs text-ink-muted md:inline"
          title={sessionId ? `Session ${sessionId}` : undefined}
        >
          {plural(questionCount, "question")} in this conversation
        </span>
      )}
      <Button
        size="sm"
        variant="ghost"
        icon={MessageSquarePlus}
        onClick={reset}
        disabled={!canReset}
        aria-label="New conversation"
        title={canReset ? "Start a new conversation" : "Available when no request or approval is pending"}
      >
        <span className="hidden sm:inline">New conversation</span>
      </Button>
      <Button
        size="sm"
        icon={FileDown}
        onClick={exportReport}
        disabled={!canExport || building}
        aria-busy={building}
        aria-label={building ? "Preparing report" : "Export PDF report"}
        title={canExport ? "Download a PDF report of this conversation" : "Ask a question first"}
      >
        <span className="hidden sm:inline">{building ? "Preparing report…" : "Export report"}</span>
      </Button>
    </>
  );
}
