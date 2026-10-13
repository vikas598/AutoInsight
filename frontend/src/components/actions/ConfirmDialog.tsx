// ConfirmDialog — modal confirmation using the native <dialog> element
// (focus trapping, Escape to cancel and inert background come built in).

import { useEffect, useRef, type ReactNode } from "react";
import { Button } from "../ui/Button";

interface Props {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  /** Extra acknowledgement required before Confirm is enabled. */
  acknowledge?: { label: string; checked: boolean; onChange: (v: boolean) => void };
}

export function ConfirmDialog({ open, title, children, confirmLabel, onConfirm, onCancel, acknowledge }: Props) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      onCancel={(e) => { e.preventDefault(); onCancel(); }}
      aria-labelledby="confirm-title"
      className="w-[min(92vw,30rem)] rounded-card border border-line bg-surface p-0 text-ink shadow-overlay backdrop:bg-navy-950/50"
    >
      <div className="px-5 pb-4 pt-5">
        <h2 id="confirm-title" className="text-base font-semibold text-ink">{title}</h2>
        <div className="mt-2 space-y-2 text-sm text-ink-secondary">{children}</div>
        {acknowledge && (
          <label className="mt-4 flex items-start gap-2 text-sm text-ink">
            <input
              type="checkbox"
              checked={acknowledge.checked}
              onChange={(e) => acknowledge.onChange(e.target.checked)}
              className="focus-ring mt-0.5 h-4 w-4 rounded border-line-strong accent-[rgb(var(--color-primary))]"
            />
            <span>{acknowledge.label}</span>
          </label>
        )}
      </div>
      <div className="flex justify-end gap-2 border-t border-line bg-surface-sunken/60 px-5 py-3">
        <Button onClick={onCancel} autoFocus>Cancel</Button>
        <Button variant="primary" onClick={onConfirm} disabled={acknowledge ? !acknowledge.checked : false}>
          {confirmLabel}
        </Button>
      </div>
    </dialog>
  );
}
