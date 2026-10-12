"""
AutoInsight — SQL Agent (complete)
===================================
Handles both intents from the Supervisor:

    * sql_read   — generate → validate → execute → narrate
    * sql_write  — generate → assess (Safety Pipeline) → interrupt for
                   approval → execute on approval → audit → narrate

Write-path flow across the LangGraph interrupt:

    First invocation (approval_status not set / "not_required"):
        _handle_write()
            → generate SQL via LLM
            → pipeline.assess()
            → populate state with write_assessment, preview_result,
              risk_score, requires_approval=True, approval_status="pending"
            → router sends state to wait_approval, graph INTERRUPTS

    Frontend posts approval decision via graph.update_state(), then resumes:

    Second invocation (approval_status in {"approved","rejected"}):
        _handle_approval()
            → reconstruct Assessment from state["write_assessment"]
            → pipeline.execute() OR pipeline.reject() + audit
            → populate query_result + narrative response

The Safety Pipeline (Step 5) is the deterministic muscle; this agent is
the LangGraph glue around it + the LLM for SQL generation and narration.
"""

from __future__ import annotations

import json

import sqlglot
import sqlglot.expressions as exp

from app.llm import chat, is_llm_available
from app.services.safety_pipeline import Assessment, get_safety_pipeline
from app.services.schema_service import get_schema_service
from app.services.sql_executor import SQLExecutionError, execute_read_query
from app.state import AutoInsightState, QueryResult, WriteAssessment


# ===========================================================================
# Prompts
# ===========================================================================
SQL_READ_SYSTEM_PROMPT = """You are a PostgreSQL expert for an automobile dealership. Given the schema below and a user's natural language question, write a single SELECT query that answers it.

RULES:
- Output ONLY the SQL query — no explanations, no markdown fences, no comments
- Use ONLY tables and columns from the schema below
- Prefer explicit JOINs over subqueries where equivalent
- Use short aliases (FROM sales s JOIN customers c ON s.customer_id = c.id)
- When aggregating, include every non-aggregated column in GROUP BY
- For time-based queries use DATE_TRUNC / EXTRACT (dialect: PostgreSQL)
- For "top N" / "latest" use ORDER BY ... LIMIT N
- Monetary columns are in INR; dates follow the YYYY-MM-DD format
- NEVER emit INSERT, UPDATE, DELETE, DROP, TRUNCATE, or any DDL

{schema_text}

Reply with the SQL query only."""


SQL_WRITE_SYSTEM_PROMPT = """You are a PostgreSQL expert for an automobile dealership. Given the schema below and a user's natural language request to CHANGE data, write a single INSERT, UPDATE, or DELETE statement.

RULES:
- Output ONLY the SQL — no explanations, no markdown fences, no comments
- Choose exactly one of: INSERT INTO ..., UPDATE ..., DELETE FROM ...
- Use ONLY tables and columns from the schema below
- For UPDATE and DELETE, ALWAYS include a WHERE clause (never unbounded)
- Prefer WHERE on primary keys (`id = ...`) for surgical operations
- Respect CHECK constraints — only use enum values the schema lists
- For INSERT, include every NOT NULL column that has no DEFAULT
- NEVER emit SELECT, DROP, TRUNCATE, CREATE, ALTER, or any DDL
- NEVER chain multiple statements with semicolons

The Safety Pipeline will show the user a preview + risk score before this runs. Write the single best SQL for the request — the user will approve or reject it.

{schema_text}

Reply with the SQL query only."""


READ_NARRATIVE_PROMPT = """You are a business analyst speaking to a dealership manager. Given the user's question and the SQL result, write a concise 2-3 sentence answer in plain English.

RULES:
- Lead with the direct answer (the number, the trend, the finding)
- Quote specific figures from the result
- Format money as Indian Rupees using lakh/crore for large amounts (₹1.5 lakh, ₹2.3 crore). Smaller amounts: ₹45,000
- Do NOT describe the SQL or how it was computed
- Do NOT suggest next steps unless the data clearly asks for them

User asked: {user_query}

SQL that ran:
{sql}

Result ({row_count} rows{truncated_note}):
{result_preview}

Write the narrative answer now:"""


