// AgentActivityIndicator — Thinking Orb + label for work in progress.
//
// Honesty rule: the backend answers over plain REST and reports no
// intermediate progress, so callers pass `state="working"` (the default) for
// the whole request. When genuine progress events exist, map them onto the
// orb's other states here — never simulate them on a timer.
//
// The orb is mounted only while the parent renders this component, so it
// stops (and the library cleans up its canvas) the moment the request ends.

import { useEffect, useState } from "react";
import { ThinkingOrb, type OrbState } from "thinking-orbs";

interface Props {
  /** Accessible and visible description of what is happening. */
  label: string;
  state?: OrbState;
  /** inline: 20px orb beside text. panel: 32px orb with a secondary line. */
  variant?: "inline" | "panel";
  /** Background the orb sits on. The app has no dark content theme, so the
   *  orb is pinned rather than following the OS colour scheme. */
  surface?: "light" | "dark";
  /** Show seconds elapsed since mount (measured in the browser). */
  showElapsed?: boolean;
  detail?: string;
}

function useElapsedSeconds(enabled: boolean) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    const started = Date.now();
    const id = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(id);
  }, [enabled]);
  return seconds;
}

export function AgentActivityIndicator({
  label,
  state = "working",
  variant = "inline",
  surface = "light",
  showElapsed = false,
  detail,
}: Props) {
  const seconds = useElapsedSeconds(showElapsed);
  const orbTheme = surface === "light" ? "light" : "dark";

  if (variant === "panel") {
    return (
      <div role="status" className="flex items-center gap-3">
        <ThinkingOrb state={state} size={32} theme={orbTheme} aria-label={label} className="shrink-0" />
        <div className="min-w-0" aria-hidden>
          <div className="text-sm font-medium text-ink">{label}</div>
          {(detail || showElapsed) && (
            <div className="text-xs text-ink-muted tabular-nums">
              {detail}
              {detail && showElapsed && " · "}
              {showElapsed && `${seconds}s`}
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <span role="status" className="inline-flex items-center gap-2">
      <ThinkingOrb state={state} size={20} theme={orbTheme} aria-label={label} className="shrink-0" />
      <span className="text-xs text-ink-muted tabular-nums" aria-hidden>
        {label}
        {showElapsed && ` · ${seconds}s`}
      </span>
    </span>
  );
}
