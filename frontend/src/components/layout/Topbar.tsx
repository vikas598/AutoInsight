// Topbar — page title, description and page-specific actions.

import type { ReactNode } from "react";
import { Menu } from "lucide-react";

interface Props {
  title: string;
  description: string;
  actions?: ReactNode;
  onOpenNav: () => void;
}

export function Topbar({ title, description, actions, onOpenNav }: Props) {
  return (
    <header className="flex h-topbar shrink-0 items-center gap-3 border-b border-line bg-surface px-4 sm:px-6">
      <button
        type="button"
        onClick={onOpenNav}
        aria-label="Open navigation"
        className="focus-ring -ml-1 rounded-control p-2 text-ink-secondary hover:bg-surface-sunken lg:hidden"
      >
        <Menu className="h-5 w-5" aria-hidden />
      </button>

      <div className="min-w-0 flex-1">
        <h1 className="truncate text-base font-semibold tracking-tight text-ink">{title}</h1>
        <p className="hidden truncate text-xs text-ink-muted sm:block">{description}</p>
      </div>

      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}
