// useHashRoute — minimal hash-based routing (#/analyst, #/overview, …).
// Five flat pages don't justify a router dependency; the hash keeps URLs
// shareable and the back button working without any server config.

import { useCallback, useEffect, useState } from "react";
import { DEFAULT_ROUTE, isRouteId, type RouteId } from "../navigation";

function readHash(): RouteId {
  const value = window.location.hash.replace(/^#\/?/, "");
  return isRouteId(value) ? value : DEFAULT_ROUTE;
}

export function useHashRoute(): [RouteId, (route: RouteId) => void] {
  const [route, setRoute] = useState<RouteId>(readHash);

  useEffect(() => {
    const onChange = () => setRoute(readHash());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const navigate = useCallback((next: RouteId) => {
    window.location.hash = `/${next}`;
  }, []);

  return [route, navigate];
}
