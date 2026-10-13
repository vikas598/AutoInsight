"""
AutoInsight — ML Service  (deterministic ML functions)
=======================================================
Three techniques, all with hard-coded guard rails:

    run_forecast       SARIMA(1,1,1)(1,1,1,12) with ARIMA(1,1,1) fallback
                       requires ≥24 monthly points
    run_clustering     K-Means with silhouette-optimal k in [k_min, k_max]
                       requires ≥100 records
    run_anomaly_detection
                       Isolation Forest, contamination=0.05
                       requires ≥50 records

All return values are converted to Python-native types (int, float, str) so
LangGraph's MemorySaver (msgpack-based) can serialize them.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler


# ===========================================================================
# Numpy → Python-native coercion  (fixes msgpack serialization)
# ===========================================================================
def _native(v: Any) -> Any:
    """Convert any numpy scalar to its Python equivalent."""
    if hasattr(v, "item"):      # numpy scalars have .item()
        return v.item()
    return v


# ===========================================================================
# FORECAST — SARIMA with ARIMA fallback
# ===========================================================================
MIN_FORECAST_POINTS = 24


def run_forecast(df_monthly: pd.DataFrame, horizon: int = 3) -> dict[str, Any]:
    if len(df_monthly) < MIN_FORECAST_POINTS:
        raise ValueError(
            f"Forecast needs ≥{MIN_FORECAST_POINTS} monthly points, got {len(df_monthly)}"
        )

    try:
        from statsmodels.tsa.statespace.sarimax import SARIMAX
        from statsmodels.tsa.arima.model import ARIMA
    except ImportError as e:
        raise RuntimeError(
            "statsmodels not installed — run: pip install statsmodels"
        ) from e

    series = df_monthly.set_index("month")["value"].astype(float)

    model_name: str
    try:
        fit = SARIMAX(
            series,
            order=(1, 1, 1),
            seasonal_order=(1, 1, 1, 12),
            enforce_stationarity=False,
            enforce_invertibility=False,
        ).fit(disp=False)
        model_name = "SARIMA(1,1,1)(1,1,1,12)"
    except Exception:
        fit = ARIMA(series, order=(1, 1, 1)).fit()
        model_name = "ARIMA(1,1,1)"

    forecast_obj = fit.get_forecast(steps=horizon)
    forecast_mean = forecast_obj.predicted_mean
    conf = forecast_obj.conf_int(alpha=0.2)

    future_months = pd.date_range(
        start=series.index[-1] + pd.offsets.MonthBegin(1),
        periods=horizon,
        freq="MS",
    )

    predictions = fit.fittedvalues
    rmse = float(np.sqrt(((series - predictions) ** 2).mean()))

    return {
        "historical": [
            {"month": ts.strftime("%Y-%m"), "value": float(v)}
            for ts, v in series.items()
        ],
        "forecast": [
            {
                "month":    ts.strftime("%Y-%m"),
                "forecast": float(forecast_mean.iloc[i]),
                "lower":    float(conf.iloc[i, 0]),
                "upper":    float(conf.iloc[i, 1]),
            }
            for i, ts in enumerate(future_months)
        ],
        "model":          model_name,
        "rmse_in_sample": rmse,
        "horizon":        int(horizon),
        "n_training":     int(len(series)),
    }


# ===========================================================================
# CLUSTERING — K-Means with silhouette optimization
# ===========================================================================
MIN_CLUSTER_RECORDS = 100


def run_clustering(
    df: pd.DataFrame,
    feature_cols: list[str],
    k_min: int = 2,
    k_max: int = 8,
) -> dict[str, Any]:
    if len(df) < MIN_CLUSTER_RECORDS:
        raise ValueError(
            f"Clustering needs ≥{MIN_CLUSTER_RECORDS} records, got {len(df)}"
        )

    X = df[feature_cols].values.astype(float)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    all_scores: dict[int, float] = {}
    best_k = k_min
    best_score = -1.0

    for k in range(k_min, k_max + 1):
        if k >= len(df):
            break
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(X_scaled)
        score = float(silhouette_score(X_scaled, labels))
        all_scores[int(k)] = score
        if score > best_score:
            best_score = score
            best_k = k

    km = KMeans(n_clusters=best_k, random_state=42, n_init=10)
    labels = km.fit_predict(X_scaled)
    centroids = scaler.inverse_transform(km.cluster_centers_)

    sizes = pd.Series(labels).value_counts().sort_index()

    return {
        "optimal_k":         int(best_k),
        "silhouette_score":  float(best_score),
        "all_scores":        all_scores,
        "cluster_sizes":     [
            {"cluster": int(c), "size": int(s)} for c, s in sizes.items()
        ],
        "cluster_centroids": [
            {
                "cluster":  int(c),
                "features": {
                    feat: float(centroids[c][i])
                    for i, feat in enumerate(feature_cols)
                },
            }
            for c in range(best_k)
        ],
        "assignments":       [
            {"label": _native(lbl), "cluster": int(cl)}
            for lbl, cl in zip(df["label"].tolist(), labels.tolist())
        ],
        "n_records":         int(len(df)),
        "feature_cols":      feature_cols,
    }


# ===========================================================================
# ANOMALY DETECTION — Isolation Forest
# ===========================================================================
MIN_ANOMALY_RECORDS = 50
DEFAULT_CONTAMINATION = 0.05


def run_anomaly_detection(
    df: pd.DataFrame,
    feature_cols: list[str],
    contamination: float = DEFAULT_CONTAMINATION,
) -> dict[str, Any]:
    if len(df) < MIN_ANOMALY_RECORDS:
        raise ValueError(
            f"Anomaly detection needs ≥{MIN_ANOMALY_RECORDS} records, got {len(df)}"
        )

    X = df[feature_cols].values.astype(float)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = IsolationForest(
        contamination=contamination,
        random_state=42,
        n_estimators=100,
    )
    predictions = model.fit_predict(X_scaled)
    scores = model.score_samples(X_scaled)

    # ---- Convert label column to Python-native once (fixes msgpack issue) ----
    labels_list = [_native(x) for x in df["label"].tolist()]
    feature_lists = {feat: df[feat].astype(float).tolist() for feat in feature_cols}

    anomalies = []
    for i, (pred, score) in enumerate(zip(predictions, scores)):
        if pred == -1:
            anomalies.append({
                "label":    labels_list[i],
                "features": {feat: feature_lists[feat][i] for feat in feature_cols},
                "score":    float(score),
            })

    anomalies.sort(key=lambda a: a["score"])

    return {
        "contamination":  float(contamination),
        "anomaly_count":  int(len(anomalies)),
        "total_records":  int(len(df)),
        "anomaly_rate":   float(len(anomalies) / len(df)) if len(df) else 0.0,
        "anomalies":      anomalies,
        "feature_cols":   feature_cols,
    }