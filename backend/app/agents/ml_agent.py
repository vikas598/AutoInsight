"""
AutoInsight — ML Analytics Agent
==================================
Orchestrates one of three deterministic ML techniques for the dealership:

    ml_forecast  → run_forecast (SARIMA → ARIMA fallback)
    ml_cluster   → run_clustering (K-Means + silhouette)
    ml_anomaly   → run_anomaly_detection (Isolation Forest)

LLM boundary (strict):
    * Intent parsing — upstream in the Supervisor
    * Narrative generation — this file, after the deterministic result

    * Model selection, feature engineering, training, validation, execution
      — all deterministic code in services/ml_service.py

The agent catches ML service exceptions and routes to the retry path via
_fail() so the Supervisor can re-plan (or give up after MAX_RETRIES).
"""

from __future__ import annotations

import re

from app.llm import chat, is_llm_available
from app.services.ml_data_fetcher import (
    fetch_customer_features,
    fetch_monthly_sales,
    fetch_sales_features,
)
from app.services.ml_service import (
    run_anomaly_detection,
    run_clustering,
    run_forecast,
)
from app.state import AutoInsightState


# ===========================================================================
# Narration prompts
# ===========================================================================
FORECAST_NARRATIVE_PROMPT = """You are a business analyst for an automobile dealership. A time-series forecast just completed. Write a 2-3 sentence summary in plain English.

User asked: {user_query}

Model used: {model}
In-sample RMSE: {rmse:.1f}
Training points: {n_training}

Last 6 months of actual sales:
{historical_tail}

Forecast for the next {horizon} months:
{forecast}

Call out: (1) the overall trend direction, (2) any obvious seasonal spike in the forecast window, (3) the predicted range for the first month ahead. Format numbers in Indian conventions where sensible. Do NOT describe the model."""


CLUSTER_NARRATIVE_PROMPT = """You are a business analyst for an automobile dealership. A customer segmentation clustering just completed. Write a 2-3 sentence summary.

User asked: {user_query}

Optimal k = {k}  (silhouette score {silhouette:.2f}, closer to 1 is better)
Clustered {n_records} customers.

Cluster sizes:
{sizes}

Cluster centroids (average feature values per cluster):
{centroids}

Describe each cluster in business terms — e.g. 'budget first-time buyers', 'premium repeat customers'. Reference the actual centroid numbers. Format money as Indian Rupees using lakh/crore for large sums (₹1.5 lakh, ₹2.3 crore)."""


ANOMALY_NARRATIVE_PROMPT = """You are a business analyst for an automobile dealership. An Isolation Forest anomaly detection just ran on sales transactions. Write a 2-3 sentence summary.

User asked: {user_query}

Flagged {anomaly_count} of {total_records} records as anomalous (contamination parameter {contamination:.0%}).

Most anomalous transactions (first 5, lowest score = most unusual):
{top_anomalies}

State the count, then call out what makes the top offenders unusual (unusually low sale_price for the listed_price, extreme discount_pct, etc.). Format money as Indian Rupees. Suggest these be reviewed by the finance team."""


# ===========================================================================
# Entry point — LangGraph node
# ===========================================================================
def ml_agent_node(state: AutoInsightState) -> dict:
    """Dispatch on intent."""
    intent = state.get("intent")

    if intent == "ml_forecast":
        return _handle_forecast(state)
    if intent == "ml_cluster":
        return _handle_cluster(state)
    if intent == "ml_anomaly":
        return _handle_anomaly(state)

    return {
        "error": f"ml_agent called with unexpected intent: {intent}",
        "retry_count": state.get("retry_count", 0) + 1,
    }


# ===========================================================================
# ml_forecast
# ===========================================================================
def _handle_forecast(state: AutoInsightState) -> dict:
    user_query = state.get("user_query", "")

    horizon = _parse_horizon(user_query)
    metric = _parse_forecast_metric(user_query)

    try:
        df = fetch_monthly_sales(metric=metric)
        result = run_forecast(df, horizon=horizon)
    except Exception as e:
        return _fail(state, f"Forecast failed: {e}")

    narrative = _narrate_forecast(user_query, result)

    return {
        "ml_result": {
            "technique": "forecast",
            "summary": {
                "model":          result["model"],
                "metric":         metric,
                "horizon_months": result["horizon"],
                "rmse":           result["rmse_in_sample"],
                "n_training":     result["n_training"],
            },
            "chart_data": _build_forecast_chart_data(result),
            "metrics": {"rmse_in_sample": result["rmse_in_sample"]},
        },
        "response": narrative,
        "error": None,
    }


