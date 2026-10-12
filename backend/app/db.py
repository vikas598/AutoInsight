"""
AutoInsight — Database Connection Manager
==========================================
Owns the two restricted SQLAlchemy engines:
  * read_engine   → connects as autoinsight_reader (SELECT only)
  * write_engine  → connects as autoinsight_writer (SELECT + DML)

The SQL agent read path uses read_engine. The write path uses write_engine
AFTER the Safety Pipeline has approved the query. Separating them at the
Postgres role level means a buggy LLM-generated SELECT can never accidentally
UPDATE anything — even if the SQL text looks like an UPDATE, Postgres will
refuse it.

Connection pooling: both engines use pool_pre_ping=True so stale connections
are detected and refreshed. statement_timeout=30s is set at the role level
(see db_users.sql) and reinforced here via connect_args.
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()


class ConnectionManager:
    """Holds the two restricted engines and their session factories."""

    def __init__(self):
        self._read_url = os.environ.get("DATABASE_URL_READ")
        self._write_url = os.environ.get("DATABASE_URL_WRITE")

        if not self._read_url:
            raise RuntimeError("DATABASE_URL_READ not set in environment / .env")
        if not self._write_url:
            raise RuntimeError("DATABASE_URL_WRITE not set in environment / .env")

        self._read_engine: Engine | None = None
        self._write_engine: Engine | None = None

    # ---- Lazy engine construction ----
    @property
    def read_engine(self) -> Engine:
        if self._read_engine is None:
            self._read_engine = create_engine(
                self._read_url,
                pool_size=5,
                max_overflow=5,
                pool_pre_ping=True,
                pool_recycle=1800,     # recycle connections every 30 min
                connect_args={
                    "options": "-c statement_timeout=30000",   # 30s hard cap
                    "application_name": "autoinsight_reader",
                },
            )
        return self._read_engine

    @property
    def write_engine(self) -> Engine:
        if self._write_engine is None:
            self._write_engine = create_engine(
                self._write_url,
                pool_size=3,
                max_overflow=2,
                pool_pre_ping=True,
                pool_recycle=1800,
                connect_args={
                    "options": "-c statement_timeout=30000",
                    "application_name": "autoinsight_writer",
                },
            )
        return self._write_engine

    # ---- Session factories (optional — for ORM use) ----
    @property
    def ReadSession(self):
        return sessionmaker(bind=self.read_engine, autocommit=False, autoflush=False)

    @property
    def WriteSession(self):
        return sessionmaker(bind=self.write_engine, autocommit=False, autoflush=False)

    def dispose(self):
        """Close all pooled connections. Call at app shutdown."""
        if self._read_engine:
            self._read_engine.dispose()
            self._read_engine = None
        if self._write_engine:
            self._write_engine.dispose()
            self._write_engine = None


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_connection_manager() -> ConnectionManager:
    """Return the process-wide ConnectionManager singleton."""
    return ConnectionManager()
