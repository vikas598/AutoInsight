// Sidebar — navy primary navigation. Persistent on desktop (lg+); rendered
// inside a drawer by AppShell on smaller screens.

import { Gauge, X } from "lucide-react";
import type { BackendStatus } from "../../hooks/useBackendHealth";
import { NAV_ITEMS, type RouteId } from "../../navigation";

interface Props {
  active: RouteId;
  onNavigate: (route: RouteId) => void;
  backendStatus: BackendStatus;
  /** Only passed when shown as a mobile drawer. */
  onClose?: () => void;
}

const STATUS_LABEL: Record<BackendStatus, string> = {
  checking: "Checking backend…",
  online:   "Backend connected",
  offline:  "Backend unreachable",
};

const STATUS_DOT: Record<BackendStatus, string> = {
  checking: "bg-navy-300",
  online:   "bg-success",
  offline:  "bg-danger",
};

export function Sidebar({ active, onNavigate, backendStatus, onClose }: Props) {
  return (
    <div className="flex h-full w-sidebar flex-col bg-navy-950 text-navy-100">
      {/* Brand */}
      <div className="flex h-topbar shrink-0 items-center justify-between gap-3 border-b border-navy-800 px-5">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-control bg-primary">
            <Gauge className="h-[18px] w-[18px] text-white" aria-hidden />
          </div>
          <div className="leading-tight">
            <div className="text-[15px] font-semibold tracking-tight text-white">AutoInsight</div>
            <div className="text-2xs text-navy-300">Dealership intelligence</div>
          </div>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation"
            className="focus-ring-navy rounded-control p-1.5 text-navy-300 hover:bg-navy-900 hover:text-white"
          >
            <X className="h-5 w-5" aria-hidden />
          </button>
        )}
      </div>

      {/* Destinations */}
      <nav aria-label="Primary" className="flex-1 overflow-y-auto px-3 py-4">
        <ul className="space-y-1">
          {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
            const isActive = id === active;
            return (
              <li key={id}>
                <a
                  href={`#/${id}`}
                  onClick={(e) => {
                    e.preventDefault();
                    onNavigate(id);
                  }}
                  aria-current={isActive ? "page" : undefined}
                  className={`focus-ring-navy group relative flex items-center gap-3 rounded-control px-3 py-2.5 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-navy-800 text-white"
                      : "text-navy-300 hover:bg-navy-900 hover:text-white"
                  }`}
                >
                  {isActive && (
                    <span className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-primary" aria-hidden />
                  )}
                  <Icon
                    className={`h-[18px] w-[18px] shrink-0 ${isActive ? "text-white" : "text-navy-300 group-hover:text-white"}`}
                    aria-hidden
                  />
                  {label}
                </a>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Backend status */}
      <div className="shrink-0 border-t border-navy-800 px-5 py-4">
        <div className="flex items-center gap-2 text-xs text-navy-300" role="status">
          <span className={`h-2 w-2 rounded-full ${STATUS_DOT[backendStatus]}`} aria-hidden />
          {STATUS_LABEL[backendStatus]}
        </div>
      </div>
    </div>
  );
}