# ===========================================================================
# ml_cluster
# ===========================================================================
def _handle_cluster(state: AutoInsightState) -> dict:
    user_query = state.get("user_query", "")

    feature_cols = ["num_purchases", "total_spend", "avg_sale_price"]

    try:
        df = fetch_customer_features()
        result = run_clustering(df, feature_cols)
    except Exception as e:
        return _fail(state, f"Clustering failed: {e}")

    narrative = _narrate_cluster(user_query, result)

    # Build chart-friendly data: one row per cluster with its centroid + size
    chart_data = [
        {
            "cluster": c["cluster"],
            "size":    c["size"],
            **next(
                cc["features"] for cc in result["cluster_centroids"]
                if cc["cluster"] == c["cluster"]
            ),
        }
        for c in result["cluster_sizes"]
    ]

    return {
        "ml_result": {
            "technique": "cluster",
            "summary": {
                "k":                result["optimal_k"],
                "silhouette_score": result["silhouette_score"],
                "n_customers":      result["n_records"],
                "all_scores":       result["all_scores"],
            },
            "chart_data": chart_data,
            "metrics": {"silhouette": result["silhouette_score"]},
        },
        "response": narrative,
        "error": None,
    }


# ===========================================================================
# ml_anomaly
# ===========================================================================
def _handle_anomaly(state: AutoInsightState) -> dict:
    user_query = state.get("user_query", "")

    feature_cols = ["sale_price", "discount", "discount_pct",
                    "listed_price", "cost_price"]

    try:
        df = fetch_sales_features()
        result = run_anomaly_detection(df, feature_cols)
    except Exception as e:
        return _fail(state, f"Anomaly detection failed: {e}")

    narrative = _narrate_anomaly(user_query, result)

    chart_data = [
        {
            "sale_id":       a["label"],
            "sale_price":    a["features"]["sale_price"],
            "discount_pct":  a["features"]["discount_pct"],
            "listed_price":  a["features"]["listed_price"],
            # All model features, so a reviewer can see why a sale stood out
            "discount":      a["features"]["discount"],
            "cost_price":    a["features"]["cost_price"],
            "score":         a["score"],
        }
        for a in result["anomalies"]
    ]

    return {
        "ml_result": {
            "technique": "anomaly",
            "summary": {
                "contamination":   result["contamination"],
                "anomalies_found": result["anomaly_count"],
                "total_records":   result["total_records"],
            },
            "chart_data": chart_data,
            "metrics": {"anomaly_rate": result["anomaly_rate"]},
        },
        "response": narrative,
        "error": None,
    }


# ===========================================================================
# Query parsing helpers (deterministic — no LLM)
# ===========================================================================
def _parse_horizon(query: str) -> int:
    """Extract forecast horizon in months from the user's query."""
    q = query.lower()
    m = re.search(r"(\d+)\s*month", q)
    if m:
        return max(1, min(12, int(m.group(1))))
    m = re.search(r"(\d+)\s*quarter", q)
    if m:
        return max(1, min(12, int(m.group(1)) * 3))
    if "quarter" in q:
        return 3
    if "year" in q:
        return 12
    return 3   # default


def _parse_forecast_metric(query: str) -> str:
    q = query.lower()
    if any(w in q for w in ("revenue", "rupees", "₹", "value", "turnover")):
        return "revenue"
    return "count"


# ===========================================================================
# Narration (LLM calls — the only ones in this agent)
# ===========================================================================
def _narrate_forecast(user_query: str, result: dict) -> str:
    if not is_llm_available():
        return _simple_forecast(result)

    historical_tail = "\n".join(
        f"  {h['month']}: {h['value']:.0f}"
        for h in result["historical"][-6:]
    )
    forecast_str = "\n".join(
        f"  {f['month']}: {f['forecast']:.1f}  (80% CI {f['lower']:.1f} to {f['upper']:.1f})"
        for f in result["forecast"]
    )

    try:
        reply = chat(
            messages=[{
                "role": "user",
                "content": FORECAST_NARRATIVE_PROMPT.format(
                    user_query=user_query,
                    model=result["model"],
                    rmse=result["rmse_in_sample"],
                    n_training=result["n_training"],
                    horizon=result["horizon"],
                    historical_tail=historical_tail,
                    forecast=forecast_str,
                ),
            }],
            temperature=0.3,
            max_tokens=300,
        )
        return reply.strip() or _simple_forecast(result)
    except Exception:
        return _simple_forecast(result)


