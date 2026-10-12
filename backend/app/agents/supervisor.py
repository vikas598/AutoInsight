"""
AutoInsight — Supervisor Agent (LLM-based router)
===================================================
Classifies the user's natural-language request into one of 7 intents, then
dispatches to the appropriate downstream agent via the LangGraph router.

Uses the FAST model (llama-3.1-8b-instant on Groq) — this is a 7-class
classification problem, so Llama 3.1 8B at ~250 tok/s is both faster and
cheaper than running the main 70B model.

A rule-based fallback kicks in only when the LLM is unavailable (no API key
set, or network error). The fallback uses tightened keyword patterns.

Retry handling: on turns where state["error"] is set and retry_count > 0,
the Supervisor preserves the existing intent (the SQL/ML agent already
chose correctly, and this is just an execution-retry pass) and appends a
retry note to the plan.
"""

from __future__ import annotations

import json

from app.llm import chat, is_llm_available
from app.state import AutoInsightState


# ---------------------------------------------------------------------------
# Classification prompt (sent to the FAST model)
# ---------------------------------------------------------------------------
CLASSIFY_PROMPT = """You classify requests for an automobile dealership data assistant.

Return a JSON object with exactly this shape:
{{"intent": "<label>", "reason": "<brief rationale, under 15 words>"}}

Labels (choose exactly one):

- "sql_read"
    Question that READS data from the database.
    Examples: "how many sales in March?", "top 5 customers by spend",
              "list vehicles under 10 lakh", "which salesperson closed the most deals?"

- "sql_write"
    Request to CHANGE / MUTATE data in the database.
    Examples: "add a new lead for customer 1", "update vehicle 5 status to reserved",
              "delete all lost leads", "mark sale 123 as refunded",
              "insert an expense of 50000 for marketing", "cancel the service for vehicle 7"

- "ml_forecast"
    Predict future values from time-series data.
    Examples: "forecast sales for next quarter", "predict revenue for Q4",
              "project how many Creta units we'll sell next 3 months"

- "ml_cluster"
    Group / segment customers or vehicles into clusters.
    Examples: "cluster our customers by spending", "segment buyers into tiers",
              "group vehicles by price band"

- "ml_anomaly"
    Flag anomalies, outliers, suspicious transactions, fraud, data-entry errors.
    Examples: "find unusual sales", "any suspicious discounts?",
              "detect anomalies in service costs", "flag outlier transactions"

- "clarification"
    The request is too vague to act on without more info.

- "unsupported"
    Outside the dealership data domain (greetings, chit-chat, generic coding help).

User request: {query}

Return ONLY the JSON, no prose, no markdown fences."""


VALID_INTENTS = {
    "sql_read", "sql_write", "ml_forecast", "ml_cluster",
    "ml_anomaly", "clarification", "unsupported",
}


# ---------------------------------------------------------------------------
# Rule-based fallback — only used when LLM unavailable
# ---------------------------------------------------------------------------
# Trailing spaces make the match word-boundary-ish without a full regex.
ML_FORECAST_KW = ("forecast", "predict", "projection", "project forward")
ML_CLUSTER_KW  = ("cluster", "segment", "group customers", "customer tier", "price band")
ML_ANOMALY_KW  = ("anomal", "outlier", "unusual", "suspicious", "fraud", "flag")
SQL_WRITE_KW   = (
    "insert ", "update ", "delete ", "remove ", "modify ", "change ",
    "add a ", "add new", "add new ", " add ", "create ", "mark ", "set ",
    "cancel ", "assign ", "refund",
)


def _fallback_classify(query: str) -> str:
    q = query.lower()
    if any(kw in q for kw in ML_FORECAST_KW): return "ml_forecast"
    if any(kw in q for kw in ML_CLUSTER_KW):  return "ml_cluster"
    if any(kw in q for kw in ML_ANOMALY_KW):  return "ml_anomaly"
    if any(kw in q for kw in SQL_WRITE_KW):   return "sql_write"
    return "sql_read"


# ---------------------------------------------------------------------------
# LangGraph node
# ---------------------------------------------------------------------------
def supervisor_node(state: AutoInsightState) -> dict:
    """Classify intent (first pass) or acknowledge retry (subsequent passes)."""
    query = (state.get("user_query") or "").strip()

    # ---- Retry path ----
    # On an error-retry turn, don't reclassify. The downstream agent already
    # chose correctly; this pass just records the error so the Supervisor
    # could, in future, re-plan.
    if state.get("error") and state.get("retry_count", 0) > 0:
        return {
            "plan": state.get("plan", []) + [
                f"retry {state.get('retry_count')} after error: {state['error'][:100]}"
            ],
        }

    # ---- Empty query ----
    if not query:
        return {
            "intent": "clarification",
            "response": "Could you tell me what you'd like to analyze or change?",
        }

    # ---- LLM classification (preferred) ----
    if is_llm_available():
        try:
            raw = chat(
                messages=[{"role": "user", "content": CLASSIFY_PROMPT.format(query=query)}],
                temperature=0,
                json_mode=True,
                fast=True,                    # cheap + fast model
                max_tokens=120,
            )
            parsed = json.loads(raw)
            intent = parsed.get("intent", "").strip()
            reason = parsed.get("reason", "")
            if intent in VALID_INTENTS:
                return {
                    "intent": intent,
                    "plan": [f"classified as {intent}: {reason}"],
                }
            # Invalid label — fall through to rule fallback
        except Exception as e:
            print(f"[supervisor] LLM classification failed ({e}); using rule fallback.")

    # ---- Rule-based fallback ----
    intent = _fallback_classify(query)
    return {
        "intent": intent,
        "plan": [f"rule-classified as {intent}"],
    }