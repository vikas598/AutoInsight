// ChatInput — the analyst composer: auto-growing multiline input, send
// button and suggestion chips. The draft text is owned by the session hook so
// it can be restored if a request fails.

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { ArrowUp } from "lucide-react";
import { SUGGESTED_PROMPTS } from "../analystPrompts";

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSend: (text: string) => void;
  /** A request is in flight: typing is allowed, sending is not. */
  busy: boolean;
  /** A proposed change awaits a decision: input is disabled entirely. */
  awaitingApproval: boolean;
  showSuggestions: boolean;
}

const MAX_HEIGHT_PX = 160;

/** The full placeholder wraps (and clips) in a one-line input on phones. */
function usePlaceholder() {
  const query = "(min-width: 640px)";
  const [wide, setWide] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = () => setWide(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return wide ? "Ask a question about your dealership data…" : "Ask about your dealership…";
}

export function ChatInput({ value, onChange, onSend, busy, awaitingApproval, showSuggestions }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const placeholder = usePlaceholder();
  const canSend = !busy && !awaitingApproval && value.trim().length > 0;

  // Grow with content up to MAX_HEIGHT_PX, then scroll inside. Re-measured
  // when the width changes, since wrapping depends on it.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const fit = () => {
      el.style.height = "";
      if (el.value) el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`;
    };
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [value]);

  // Return focus to the input once a request or approval finishes (not on
  // first mount, which would pop the keyboard on phones)
  const locked = busy || awaitingApproval;
  const wasLocked = useRef(locked);
  useEffect(() => {
    if (wasLocked.current && !locked) ref.current?.focus({ preventScroll: true });
    wasLocked.current = locked;
  }, [locked]);

  const submit = () => {
    if (canSend) onSend(value);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  const hint = awaitingApproval
    ? "Approve or reject the proposed change above to continue."
    : busy
      ? "Waiting for the current answer…"
      : null;

  return (
    <div className="shrink-0 border-t border-line bg-surface/95 px-4 pb-4 pt-3 backdrop-blur sm:px-6">
      <div className="mx-auto max-w-3xl">
        {showSuggestions && !awaitingApproval && (
          <div className="scrollbar-none -mx-1 mb-2.5 flex gap-1.5 overflow-x-auto px-1 py-0.5" aria-label="Suggested questions" role="group">
            {SUGGESTED_PROMPTS.map(({ question }) => (
              <button
                key={question}
                type="button"
                onClick={() => onSend(question)}
                disabled={busy}
                className="focus-ring shrink-0 whitespace-nowrap rounded-full border border-line bg-surface px-3 py-1 text-xs text-ink-secondary transition-colors hover:border-line-strong hover:bg-surface-sunken hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
              >
                {question}
              </button>
            ))}
          </div>
        )}

        <form
          onSubmit={(e) => { e.preventDefault(); submit(); }}
          className={`flex items-end gap-2 rounded-card border bg-surface p-2 shadow-card transition-colors focus-within:border-primary focus-within:ring-2 focus-within:ring-focus/30 ${
            awaitingApproval ? "border-line bg-surface-sunken" : "border-line-strong"
          }`}
        >
          <label htmlFor="analyst-input" className="sr-only">Ask a question about your dealership data</label>
          <textarea
            id="analyst-input"
            ref={ref}
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={onKeyDown}
            disabled={awaitingApproval}
            placeholder={placeholder}
            aria-describedby="analyst-input-hint"
            className="max-h-40 min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-[15px] leading-6 text-ink placeholder:text-ink-muted focus:outline-none disabled:cursor-not-allowed"
          />
          <button
            type="submit"
            disabled={!canSend}
            aria-label={busy ? "Sending is unavailable while an answer is in progress" : "Send question"}
            className="focus-ring flex h-10 w-10 shrink-0 items-center justify-center rounded-control bg-primary text-white transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-line-strong disabled:text-white"
          >
            <ArrowUp className="h-[18px] w-[18px]" aria-hidden />
          </button>
        </form>

        <div id="analyst-input-hint" className="mt-1.5 flex items-center justify-between gap-3 px-1 text-2xs text-ink-muted">
          <span aria-live="polite">{hint}</span>
          <span className="hidden shrink-0 sm:inline">
            <kbd className="font-sans font-medium text-ink-secondary">Enter</kbd> to send ·{" "}
            <kbd className="font-sans font-medium text-ink-secondary">Shift + Enter</kbd> for a new line
          </span>
        </div>
      </div>
    </div>
  );
}
