"""
AutoInsight — Audit Logger
===========================
Append-only JSONL log of every write attempt the Safety Pipeline sees.

Each line is a self-contained JSON object with everything you need to
reconstruct what happened:

    - timestamp         ISO-8601 UTC
    - session_id        LangGraph thread id
    - user_query        the raw NL question
    - sql               the generated SQL
    - operation         INSERT / UPDATE / DELETE
    - target_table      which table was being written to
    - risk_score        0-100 from the risk engine
    - risk_factors      {op, table_sensitivity, where_specificity, est_rows}
    - affected_rows     from the transactional preview
    - decision          auto_approved / approved / rejected / blocked / error
    - executed          true if a COMMIT was issued
    - approved_by       user id, or None for auto-approvals
    - error             string, or None

The file is opened append-only. Reads use a separate iterator helper.

Default log path: ./logs/audit.jsonl   (override via AUDIT_LOG_PATH in .env)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


DEFAULT_LOG_PATH = Path(os.environ.get("AUDIT_LOG_PATH", "logs/audit.jsonl"))


class AuditLogger:
    """Append-only JSONL writer for write-path decisions."""

    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else DEFAULT_LOG_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        *,
        session_id: str,
        user_query: str,
        sql: str,
        operation: str,
        target_table: str,
        risk_score: int,
        risk_factors: dict[str, Any],
        affected_rows: int,
        decision: str,
        executed: bool,
        approved_by: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Write one audit record and return it (for inclusion in state)."""
        entry = {
            "timestamp":     datetime.now(timezone.utc).isoformat(),
            "session_id":    session_id,
            "user_query":    user_query,
            "sql":           sql,
            "operation":     operation,
            "target_table":  target_table,
            "risk_score":    risk_score,
            "risk_factors":  risk_factors,
            "affected_rows": affected_rows,
            "decision":      decision,
            "executed":      executed,
            "approved_by":   approved_by,
            "error":         error,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        return entry

    def tail(self, n: int = 20) -> list[dict[str, Any]]:
        """Return the last `n` entries (newest first)."""
        if not self.path.exists():
            return []
        with self.path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        out: list[dict[str, Any]] = []
        for raw in reversed(lines[-n:]):
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        return out

    def iterate(self) -> Iterator[dict[str, Any]]:
        """Yield every entry (oldest first). Useful for reports."""
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


# Module-level singleton
_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