WRITE_NARRATIVE_PROMPT = """You are a business analyst reporting a database change to a dealership manager. State what just happened in 1-2 sentences.

RULES:
- Lead with the action (Updated / Inserted / Deleted) and the count
- Reference specific values from the user's request when they help clarity
- Format money as Indian Rupees with lakh/crore where sensible
- Do NOT describe the SQL
- Do NOT suggest next steps

User requested: {user_query}
Operation: {operation} on {target_table}
Rows affected: {affected_rows}
SQL that ran: {sql}

Write the confirmation message now:"""


# ===========================================================================
# LangGraph node — entry point
# ===========================================================================
def sql_agent_node(state: AutoInsightState) -> dict:
    """
    Dispatch on intent. For sql_write we also check approval_status so a
    re-entry after the wait_approval interrupt executes rather than
    re-generating the SQL.
    """
    intent = state.get("intent")

    if intent == "sql_read":
        return _handle_read(state)

    if intent == "sql_write":
        # Second pass — user already decided
        status = state.get("approval_status")
        if status in ("approved", "rejected"):
            return _handle_approval(state)
        # First pass — prepare + assess
        return _handle_write(state)

    return {
        "error": f"sql_agent called with unexpected intent: {intent}",
        "retry_count": state.get("retry_count", 0) + 1,
    }


# ===========================================================================
# READ PATH (unchanged from Step 4)
# ===========================================================================
def _handle_read(state: AutoInsightState) -> dict:
    user_query = (state.get("user_query") or "").strip()
    if not user_query:
        return _fail(state, "No user query provided")

    schema_svc = get_schema_service()
    schema_text = schema_svc.get_schema_text()

    try:
        sql = _generate_sql(user_query, schema_text, SQL_READ_SYSTEM_PROMPT)
    except Exception as e:
        return _fail(state, f"SQL generation failed: {e}")

    if not sql:
        return _fail(state, "LLM returned empty SQL — try rephrasing your question")

    valid, errors = _validate_read_sql(sql, schema_svc)
    if not valid:
        return _fail(state, f"SQL validation failed: {'; '.join(errors)}", sql=sql)

    try:
        result = execute_read_query(sql)
    except SQLExecutionError as e:
        return _fail(state, f"Query execution error: {e}", sql=sql)

    narrative = _narrate_read_result(user_query, result)
    return {
        "sql_query": result["executed_sql"],
        "query_result": result,
        "response": narrative,
        "error": None,
    }


# ===========================================================================
# WRITE PATH — Phase 1: generate + assess (before interrupt)
# ===========================================================================
def _handle_write(state: AutoInsightState) -> dict:
    """
    Generate a write SQL, run it through the Safety Pipeline, and populate
    state with the Assessment. The LangGraph router sees requires_approval
    + approval_status="pending" and routes to wait_approval, where the
    graph interrupts.
    """
    user_query = (state.get("user_query") or "").strip()
    session_id = state.get("session_id", "unknown")

    if not user_query:
        return _fail(state, "No user query provided")

    schema_svc = get_schema_service()
    schema_text = schema_svc.get_schema_text()

    # ---- 1. Generate write SQL ----
    try:
        sql = _generate_sql(user_query, schema_text, SQL_WRITE_SYSTEM_PROMPT)
    except Exception as e:
        return _fail(state, f"SQL generation failed: {e}")

    if not sql:
        return _fail(state, "LLM returned empty SQL — try rephrasing your request")

    # ---- 2. Assess via Safety Pipeline (handles stages 1-4) ----
    pipeline = get_safety_pipeline()
    assessment = pipeline.assess(
        sql, session_id=session_id, user_query=user_query,
    )

    # Blocked at validation — audit and bail
    if assessment.decision == "blocked":
        pipeline.execute(                           # audits the block
            assessment, session_id=session_id, user_query=user_query,
        )
        return _fail(state, f"Safety pipeline blocked this: {assessment.error}", sql=sql)

    # ---- 3. Populate state for the frontend ApprovalCard ----
    write_assessment: WriteAssessment = {
        "sql":               assessment.sql,
        "operation":         assessment.operation,
        "target_table":      assessment.target_table,
        "risk_score":        assessment.risk_score,
        "risk_factors":      assessment.risk_factors,
        "requires_approval": assessment.requires_approval,
        "preview_columns":   assessment.preview_columns,
        "preview_rows":      assessment.preview_rows,
        "affected_rows":     assessment.affected_rows,
        "decision":          assessment.decision,
        "error":             assessment.error,
    }

    preview_result: QueryResult = {
        "columns":      assessment.preview_columns,
        "rows":         assessment.preview_rows,
        "row_count":    assessment.affected_rows,
        "truncated":    len(assessment.preview_rows) >= 50,
        "executed_sql": "",   # the preview SELECT, not the write — hidden
    }

    # Auto-approved path (risk < threshold) — execute immediately
    if assessment.decision == "auto_approved":
        return _execute_assessment(
            assessment, state,
            approved_by=None,     # system auto-approval
        ) | {
            "sql_query":        assessment.sql,
            "write_assessment": write_assessment,
            "preview_result":   preview_result,
            "risk_score":       assessment.risk_score,
        }

    # Needs human approval — pause the graph
    return {
        "sql_query":         assessment.sql,
        "write_assessment":  write_assessment,
        "preview_result":    preview_result,
        "risk_score":        assessment.risk_score,
        "requires_approval": True,
        "approval_status":   "pending",
        "response": (
            f"I prepared a {assessment.operation} on `{assessment.target_table}` "
            f"affecting {assessment.affected_rows} row(s). "
            f"Risk score: {assessment.risk_score}/100. "
            "Review the preview and approve or reject."
        ),
        "error": None,
    }


