// RichText — renders the narrative text returned by the backend. Handles the
// little structure LLM narration uses (paragraphs, bullet/numbered lists,
// **bold**) as React elements; never injects HTML.

import type { ReactNode } from "react";

function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={i} className="font-semibold text-ink">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return <code key={i} className="rounded bg-surface-sunken px-1 py-px font-mono text-[0.88em]">{part.slice(1, -1)}</code>;
    }
    return part;
  });
}

const BULLET = /^\s*[-*•]\s+/;
const NUMBERED = /^\s*\d+[.)]\s+/;

type Run = { kind: "p" | "ul" | "ol"; lines: string[] };

/** Group lines into paragraphs and lists; a blank line ends a paragraph. */
function toRuns(text: string): Run[] {
  const runs: Run[] = [];
  for (const raw of text.trim().split("\n")) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      runs.push({ kind: "p", lines: [] });
      continue;
    }
    const kind: Run["kind"] = BULLET.test(line) ? "ul" : NUMBERED.test(line) ? "ol" : "p";
    const content = kind === "ul" ? line.replace(BULLET, "") : kind === "ol" ? line.replace(NUMBERED, "") : line;
    const last = runs[runs.length - 1];
    if (last && last.kind === kind && (kind !== "p" || last.lines.length)) last.lines.push(content);
    else runs.push({ kind, lines: [content] });
  }
  return runs.filter((r) => r.lines.length);
}

export function RichText({ text, className = "" }: { text: string; className?: string }) {
  return (
    <div className={`space-y-3 text-[15px] leading-relaxed text-ink ${className}`}>
      {toRuns(text).map((run, i) => {
        if (run.kind === "p") {
          return <p key={i}>{run.lines.map((l, j) => <span key={j}>{j > 0 && <br />}{inline(l)}</span>)}</p>;
        }
        const List = run.kind;
        return (
          <List key={i} className={`${run.kind === "ul" ? "list-disc" : "list-decimal"} space-y-1 pl-5 marker:text-ink-muted`}>
            {run.lines.map((l, j) => <li key={j}>{inline(l)}</li>)}
          </List>
        );
      })}
    </div>
  );
}
