"""
AutoInsight — ML Data Fetchers
================================
Deterministic SQL queries that produce feature DataFrames for the ML service.
Keeps all data-fetching logic out of the ml_agent so the agent is purely
orchestration + narration.

All queries use the READ engine (never writer).
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from app.db import get_connection_manager


# ---------------------------------------------------------------------------
# Forecast — monthly aggregated sales count
# ---------------------------------------------------------------------------
def fetch_monthly_sales(metric: str = "count") -> pd.DataFrame:
    """
    Return a DataFrame with monthly aggregated sales for forecasting.

    Args:
        metric: "count"  — number of sales per month (default)
                "revenue" — SUM(sale_price) per month

    Returns:
        columns: month (datetime, month-start), value (float)
    """
    agg = "COUNT(*)" if metric == "count" else "COALESCE(SUM(sale_price), 0)"
    sql = f"""
        SELECT
            DATE_TRUNC('month', sale_date)::date AS month,
            {agg}::float AS value
        FROM sales
        GROUP BY DATE_TRUNC('month', sale_date)
        ORDER BY month
    """
    engine = get_connection_manager().read_engine
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    df["month"] = pd.to_datetime(df["month"])
    return df


# ---------------------------------------------------------------------------
# Clustering — customer-level features
# ---------------------------------------------------------------------------
def fetch_customer_features() -> pd.DataFrame:
    """
    Return a DataFrame of customer features for clustering.

    Only customers with at least one purchase are included (otherwise the
    clustering collapses most of them into a zero-spend cluster).

    Returns:
        columns: label (customer id), num_purchases, total_spend, avg_sale_price
    """
    sql = """
        SELECT
            c.id                                      AS label,
            COUNT(s.id)                               AS num_purchases,
            COALESCE(SUM(s.sale_price), 0)::float     AS total_spend,
            COALESCE(AVG(s.sale_price), 0)::float     AS avg_sale_price
        FROM customers c
        JOIN sales s ON s.customer_id = c.id
        GROUP BY c.id
        HAVING COUNT(s.id) > 0
    """
    engine = get_connection_manager().read_engine
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    return df


# ---------------------------------------------------------------------------
# Anomaly detection — per-sale features
# ---------------------------------------------------------------------------
def fetch_sales_features() -> pd.DataFrame:
    """
    Return a DataFrame of per-sale features for anomaly detection.

    discount_pct is the discount as a fraction of listed price — the single
    best feature for catching "sold 95% off" and similar anomalies.

    Returns:
        columns: label (sale id), sale_price, discount, discount_pct,
                 listed_price, cost_price
    """
    sql = """
        SELECT
            s.id                                                    AS label,
            s.sale_price::float                                     AS sale_price,
            s.discount::float                                       AS discount,
            CASE WHEN v.price > 0 THEN (s.discount / v.price)::float
                 ELSE 0 END                                         AS discount_pct,
            v.price::float                                          AS listed_price,
            v.cost_price::float                                     AS cost_price
        FROM sales s
        JOIN vehicles v ON v.id = s.vehicle_id
    """
    engine = get_connection_manager().read_engine
    with engine.connect() as conn:
        df = pd.read_sql(text(sql), conn)
    return df
