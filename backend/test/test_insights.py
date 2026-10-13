"""
AutoInsight — Test for the Insights & Forecasts API contract
=============================================================
Sends the three questions the Insights page uses through POST /api/chat
(the real graph: Supervisor -> ML agent -> narration) and checks that:

  * each is routed to the intended ML intent,
  * the response carries `ml_result` (technique, summary, metrics),
  * every returned number equals a direct, deterministic call to
    ml_service with the same inputs (all models use random_state=42),
  * chart_config uses the expected x / y fields,
  * anomaly rows carry every model feature.

Requires a configured LLM (classification + narration) and the database.
Read-only: ML analyses never write.

Run from backend/:
    python test/test_insights.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from fastapi.testclient import TestClient

from app.api.main import app
from app.services.ml_data_fetcher import (
    fetch_customer_features,
    fetch_monthly_sales,
    fetch_sales_features,
)
from app.services.ml_service import run_anomaly_detection, run_clustering, run_forecast

BAR = "=" * 72
failures: list[str] = []
client = TestClient(app)


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{' - ' + detail if detail else ''}")
    if not ok:
        failures.append(name)


def close(a, b, tol=1e-6) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) <= tol * max(1.0, abs(float(b)))


def ask(q: str) -> dict:
    r = client.post("/api/chat", json={"session_id": None, "user_query": q})
    assert r.status_code == 200, r.text
    return r.json()


def test_forecast(metric: str, horizon: int, question: str) -> None:
    print(f"\nForecast ({metric}, {horizon} months): {question!r}")
    res = ask(question)
    ml = res.get("ml_result") or {}
    check("intent ml_forecast", res["intent"] == "ml_forecast", str(res["intent"]))
    check("status complete", res["status"] == "complete", res.get("error") or "")
    check("technique forecast", ml.get("technique") == "forecast")
    s = ml.get("summary", {})
    check("metric parsed from question", s.get("metric") == metric, str(s.get("metric")))
    check("horizon parsed from question", s.get("horizon_months") == horizon, str(s.get("horizon_months")))

    ref = run_forecast(fetch_monthly_sales(metric=metric), horizon=horizon)
    check("model matches direct run", s.get("model") == ref["model"], s.get("model", ""))
    check("rmse matches direct run", close(s.get("rmse"), ref["rmse_in_sample"]), f"{s.get('rmse')}")
    check("n_training matches", s.get("n_training") == ref["n_training"], str(s.get("n_training")))

    cc = res["chart_config"]
    check("chart forecast_line on month", cc["chart_type"] == "forecast_line" and cc["x_key"] == "month")
    future = [r for r in cc["data"] if r["forecast"] is not None]
    hist = [r for r in cc["data"] if r["actual"] is not None]
    check("chart has horizon future points", len(future) == horizon)
    check("chart history length", len(hist) == ref["n_training"])
    check("forecast values match", all(
        close(a["forecast"], b["forecast"]) and close(a["lower"], b["lower"]) and close(a["upper"], b["upper"])
        and a["month"] == b["month"] for a, b in zip(future, ref["forecast"])))
    neg = [r["month"] for r in future if r["lower"] < 0 or r["forecast"] < 0]
    print(f"  [INFO] months with a negative forecast or lower bound: {neg or 'none'}")


def test_clusters() -> None:
    print("\nSegmentation")
    res = ask("Segment customers by spending behavior.")
    ml = res.get("ml_result") or {}
    check("intent ml_cluster", res["intent"] == "ml_cluster", str(res["intent"]))
    check("technique cluster", ml.get("technique") == "cluster")
    s = ml.get("summary", {})

    ref = run_clustering(fetch_customer_features(), ["num_purchases", "total_spend", "avg_sale_price"])
    check("k matches", s.get("k") == ref["optimal_k"], str(s.get("k")))
    check("silhouette matches", close(s.get("silhouette_score"), ref["silhouette_score"]), f"{s.get('silhouette_score'):.4f}")
    check("n_customers matches", s.get("n_customers") == ref["n_records"], str(s.get("n_customers")))
    scores = {int(k): v for k, v in (s.get("all_scores") or {}).items()}
    check("all_scores returned for k=2..8", sorted(scores) == list(range(2, 9)), str(sorted(scores)))

    cc = res["chart_config"]
    check("chart scatter total_spend x num_purchases",
          cc["chart_type"] == "scatter" and cc["x_key"] == "total_spend" and cc["y_keys"] == ["num_purchases"])
    sizes = {r["cluster"]: r["size"] for r in cc["data"]}
    check("cluster sizes match", sizes == {c["cluster"]: c["size"] for c in ref["cluster_sizes"]})
    check("sizes sum to customers", sum(sizes.values()) == ref["n_records"])


def test_anomalies() -> None:
    print("\nAnomalies")
    res = ask("Find unusual sales transactions.")
    ml = res.get("ml_result") or {}
    check("intent ml_anomaly", res["intent"] == "ml_anomaly", str(res["intent"]))
    check("technique anomaly", ml.get("technique") == "anomaly")
    s = ml.get("summary", {})

    cols = ["sale_price", "discount", "discount_pct", "listed_price", "cost_price"]
    ref = run_anomaly_detection(fetch_sales_features(), cols)
    check("anomalies_found matches", s.get("anomalies_found") == ref["anomaly_count"], str(s.get("anomalies_found")))
    check("total_records matches", s.get("total_records") == ref["total_records"], str(s.get("total_records")))
    check("contamination matches", close(s.get("contamination"), ref["contamination"]))

    cc = res["chart_config"]
    check("chart scatter sale_price x discount_pct",
          cc["chart_type"] == "scatter" and cc["x_key"] == "sale_price" and cc["y_keys"] == ["discount_pct"])
    row = cc["data"][0]
    check("rows carry every model feature", all(c in row for c in cols) and "score" in row and "sale_id" in row, str(sorted(row)))
    check("rows match direct run (ids, scores)", [(r["sale_id"], round(r["score"], 9)) for r in cc["data"]]
          == [(a["label"], round(a["score"], 9)) for a in ref["anomalies"]])


def main() -> int:
    print(BAR, "\nInsights & Forecasts - /api/chat ML contract\n", BAR, sep="")
    test_forecast("count", 3, "Forecast the number of sales for the next 3 months.")
    test_forecast("revenue", 6, "Forecast sales revenue for the next 6 months.")
    test_clusters()
    test_anomalies()

    print("\nNon-ML response keeps ml_result empty")
    res = ask("How many sales did we make in 2024?")
    check("sql_read has ml_result null", res.get("ml_result") is None, str(res.get("intent")))

    print("\n" + BAR)
    print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
