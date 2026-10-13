// useAnalystSession — conversation, approval and report state for the AI
// Analyst. Lives above the page so the conversation survives navigation.
//
// Single sources of truth:
//   * `messages`          — every turn, including approval proposals
//   * `inFlight`          — the one request currently awaiting the server
//   * `pendingApprovalId` — which proposal message is awaiting a decision;
//                           its assessment lives on that message, not copied

import { useCallback, useRef, useState } from "react";
import { api, ApiError, errorMessage } from "../api";
import type { AssistantMessage, Decision, Message } from "../types";

type InFlight = null | { kind: "chat" } | { kind: "decision"; decision: Decision };

export type ExportState =
  | { status: "idle" }
  | { status: "building" }
  | { status: "done"; filename: string; url: string; sizeKb: number }
  | { status: "error"; message: string };

const newId = () => crypto.randomUUID();

export function useAnalystSession() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inFlight, setInFlight] = useState<InFlight>(null);
  const [pendingApprovalId, setPendingApprovalId] = useState<string | null>(null);
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [exportState, setExportState] = useState<ExportState>({ status: "idle" });

  // Bumped on "new conversation" so a late response can't land in the new one
  const epoch = useRef(0);

  const pendingApproval = pendingApprovalId
    ? (messages.find((m) => m.id === pendingApprovalId) as AssistantMessage | undefined) ?? null
    : null;

  const busy = inFlight !== null;
  const inputLocked = busy || pendingApproval !== null;

  const send = useCallback(async (raw: string) => {
    const text = raw.trim();
    if (!text || inFlight || pendingApprovalId) return;

    const run = epoch.current;
    const userMsgId = newId();
    setMessages((m) => [...m, { id: userMsgId, role: "user", text }]);
    setDraft("");
    setInFlight({ kind: "chat" });

    try {
      const res = await api.chat(sessionId, text);
      if (run !== epoch.current) return;
      setSessionId(res.session_id);

      const assistantId = newId();
      setMessages((m) => [...m, { id: assistantId, role: "assistant", response: res }]);
      if (res.status === "needs_approval" && res.assessment) {
        setApprovalError(null);
        setPendingApprovalId(assistantId);
      }
    } catch (e) {
      if (run !== epoch.current) return;
      // The request never produced a response: flag the message and give the
      // text back so the user can resend without retyping.
      setMessages((m) => m.map((msg) =>
        msg.id === userMsgId ? { ...msg, deliveryError: errorMessage(e) } : msg));
      setDraft((current) => current || text);
    } finally {
      if (run === epoch.current) setInFlight(null);
    }
  }, [inFlight, pendingApprovalId, sessionId]);

  const decide = useCallback(async (decision: Decision) => {
    if (!pendingApprovalId || !sessionId || inFlight) return;

    const run = epoch.current;
    const proposalId = pendingApprovalId;
    setApprovalError(null);
    setInFlight({ kind: "decision", decision });

    try {
      const res = await api.approve(sessionId, decision);
      if (run !== epoch.current) return;
      // Only now — with the server's answer in hand — is the proposal resolved
      setMessages((m) => [
        ...m.map((msg) => (msg.id === proposalId ? { ...msg, decision } : msg)),
        { id: newId(), role: "assistant", response: res, answersDecision: decision },
      ]);
      setPendingApprovalId(null);
    } catch (e) {
      if (run !== epoch.current) return;
      setApprovalError(
        `${errorMessage(e)} Your decision was not confirmed by the server. ` +
        "If you try again, first check that the change has not already been applied.",
      );
    } finally {
      if (run === epoch.current) setInFlight(null);
    }
  }, [inFlight, pendingApprovalId, sessionId]);

  const exportReport = useCallback(async () => {
    if (!sessionId || exportState.status === "building") return;
    setExportState({ status: "building" });
    try {
      const info = await api.buildReport(sessionId);
      // Same-origin download link: unlike window.open after an await, this
      // isn't blocked as a popup.
      const a = document.createElement("a");
      a.href = info.url;
      a.download = info.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setExportState({ status: "done", filename: info.filename, url: info.url, sizeKb: info.size_kb });
    } catch (e) {
      const message = e instanceof ApiError && e.status === 404
        ? "The server has no history for this conversation, so there is nothing to export. This happens if the backend restarted since the conversation began."
        : `The report could not be generated. ${errorMessage(e)}`;
      setExportState({ status: "error", message });
    }
  }, [exportState.status, sessionId]);

  const dismissExport = useCallback(() => setExportState({ status: "idle" }), []);

  const reset = useCallback(() => {
    if (inFlight || pendingApprovalId) return;
    epoch.current += 1;
    setSessionId(null);
    setMessages([]);
    setApprovalError(null);
    setDraft("");
    setExportState({ status: "idle" });
  }, [inFlight, pendingApprovalId]);

  const questionCount = messages.filter((m) => m.role === "user" && !m.deliveryError).length;

  return {
    sessionId,
    messages,
    inFlight,
    busy,
    inputLocked,
    pendingApproval,
    approvalError,
    draft,
    setDraft,
    exportState,
    questionCount,
    canExport: !!sessionId && messages.some((m) => m.role === "assistant"),
    canReset: messages.length > 0 && !busy && !pendingApproval,
    send,
    decide,
    exportReport,
    dismissExport,
    reset,
  };
}

export type AnalystSession = ReturnType<typeof useAnalystSession>;
