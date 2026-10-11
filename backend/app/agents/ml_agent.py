"""
ML Analytics Agent — STUB
==========================
Runs one of three deterministic ML techniques against the dealership data:
  * ml_forecast → SARIMA with Prophet fallback
  * ml_cluster  → K-Means (k chosen by silhouette)
  * ml_anomaly  → Isolation Forest

LLM boundary (strict): LLM handles intent parsing (upstream in Supervisor) and
narrative generation only. Model selection, feature engineering, training,
validation, and execution are deterministic code (Step 7).

This stub returns canned result shapes so the graph can be smoke-tested.
"""

from __future__ import annotations

from app.state import AutoInsightState


def ml_agent_node(state: AutoInsightState) -> dict:
    intent = state.get("intent")

    if intent == "ml_forecast":
        return _stub_forecast(state)
    if intent == "ml_cluster":
        return _stub_cluster(state)
    if intent == "ml_anomaly":
        return _stub_anomaly(state)

    return {
        "error": f"ml_agent called with unexpected intent: {intent}",
        "retry_count": state.get("retry_count", 0) + 1,
    }


def _stub_forecast(state: AutoInsightState) -> dict:
    return {
        "ml_result": {
            "technique": "forecast",
            "summary": {
                "model": "SARIMA(1,1,1)(1,1,1,12)",
                "horizon_months": 3,
                "mape": 8.4,
            },
            "chart_data": [
                {"month": "2025-01", "actual": None,  "forecast": 48, "lower": 41, "upper": 55},
                {"month": "2025-02", "actual": None,  "forecast": 52, "lower": 44, "upper": 60},
                {"month": "2025-03", "actual": None,  "forecast": 89, "lower": 78, "upper": 100},
            ],
            "metrics": {"mape": 8.4, "rmse": 4.2},
        },
        "response": "[STUB] 3-month sales forecast ready. March spike predicted (~89 units).",
        "error": None,
    }


def _stub_cluster(state: AutoInsightState) -> dict:
    return {
        "ml_result": {
            "technique": "cluster",
            "summary": {
                "k": 3,
                "silhouette_score": 0.62,
                "cluster_labels": ["Budget", "Mid-tier", "Premium"],
            },
            "chart_data": [
                {"cluster": "Budget",    "avg_spend":  620000, "count": 298},
                {"cluster": "Mid-tier",  "avg_spend": 1250000, "count": 152},
                {"cluster": "Premium",   "avg_spend": 2850000, "count":  50},
            ],
            "metrics": {"silhouette": 0.62, "n_customers": 500},
        },
        "response": "[STUB] Found 3 customer clusters (silhouette=0.62).",
        "error": None,
    }


def _stub_anomaly(state: AutoInsightState) -> dict:
    return {
        "ml_result": {
            "technique": "anomaly",
            "summary": {
                "contamination": 0.05,
                "anomalies_found": 7,
                "total_records": 800,
            },
            "chart_data": [
                {"sale_id": 123, "sale_price":       1.00, "score": -0.42},
                {"sale_id": 456, "sale_price":  300000.00, "score": -0.38},
                {"sale_id": 789, "sale_price": 4800000.00, "score": -0.35},
            ],
            "metrics": {"anomaly_rate": 0.00875},
        },
        "response": "[STUB] Detected 7 anomalous transactions in 800 sales.",
        "error": None,
    }
