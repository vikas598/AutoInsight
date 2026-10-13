"""
AutoInsight — FastAPI application
===================================
Thin HTTP layer over the LangGraph. All business logic lives in the agents
and services; this file just translates HTTP ↔ graph state.

Routes:
    GET  /api/health                       — liveness check
    GET  /api/schema                       — introspected schema (for UI)
    GET  /api/audit?limit=N                — recent audit entries
    GET  /api/dashboard/overview?period=P  — Overview dashboard aggregates
    POST /api/chat                         — send a query, get a response
    POST /api/approve/{session_id}         — approve or reject a pending write
    POST /api/report/{session_id}          — build a PDF of a session
    GET  /api/download-report/{filename}   — download a built PDF

Session continuity is via LangGraph's checkpointer — the session_id becomes
the LangGraph thread_id, so multi-turn flows (query → approval → execute)
keep their state server-side between HTTP calls.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from app.graph import build_graph
from app.services.audit_log import get_audit_logger
from app.services.dashboard_service import get_overview
from app.services.schema_service import get_schema_service
from app.services.visualization_service import get_visualization_service
from app.state import new_state


# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------
app = FastAPI(
    title="AutoInsight API",
    version="0.1.0",
    description="Multi-agent conversational AI data analyst for automobile dealerships.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",     # Vite dev server
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Shared state — graph singleton + per-session history (for PDF export)
# ---------------------------------------------------------------------------
graph = build_graph()
_session_history: dict[str, list[dict[str, Any]]] = {}


# ---------------------------------------------------------------------------
# Request/response schemas
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    session_id: Optional[str] = Field(None, description="Session id. Omit to start fresh.")
    user_query: str = Field(..., description="Natural-language question or command.")


class ApprovalRequest(BaseModel):
    decision: str = Field(..., description="'approved' or 'rejected'")
    approved_by: Optional[str] = Field("user", description="User identifier for the audit log.")


class ChatResponse(BaseModel):
    session_id: str
    status: str                            # "complete" | "needs_approval" | "error"
    intent: Optional[str] = None
    response: Optional[str] = None
    sql_query: Optional[str] = None
    query_result: Optional[dict] = None
    chart_config: Optional[dict] = None
    assessment: Optional[dict] = None      # populated when status == "needs_approval"
    ml_result: Optional[dict] = None       # technique, summary, metrics, chart_data — ML intents only
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "autoinsight"}


@app.get("/api/schema")
def api_schema() -> dict:
    """Return the introspected schema for the connection form / explorer."""
    svc = get_schema_service()
    schema = svc.get_schema()
    return {
        "table_count": schema.table_count,
        "total_rows":  schema.total_rows,
        "enriched":    schema.enriched,
        "tables": [
            {
                "name":        t.name,
                "description": t.description,
                "row_count":   t.row_count,
                "columns": [
                    {
                        "name":          c.name,
                        "type":          c.type,
                        "nullable":      c.nullable,
                        "primary_key":   c.primary_key,
                        "description":   c.description,
                        "check_values":  c.check_values,
                    }
                    for c in t.columns
                ],
                "foreign_keys": [
                    {"column": fk.column, "to_table": fk.references_table,
                     "to_column": fk.references_column}
                    for fk in t.foreign_keys
                ],
            }
            for t in schema.tables.values()
        ],
    }


@app.get("/api/audit")
def api_audit(limit: int = 20) -> dict:
    """Return the most recent write-path audit entries."""
    entries = get_audit_logger().tail(min(max(1, limit), 200))
    return {"entries": entries, "count": len(entries)}


@app.get("/api/dashboard/overview")
def api_dashboard_overview(
    period: Optional[str] = Query(
        None,
        max_length=8,
        description="A calendar year with sales (e.g. '2024') or 'all'. Defaults to the latest year with sales.",
    ),
) -> dict:
    """Read-only, deterministic aggregates for the Overview dashboard."""
    try:
        return get_overview(period)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="The database is unavailable.")


@app.post("/api/chat", response_model=ChatResponse)
def api_chat(req: ChatRequest) -> ChatResponse:
    """Send a user query to the agent pipeline."""
    session_id = req.session_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}

    state = new_state(user_query=req.user_query, session_id=session_id)

    try:
        final = graph.invoke(state, config=config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph error: {e}")

    return _build_response(session_id, final)


@app.post("/api/approve/{session_id}", response_model=ChatResponse)
def api_approve(session_id: str, req: ApprovalRequest) -> ChatResponse:
    """Post an approval decision for a paused write."""
    if req.decision not in ("approved", "rejected"):
        raise HTTPException(
            status_code=400,
            detail="decision must be 'approved' or 'rejected'",
        )

    config = {"configurable": {"thread_id": session_id}}

    # as_node="supervisor" so the resume routes through sql_agent (where
    # _handle_approval lives) instead of auto-advancing to respond
    try:
        graph.update_state(
            config,
            {"approval_status": req.decision, "approved_by": req.approved_by},
            as_node="supervisor",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"update_state error: {e}")

    try:
        final = graph.invoke(None, config=config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Resume error: {e}")

    return _build_response(session_id, final)


@app.post("/api/report/{session_id}")
def api_report(session_id: str) -> dict:
    """Build a PDF of the session so far."""
    entries = _session_history.get(session_id)
    if not entries:
        raise HTTPException(status_code=404, detail="No history for this session")

    viz = get_visualization_service()
    filename = f"report-{session_id[:8]}.pdf"
    path = viz.build_pdf_report(entries, Path("reports") / filename)
    return {
        "filename": path.name,
        "url":      f"/api/download-report/{path.name}",
        "size_kb":  path.stat().st_size // 1024,
        "entries":  len(entries),
    }


@app.get("/api/download-report/{filename}")
def api_download_report(filename: str):
    """Download a previously built PDF."""
    # Prevent path traversal
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = Path("reports") / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(
        str(path),
        media_type="application/pdf",
        filename=filename,
    )


# ---------------------------------------------------------------------------
# Shared response builder
# ---------------------------------------------------------------------------
def _build_response(session_id: str, state: dict) -> ChatResponse:
    """Turn a LangGraph final state into a ChatResponse + record history."""
    viz = get_visualization_service()
    chart_config = viz.generate_chart_config(state)

    requires_approval = bool(state.get("requires_approval"))
    approval_status = state.get("approval_status")
    error = state.get("error")

    if requires_approval and approval_status == "pending":
        status = "needs_approval"
    elif error:
        status = "error"
    else:
        status = "complete"

    # Record every turn for PDF export (even approval-pending ones so the
    # history shows the proposed change)
    _session_history.setdefault(session_id, []).append({
        "user_query": state.get("user_query", ""),
        "response":   state.get("response", ""),
        "sql_query":  state.get("sql_query", ""),
        "viz_config": chart_config,
        "row_count":  (state.get("query_result") or {}).get("row_count"),
    })

    return ChatResponse(
        session_id=session_id,
        status=status,
        intent=state.get("intent"),
        response=state.get("response"),
        sql_query=state.get("sql_query"),
        query_result=state.get("query_result"),
        chart_config=chart_config,
        assessment=state.get("write_assessment") if requires_approval else None,
        ml_result=state.get("ml_result") or None,
        error=error,
    )
