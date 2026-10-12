"""
AutoInsight — SQL Agent (Read Path)
====================================
The SQL / CRUD agent handles two intents from the Supervisor:

    * sql_read   — the full pipeline (THIS FILE, read-path section)
    * sql_write  — gated behind the Safety Pipeline (Step 6, still stubbed)

Read-path pipeline:

    user_query + schema_text
            ↓
    [1] LLM generates SQL           ← Groq / OpenAI / Together
            ↓
    [2] 3-stage validation
          a. AST parse               ← sqlglot
          b. SELECT-only enforcement ← walk AST for forbidden node types
          c. Schema references       ← SchemaService.validate_references
            ↓
    [3] execute_read_query          ← LIMIT + timeout enforced
            ↓
    [4] LLM narrates the result    ← short, numbers-first answer

Any failure in 1-3 sets state["error"] and increments retry_count so the
Supervisor can take another pass (bounded by MAX_RETRIES in state.py).
"""

from __future__ import annotations

import json

import sqlglot
import sqlglot.expressions as exp

from app.llm import chat, is_llm_available
from app.services.schema_service import get_schema_service
from app.services.sql_executor import SQLExecutionError, execute_read_query
from app.state import AutoInsightState, QueryResult


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


NARRATIVE_PROMPT = """You are a business analyst speaking to a dealership manager. Given the user's question and the SQL result, write a concise 2-3 sentence answer in plain English.

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


# ===========================================================================
# Entry point (LangGraph node)
# ===========================================================================
def sql_agent_node(state: AutoInsightState) -> dict:
    """Dispatch on intent — read path is real, write path still stubbed."""
    intent = state.get("intent")

    if intent == "sql_read":
        return _handle_read(state)

    if intent == "sql_write":
        return _handle_write_stub(state)      # real impl lands in Step 6

    return {
        "error": f"sql_agent called with unexpected intent: {intent}",
        "retry_count": state.get("retry_count", 0) + 1,
    }


# ===========================================================================
# READ PATH
# ===========================================================================
def _handle_read(state: AutoInsightState) -> dict:
    """Full generate → validate → execute → narrate pipeline."""
    user_query = (state.get("user_query") or "").strip()
    if not user_query:
        return _fail(state, "No user query provided")

    schema_svc = get_schema_service()
    schema_text = schema_svc.get_schema_text()

    # ---- 1. Generate ----
    try:
        sql = _generate_sql(user_query, schema_text)
    except Exception as e:
        return _fail(state, f"SQL generation failed: {e}")

    if not sql:
        return _fail(state, "LLM returned empty SQL — try rephrasing your question")

    # ---- 2. Validate ----
    valid, errors = _validate_sql(sql, schema_svc)
    if not valid:
        return _fail(
            state,
            f"SQL validation failed: {'; '.join(errors)}",
            sql=sql,
        )

    # ---- 3. Execute ----
    try:
        result = execute_read_query(sql)
    except SQLExecutionError as e:
        return _fail(state, f"Query execution error: {e}", sql=sql)

    # ---- 4. Narrate ----
    narrative = _narrate_result(user_query, result)

    return {
        "sql_query": result["executed_sql"],
        "query_result": result,
        "response": narrative,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Stage 1 — Generation
# ---------------------------------------------------------------------------
def _generate_sql(user_query: str, schema_text: str) -> str:
    """Call the LLM to produce a SQL query."""
    if not is_llm_available():
        raise RuntimeError("LLM not configured — set LLM_API_KEY in .env")

    system = SQL_READ_SYSTEM_PROMPT.format(schema_text=schema_text)
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
    """Remove ```sql fences and surrounding whitespace / trailing semicolons."""
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip().rstrip(";").strip()


# ---------------------------------------------------------------------------
# Stage 2 — Validation (3 sub-stages)
# ---------------------------------------------------------------------------
# Forbidden AST node types — a SELECT must contain none of these anywhere.
_FORBIDDEN_NODES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.TruncateTable,
    exp.Merge,
)

# Allowed top-level AST node types
_ALLOWED_TOP = (exp.Select, exp.Union, exp.Subquery, exp.With)


def _validate_sql(sql: str, schema_svc) -> tuple[bool, list[str]]:
    """
    3-stage validation:
      (a) AST parse — valid Postgres syntax
      (b) SELECT-only — forbid every DML / DDL node type anywhere in the tree
      (c) Schema references — tables and qualified columns must exist
    """
    # ---- (a) AST parse ----
    try:
        parsed = sqlglot.parse_one(sql, read="postgres")
    except Exception as e:
        return (False, [f"parse error: {e}"])

    if parsed is None:
        return (False, ["parse error: empty query"])

    errors: list[str] = []

    # ---- (b) SELECT only ----
    for node in parsed.walk():
        actual_node = node[0] if isinstance(node, tuple) else node
        if isinstance(actual_node, _FORBIDDEN_NODES):
            return (
                False,
                [f"only SELECT allowed — found {type(actual_node).__name__}"],
            )

    if not isinstance(parsed, _ALLOWED_TOP):
        errors.append(f"top-level must be SELECT — got {type(parsed).__name__}")

    # ---- (c) Schema references ----
    ok, ref_errors = schema_svc.validate_references(sql)
    if not ok:
        errors.extend(ref_errors)

    return (len(errors) == 0, errors)


# ---------------------------------------------------------------------------
# Stage 4 — Narration
# ---------------------------------------------------------------------------
def _narrate_result(user_query: str, result: QueryResult) -> str:
    """Have the LLM write a short answer from the query result."""
    if not is_llm_available():
        return _simple_narrative(result)

    # Compact result preview — first 20 rows is enough for the LLM to pattern-match
    preview_rows = result["rows"][:20]
    preview_json = json.dumps(
        {"columns": result["columns"], "rows": preview_rows},
        indent=2,
        default=str,
    )

    truncated_note = ""
    if result.get("truncated"):
        truncated_note = f", capped at {result['row_count']}"

    try:
        reply = chat(
            messages=[{
                "role": "user",
                "content": NARRATIVE_PROMPT.format(
                    user_query=user_query,
                    sql=result["executed_sql"],
                    row_count=result["row_count"],
                    truncated_note=truncated_note,
                    result_preview=preview_json,
                ),
            }],
            temperature=0.3,
            max_tokens=250,
        )
        return reply.strip() or _simple_narrative(result)
    except Exception:
        return _simple_narrative(result)


def _simple_narrative(result: QueryResult) -> str:
    """Fallback when the LLM is unavailable or fails."""
    rc = result["row_count"]
    cols = result.get("columns") or []
    if rc == 0:
        return "The query returned no results."
    if rc == 1 and len(cols) == 1:
        val = result["rows"][0][0]
        return f"Result: {val}"
    return f"Query returned {rc} row{'s' if rc != 1 else ''} across {len(cols)} column{'s' if len(cols) != 1 else ''}."


# ===========================================================================
# WRITE PATH — stubbed, replaced in Step 6
# ===========================================================================
def _handle_write_stub(state: AutoInsightState) -> dict:
    """Preserved from Step 2 — real Safety Pipeline integration comes next."""
    stub_sql = "UPDATE vehicles SET status = 'reserved' WHERE id = 123;"

    if state.get("approval_status") == "approved":
        return {
            "query_result": {
                "columns": [], "rows": [], "row_count": 1,
                "truncated": False, "executed_sql": stub_sql,
            },
            "response": "[STUB] Executed write. 1 row affected.",
            "requires_approval": False,
            "approval_status": "not_required",
            "error": None,
        }

    return {
        "sql_query": stub_sql,
        "risk_score": 35,
        "preview_result": {
            "columns": ["affected_rows"], "rows": [[1]],
            "row_count": 1, "truncated": False, "executed_sql": stub_sql,
        },
        "requires_approval": True,
        "approval_status": "pending",
        "response": "[STUB] Prepared write. Awaiting approval.",
        "error": None,
    }


# ===========================================================================
# Helpers
# ===========================================================================
def _fail(state: AutoInsightState, msg: str, sql: str = "") -> dict:
    """
    Build an error update. The router sees state["error"] + retry_count
    and loops back to the Supervisor (bounded by MAX_RETRIES).
    """
    return {
        "error": msg,
        "sql_query": sql or state.get("sql_query", ""),
        "retry_count": state.get("retry_count", 0) + 1,
        "response": f"I couldn't complete that: {msg}",
    }
