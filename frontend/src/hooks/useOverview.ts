// useOverview — dashboard data for the Overview page.
//
// * One aggregated request (GET /api/dashboard/overview) feeds every sales
//   and inventory section; recent activity comes from GET /api/audit and is
//   loaded independently so its failure can't blank the dashboard.
// * Lives above the page: data survives navigation; nothing refetches until
//   the period changes or the user presses Refresh. No polling.
// * Changing the period aborts the in-flight request, so a slow response for
//   an old period can never overwrite a newer one.

import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "../api";
import type { AuditEntry, OverviewResponse } from "../types";

const AUDIT_LIMIT = 8;

export type Load<T> =
  | { status: "idle" }
  | { status: "loading" }                               // nothing to show yet
  | { status: "ready"; data: T; refreshing: boolean }
  | { status: "error"; message: string };

const isAbort = (e: unknown) => e instanceof DOMException && e.name === "AbortError";

export function useOverview(enabled: boolean) {
  // The user's explicit choice; null = server default (latest year with sales)
  const [requested, setRequested] = useState<string | null>(null);
  const [overview, setOverview] = useState<Load<OverviewResponse>>({ status: "idle" });
  const [activity, setActivity] = useState<Load<AuditEntry[]>>({ status: "idle" });
  const [reloadKey, setReloadKey] = useState(0);
  const loadedKey = useRef<string | null>(null);
  const activityKey = useRef<number | null>(null);

  // Sales + inventory aggregates: reload on period change or Refresh
  useEffect(() => {
    if (!enabled) return;
    const key = `${requested ?? "default"}#${reloadKey}`;
    if (loadedKey.current === key) return;
    loadedKey.current = key;

    const ctrl = new AbortController();
    let done = false;
    setOverview((prev) => (prev.status === "ready" ? { ...prev, refreshing: true } : { status: "loading" }));
    api.overview(requested, ctrl.signal)
      .then((data) => setOverview({ status: "ready", data, refreshing: false }))
      .catch((e) => {
        if (isAbort(e)) return;
        loadedKey.current = null;                     // allow retry
        setOverview({ status: "error", message: errorMessage(e) });
      })
      .finally(() => { done = true; });

    return () => {
      // Cut short (period changed, page left mid-load, StrictMode remount):
      // abort, and let the next run fetch again. Completed loads are kept.
      if (!done) {
        ctrl.abort();
        if (loadedKey.current === key) loadedKey.current = null;
      }
    };
  }, [enabled, requested, reloadKey]);

  // Audit activity doesn't depend on the period: first visit + Refresh only
  useEffect(() => {
    if (!enabled || activityKey.current === reloadKey) return;
    activityKey.current = reloadKey;

    const ctrl = new AbortController();
    let done = false;
    setActivity((prev) => (prev.status === "ready" ? { ...prev, refreshing: true } : { status: "loading" }));
    api.audit(AUDIT_LIMIT, ctrl.signal)
      .then((res) => setActivity({ status: "ready", data: res.entries, refreshing: false }))
      .catch((e) => {
        if (isAbort(e)) return;
        activityKey.current = null;
        setActivity({ status: "error", message: errorMessage(e) });
      })
      .finally(() => { done = true; });

    return () => {
      if (!done) {
        ctrl.abort();
        if (activityKey.current === reloadKey) activityKey.current = null;
      }
    };
  }, [enabled, reloadKey]);

  /** The period actually displayed (what the server answered with). */
  const shownPeriod = overview.status === "ready" ? overview.data.period?.id ?? null : requested;

  const choosePeriod = useCallback((next: string) => {
    if (next === shownPeriod && overview.status === "ready") return;   // already showing it
    setRequested(next);
  }, [shownPeriod, overview.status]);

  const refresh = useCallback(() => setReloadKey((k) => k + 1), []);

  const busy = overview.status === "loading" || (overview.status === "ready" && overview.refreshing);

  return { shownPeriod, choosePeriod, overview, activity, refresh, busy };
}

export type OverviewState = ReturnType<typeof useOverview>;
