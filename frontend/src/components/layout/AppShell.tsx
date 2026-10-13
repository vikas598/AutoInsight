// AppShell — sidebar + topbar + content frame. Owns the mobile drawer state.

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useBackendHealth } from "../../hooks/useBackendHealth";
import { getNavItem, type RouteId } from "../../navigation";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

interface Props {
  route: RouteId;
  onNavigate: (route: RouteId) => void;
  /** Page-specific controls rendered on the right of the topbar. */
  actions?: ReactNode;
  children: ReactNode;
}

export function AppShell({ route, onNavigate, actions, children }: Props) {
  const [navOpen, setNavOpen] = useState(false);
  const drawerRef = useRef<HTMLDivElement>(null);
  const backendStatus = useBackendHealth();
  const { label, description } = getNavItem(route);

  // Drawer: focus the active link on open, close on Escape, and hand focus
  // back to whatever opened it (the menu button) on close.
  useEffect(() => {
    if (!navOpen) return;
    const opener = document.activeElement as HTMLElement | null;
    const drawer = drawerRef.current;
    (drawer?.querySelector<HTMLElement>("a[aria-current]") ?? drawer?.querySelector<HTMLElement>("a"))?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setNavOpen(false);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      opener?.focus();
    };
  }, [navOpen]);

  const navigate = (next: RouteId) => {
    setNavOpen(false);
    onNavigate(next);
  };

  return (
    <div className="flex h-dvh overflow-hidden bg-canvas">
      {/* Desktop sidebar */}
      <aside className="hidden shrink-0 lg:block">
        <Sidebar active={route} onNavigate={navigate} backendStatus={backendStatus} />
      </aside>

      {/* Mobile drawer */}
      {navOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <div className="absolute inset-0 bg-navy-950/50" onClick={() => setNavOpen(false)} aria-hidden />
          <div ref={drawerRef} className="relative h-full w-sidebar max-w-[85vw] shadow-overlay">
            <Sidebar
              active={route}
              onNavigate={navigate}
              backendStatus={backendStatus}
              onClose={() => setNavOpen(false)}
            />
          </div>
        </div>
      )}

      {/* Content column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar
          title={label}
          description={description}
          actions={actions}
          onOpenNav={() => setNavOpen(true)}
        />
        <main className="min-h-0 flex-1">{children}</main>
      </div>
    </div>
  );
}
