"""
Supervisor Agent (Router) — STUB
=================================
Classifies the user's intent and dispatches to the right downstream agent.

This is a stub: real intent classification will call the LLM in Step 4.
For now it does rule-based keyword matching so the graph can be smoke-tested
end-to-end before any LLM is wired up.
"""

from __future__ import annotations

from app.state import AutoInsightState


# Keyword tables used by the stub classifier
ML_FORECAST_KW  = {"forecast", "predict", "next quarter", "next month", "projection"}
ML_CLUSTER_KW   = {"cluster", "segment", "group customers", "customer tiers"}
ML_ANOMALY_KW   = {"anomal", "outlier", "unusual", "suspicious", "flag"}
SQL_WRITE_KW    = {"insert", "update", "delete", "add new", "remove", "modify",
                   "change the", "mark as"}
# Everything else that reads data is sql_read (default for substantive questions)


def supervisor_node(state: AutoInsightState) -> dict:
    """
    STUB implementation.

    Reads state["user_query"], classifies it, returns an updated intent.
    If retry_count > 0, the Supervisor also sees state["error"] and
    could rewrite the plan — real logic lives in Step 4.
    """
    query = (state.get("user_query") or "").lower().strip()

    # Error-retry path: Supervisor acknowledges and re-dispatches
    if state.get("error") and state.get("retry_count", 0) > 0:
        # Keep whatever intent was set — real logic would refine the plan here
        return {
            "plan": state.get("plan", []) + [f"retry after error: {state['error'][:80]}"],
        }

    # Empty query → clarification
    if not query:
        return {
            "intent": "clarification",
            "response": "Could you tell me what you'd like to analyze?",
        }

    # ML intents (checked first — more specific)
    if any(kw in query for kw in ML_FORECAST_KW):
        return {"intent": "ml_forecast", "plan": ["run time-series forecast"]}

    if any(kw in query for kw in ML_CLUSTER_KW):
        return {"intent": "ml_cluster", "plan": ["run K-Means clustering"]}

    if any(kw in query for kw in ML_ANOMALY_KW):
        return {"intent": "ml_anomaly", "plan": ["run anomaly detection"]}

    # SQL write — needs approval
    if any(kw in query for kw in SQL_WRITE_KW):
        return {
            "intent": "sql_write",
            "plan": ["generate SQL", "preview", "request approval", "execute"],
        }

    # Default: analytical read
    return {
        "intent": "sql_read",
        "plan": ["generate SQL", "execute", "narrate result"],
    }