# ===========================================================================
# WRITE PATH — Phase 2: execute after approval
# ===========================================================================
def _handle_approval(state: AutoInsightState) -> dict:
    """
    Runs after the wait_approval interrupt resumes. Reads approval_status
    and executes or rejects the write via the Safety Pipeline.
    """
    status = state.get("approval_status")
    assessment_dict = state.get("write_assessment") or {}
    session_id = state.get("session_id", "unknown")
    user_query = state.get("user_query", "")
    approved_by = state.get("approved_by")

    if not assessment_dict.get("sql"):
        return _fail(state, "Approval resumed without a stored assessment")

    # Reconstruct the Assessment dataclass for the pipeline
    assessment = Assessment(
        sql=assessment_dict["sql"],
        operation=assessment_dict["operation"],
        target_table=assessment_dict["target_table"],
        risk_score=assessment_dict["risk_score"],
        risk_factors=assessment_dict["risk_factors"],
        requires_approval=assessment_dict["requires_approval"],
        preview_columns=assessment_dict.get("preview_columns", []),
        preview_rows=assessment_dict.get("preview_rows", []),
        affected_rows=assessment_dict.get("affected_rows", 0),
        decision=assessment_dict.get("decision", "needs_approval"),
        error=assessment_dict.get("error"),
    )

    pipeline = get_safety_pipeline()

    if status == "rejected":
        pipeline.reject(
            assessment,
            session_id=session_id,
            user_query=user_query,
            rejected_by=approved_by,
        )
        return {
            "query_result": {
                "columns": [], "rows": [], "row_count": 0,
                "truncated": False, "executed_sql": assessment.sql,
            },
            "requires_approval": False,
            "approval_status":   "not_required",
            "response":          f"Change rejected. No modifications were made to the database.",
            "error":             None,
        }

    # Approved
    return _execute_assessment(assessment, state, approved_by=approved_by)


def _execute_assessment(
    assessment: Assessment,
    state: AutoInsightState,
    *,
    approved_by: str | None,
) -> dict:
    """Execute an approved assessment and build the final state update."""
    pipeline = get_safety_pipeline()
    session_id = state.get("session_id", "unknown")
    user_query = state.get("user_query", "")

    result = pipeline.execute(
        assessment,
        session_id=session_id,
        user_query=user_query,
        approved_by=approved_by,
    )

    if not result["executed"]:
        return _fail(
            state,
            f"Execution failed: {result.get('error', 'unknown error')}",
            sql=assessment.sql,
        )

    narrative = _narrate_write_result(user_query, assessment, result["affected_rows"])

    return {
        "query_result": {
            "columns":      [],
            "rows":         [],
            "row_count":    result["affected_rows"],
            "truncated":    False,
            "executed_sql": assessment.sql,
        },
        "requires_approval": False,
        "approval_status":   "not_required",
        "response":          narrative,
        "error":             None,
    }


# ===========================================================================
# Shared helpers
# ===========================================================================
def _generate_sql(user_query: str, schema_text: str, system_template: str) -> str:
    """Call the LLM to produce a SQL query (read or write)."""
    if not is_llm_available():
        raise RuntimeError("LLM not configured — set LLM_API_KEY in .env")
    system = system_template.format(schema_text=schema_text)
    content = chat(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_query},
        ],
        temperature=0,
        max_tokens=600,
    )
    return _strip_sql_markdown(content)


