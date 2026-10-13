// useBackendHealth — polls GET /api/health so the shell can show whether the
// analyst backend is reachable.

import { useEffect, useState } from "react";
import { api } from "../api";

export type BackendStatus = "checking" | "online" | "offline";

const POLL_MS = 30_000;

export function useBackendHealth(): BackendStatus {
  const [status, setStatus] = useState<BackendStatus>("checking");

  useEffect(() => {
    let cancelled = false;
    const check = () =>
      api.health()
        .then(() => !cancelled && setStatus("online"))
        .catch(() => !cancelled && setStatus("offline"));

    check();
    const id = window.setInterval(check, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  return status;
}