def _narrate_cluster(user_query: str, result: dict) -> str:
    if not is_llm_available():
        return _simple_cluster(result)

    sizes = ", ".join(
        f"cluster {c['cluster']}: {c['size']}"
        for c in result["cluster_sizes"]
    )
    centroids = "\n".join(
        f"  cluster {cc['cluster']}: " + ", ".join(
            f"{k}={v:,.0f}" for k, v in cc["features"].items()
        )
        for cc in result["cluster_centroids"]
    )

    try:
        reply = chat(
            messages=[{
                "role": "user",
                "content": CLUSTER_NARRATIVE_PROMPT.format(
                    user_query=user_query,
                    k=result["optimal_k"],
                    silhouette=result["silhouette_score"],
                    n_records=result["n_records"],
                    sizes=sizes,
                    centroids=centroids,
                ),
            }],
            temperature=0.3,
            max_tokens=300,
        )
        return reply.strip() or _simple_cluster(result)
    except Exception:
        return _simple_cluster(result)


def _narrate_anomaly(user_query: str, result: dict) -> str:
    if not is_llm_available():
        return _simple_anomaly(result)

    top5 = result["anomalies"][:5]
    top_str = "\n".join(
        f"  sale_id={a['label']}, " + ", ".join(
            f"{k}={v:,.2f}" for k, v in a["features"].items()
        ) + f", score={a['score']:.3f}"
        for a in top5
    )

    try:
        reply = chat(
            messages=[{
                "role": "user",
                "content": ANOMALY_NARRATIVE_PROMPT.format(
                    user_query=user_query,
                    anomaly_count=result["anomaly_count"],
                    total_records=result["total_records"],
                    contamination=result["contamination"],
                    top_anomalies=top_str,
                ),
            }],
            temperature=0.3,
            max_tokens=300,
        )
        return reply.strip() or _simple_anomaly(result)
    except Exception:
        return _simple_anomaly(result)


# ---- Fallback narratives when LLM unavailable ----
def _simple_forecast(r: dict) -> str:
    f0 = r["forecast"][0] if r["forecast"] else None
    if f0:
        return (f"Forecasted {r['horizon']} months via {r['model']}. "
                f"Next month: {f0['forecast']:.1f} (range {f0['lower']:.1f}–{f0['upper']:.1f}).")
    return f"Forecasted {r['horizon']} months via {r['model']}."


def _simple_cluster(r: dict) -> str:
    return (f"Clustered {r['n_records']} customers into {r['optimal_k']} groups "
            f"(silhouette={r['silhouette_score']:.2f}).")


def _simple_anomaly(r: dict) -> str:
    return (f"Flagged {r['anomaly_count']} anomalies out of {r['total_records']} records "
            f"({r['anomaly_rate']:.1%}).")


# ===========================================================================
# Forecast chart data builder
# ===========================================================================
def _build_forecast_chart_data(result: dict) -> list[dict]:
    """One continuous series: 'actual' for historical, 'forecast' + CI for future."""
    chart: list[dict] = []
    for h in result["historical"]:
        chart.append({
            "month":    h["month"],
            "actual":   h["value"],
            "forecast": None,
            "lower":    None,
            "upper":    None,
        })
    for f in result["forecast"]:
        chart.append({
            "month":    f["month"],
            "actual":   None,
            "forecast": f["forecast"],
            "lower":    f["lower"],
            "upper":    f["upper"],
        })
    return chart


# ===========================================================================
# Helpers
# ===========================================================================
def _fail(state: AutoInsightState, msg: str) -> dict:
    return {
        "error":       msg,
        "retry_count": state.get("retry_count", 0) + 1,
        "response":    f"ML analysis failed: {msg}",
    }