def _strip_sql_markdown(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip().rstrip(";").strip()


# ---------------------------------------------------------------------------
# Read-path validation (identical to Step 4)
# ---------------------------------------------------------------------------
_FORBIDDEN_NODES_READ = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create,
    exp.Alter, exp.TruncateTable, exp.Merge,
)
_ALLOWED_TOP_READ = (exp.Select, exp.Union, exp.Subquery, exp.With)


def _validate_read_sql(sql: str, schema_svc) -> tuple[bool, list[str]]:
    try:
        parsed = sqlglot.parse_one(sql, read="postgres")
    except Exception as e:
        return (False, [f"parse error: {e}"])

    if parsed is None:
        return (False, ["parse error: empty query"])

    for node in parsed.walk():
        n = node[0] if isinstance(node, tuple) else node
        if isinstance(n, _FORBIDDEN_NODES_READ):
            return (False, [f"only SELECT allowed — found {type(n).__name__}"])

    errors: list[str] = []
    if not isinstance(parsed, _ALLOWED_TOP_READ):
        errors.append(f"top-level must be SELECT — got {type(parsed).__name__}")

    ok, ref_errors = schema_svc.validate_references(sql)
    if not ok:
        errors.extend(ref_errors)

    return (len(errors) == 0, errors)


# ---------------------------------------------------------------------------
# Narration
# ---------------------------------------------------------------------------
def _narrate_read_result(user_query: str, result: QueryResult) -> str:
    if not is_llm_available():
        return _simple_read_narrative(result)

    preview_rows = result["rows"][:20]
    preview_json = json.dumps(
        {"columns": result["columns"], "rows": preview_rows},
        indent=2, default=str,
    )
    truncated_note = ""
    if result.get("truncated"):
        truncated_note = f", capped at {result['row_count']}"

    try:
        reply = chat(
            messages=[{
                "role": "user",
                "content": READ_NARRATIVE_PROMPT.format(
                    user_query=user_query, sql=result["executed_sql"],
                    row_count=result["row_count"],
                    truncated_note=truncated_note,
                    result_preview=preview_json,
                ),
            }],
            temperature=0.3, max_tokens=250,
        )
        return reply.strip() or _simple_read_narrative(result)
    except Exception:
        return _simple_read_narrative(result)


def _narrate_write_result(user_query: str, assessment: Assessment, affected_rows: int) -> str:
    """Build a one-line confirmation for the write path."""
    if not is_llm_available():
        return _simple_write_narrative(assessment, affected_rows)

    try:
        reply = chat(
            messages=[{
                "role": "user",
                "content": WRITE_NARRATIVE_PROMPT.format(
                    user_query=user_query,
                    operation=assessment.operation,
                    target_table=assessment.target_table,
                    affected_rows=affected_rows,
                    sql=assessment.sql,
                ),
            }],
            temperature=0.3, max_tokens=120,
        )
        return reply.strip() or _simple_write_narrative(assessment, affected_rows)
    except Exception:
        return _simple_write_narrative(assessment, affected_rows)


def _simple_read_narrative(result: QueryResult) -> str:
    rc = result["row_count"]
    cols = result.get("columns") or []
    if rc == 0:
        return "The query returned no results."
    if rc == 1 and len(cols) == 1:
        return f"Result: {result['rows'][0][0]}"
    return f"Query returned {rc} row{'s' if rc != 1 else ''} across {len(cols)} column{'s' if len(cols) != 1 else ''}."


def _simple_write_narrative(assessment: Assessment, affected: int) -> str:
    verb = {"INSERT": "Inserted", "UPDATE": "Updated", "DELETE": "Deleted"}[assessment.operation]
    return f"{verb} {affected} row{'s' if affected != 1 else ''} in `{assessment.target_table}`."


# ---------------------------------------------------------------------------
# Error helper
# ---------------------------------------------------------------------------
def _fail(state: AutoInsightState, msg: str, sql: str = "") -> dict:
    return {
        "error":       msg,
        "sql_query":   sql or state.get("sql_query", ""),
        "retry_count": state.get("retry_count", 0) + 1,
        "response":    f"I couldn't complete that: {msg}",
    }
