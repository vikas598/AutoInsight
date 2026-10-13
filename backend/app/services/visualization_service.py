"""
AutoInsight — Visualization Service
=====================================
Two outputs:

    1. CHART CONFIG — JSON ready for Recharts in the frontend.
       Rule-based chart-type picker (no LLM) that inspects the state's
       query_result or ml_result and decides line vs bar vs scatter vs KPI.

    2. PDF REPORT — ReportLab-based report builder that renders a session's
       queries, SQL, narratives, and embedded chart images into one shareable
       PDF for a dealership manager.

The frontend reads the chart config. The user can click "Export report" to
get a PDF built via build_pdf_report.

Dependencies:
    pip install reportlab matplotlib
"""

from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.state import AutoInsightState, QueryResult, VizConfig


# ===========================================================================
# Chart-type decision rules
# ===========================================================================
#
# For an SQL query_result, we look at (columns, rows) and apply these rules
# in order. First match wins:
#
#   1. row_count == 0                     → "empty"
#   2. 1 row and 1 numeric column          → "kpi"
#   3. First column looks like a date      → "line"      (time-series)
#   4. First column categorical,
#      has 1-2 numeric columns             → "bar"
#   5. First column categorical,
#      multi numeric columns               → "grouped_bar"
#   6. Anything else                       → "table"
#
# For an ML result, we switch on `technique`:
#
#   forecast  → "forecast_line"  (actual + forecast + CI band)
#   cluster   → "scatter"        (first two centroid features)
#   anomaly   → "scatter"        (sale_price vs discount_pct)
#


# Column names that look like dates/times
_DATE_LIKE_NAMES = {"month", "date", "day", "year", "quarter", "week",
                    "created_at", "sale_date", "service_date", "expense_date",
                    "logged_at", "updated_at", "hire_date"}

# Column names that are likely identifiers (not interesting to plot)
_ID_LIKE_NAMES = {"id", "pk", "uuid"}


def _is_datelike(col_name: str, sample_value: Any) -> bool:
    name = col_name.lower()
    if any(name == dn or name.endswith("_" + dn) or name.startswith(dn + "_")
           for dn in _DATE_LIKE_NAMES):
        return True
    # String that looks like YYYY-MM-DD or YYYY-MM
    if isinstance(sample_value, str):
        if re.match(r"^\d{4}-\d{2}(-\d{2})?$", sample_value):
            return True
    return False


def _is_numeric(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _detect_sql_chart(result: QueryResult) -> VizConfig:
    """Rule-based chart picker for an SQL query_result."""
    columns = result.get("columns") or []
    rows = result.get("rows") or []
    row_count = result.get("row_count", 0)

    if row_count == 0 or not columns or not rows:
        return VizConfig(chart_type="table", data=[], x_key="", y_keys=[], title="No results")

    # Convert rows to list of dicts for Recharts
    records = [dict(zip(columns, r)) for r in rows]

    # Numeric columns
    numeric_cols = [c for c in columns if _is_numeric(rows[0][columns.index(c)])]

    # ---- Rule 2: single-row single-value → KPI tile ----
    if row_count == 1 and len(numeric_cols) == 1 and len(columns) == 1:
        return VizConfig(
            chart_type="kpi",
            data=records,
            x_key=columns[0],
            y_keys=numeric_cols,
            title=columns[0].replace("_", " ").title(),
        )

    # ---- Rule 3: time-series ----
    if _is_datelike(columns[0], rows[0][0]) and numeric_cols:
        return VizConfig(
            chart_type="line",
            data=records,
            x_key=columns[0],
            y_keys=numeric_cols,
            title=f"{', '.join(numeric_cols)} over {columns[0]}",
        )

    # ---- Rule 4+5: categorical first column + numeric ----
    first_is_cat = not _is_numeric(rows[0][0]) and not _is_datelike(columns[0], rows[0][0])
    if first_is_cat and numeric_cols:
        chart_type = "bar" if len(numeric_cols) == 1 else "grouped_bar"
        return VizConfig(
            chart_type=chart_type,
            data=records,
            x_key=columns[0],
            y_keys=numeric_cols,
            title=f"{', '.join(numeric_cols)} by {columns[0]}",
        )

    # ---- Rule 6: fallback to table ----
    return VizConfig(
        chart_type="table",
        data=records,
        x_key=columns[0],
        y_keys=[c for c in columns if c != columns[0]],
        title=", ".join(columns),
    )


def _detect_ml_chart(ml_result: dict) -> VizConfig:
    """Chart picker for ML results — switch on technique."""
    technique = ml_result.get("technique", "")
    chart_data = ml_result.get("chart_data") or []

    if technique == "forecast":
        return VizConfig(
            chart_type="forecast_line",
            data=chart_data,
            x_key="month",
            y_keys=["actual", "forecast", "lower", "upper"],
            title="Sales forecast",
        )

    if technique == "cluster":
        return VizConfig(
            chart_type="scatter",
            data=chart_data,
            x_key="total_spend",
            y_keys=["num_purchases"],
            title=f"Customer clusters (k={ml_result.get('summary', {}).get('k', '?')})",
        )

    if technique == "anomaly":
        return VizConfig(
            chart_type="scatter",
            data=chart_data,
            x_key="sale_price",
            y_keys=["discount_pct"],
            title=f"Anomalous transactions ({ml_result.get('summary', {}).get('anomalies_found', 0)} flagged)",
        )

    return VizConfig(chart_type="table", data=chart_data, x_key="", y_keys=[], title="ML result")


# ===========================================================================
# Public — chart config generation
# ===========================================================================
def generate_chart_config(state: AutoInsightState) -> VizConfig:
    """
    Decide a chart config for the current state. Order of precedence:

        1. ml_result present      → ML chart (forecast/cluster/anomaly)
        2. query_result has rows  → SQL chart
        3. nothing                → empty table
    """
    ml_result = state.get("ml_result") or {}
    if ml_result.get("technique"):
        return _detect_ml_chart(ml_result)

    query_result = state.get("query_result") or {}
    if query_result.get("rows"):
        return _detect_sql_chart(query_result)

    return VizConfig(chart_type="table", data=[], x_key="", y_keys=[], title="No result")


# ===========================================================================
# PDF Report Builder
# ===========================================================================
def _render_chart_png(viz: VizConfig) -> bytes | None:
    """
    Render a VizConfig as a PNG via matplotlib.

    Returns None if the chart type can't be rendered (empty, kpi — those
    show as text instead).
    """
    chart_type = viz.get("chart_type")
    data = viz.get("data") or []

    if chart_type in ("table", "empty", "kpi") or not data:
        return None

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    fig, ax = plt.subplots(figsize=(7, 3.5), dpi=120)
    x_key = viz.get("x_key", "")
    y_keys = viz.get("y_keys") or []

    try:
        if chart_type == "line":
            x = [d.get(x_key) for d in data]
            for yk in y_keys:
                y = [d.get(yk) for d in data]
                ax.plot(x, y, marker="o", label=yk, linewidth=2)

        elif chart_type == "forecast_line":
            months = [d.get("month") for d in data]
            actuals = [d.get("actual") for d in data]
            forecasts = [d.get("forecast") for d in data]
            lowers = [d.get("lower") for d in data]
            uppers = [d.get("upper") for d in data]
            ax.plot(months, actuals, marker="o", label="Actual", linewidth=2, color="#2563eb")
            ax.plot(months, forecasts, marker="s", label="Forecast", linewidth=2, color="#ef4444", linestyle="--")
            lb = [l if l is not None else None for l in lowers]
            ub = [u if u is not None else None for u in uppers]
            # Draw CI band where both exist
            ci_months = [m for m, l, u in zip(months, lb, ub) if l is not None and u is not None]
            ci_lower = [l for l in lb if l is not None]
            ci_upper = [u for u in ub if u is not None]
            if ci_months:
                ax.fill_between(ci_months, ci_lower, ci_upper, alpha=0.2, color="#ef4444", label="80% CI")

        elif chart_type in ("bar", "grouped_bar"):
            x_labels = [str(d.get(x_key)) for d in data]
            if chart_type == "bar" and y_keys:
                y = [d.get(y_keys[0]) for d in data]
                ax.bar(x_labels, y, color="#2563eb")
            else:
                import numpy as np
                xs = np.arange(len(x_labels))
                width = 0.8 / max(len(y_keys), 1)
                for i, yk in enumerate(y_keys):
                    y = [d.get(yk) for d in data]
                    ax.bar(xs + i * width, y, width=width, label=yk)
                ax.set_xticks(xs + width * (len(y_keys) - 1) / 2)
                ax.set_xticklabels(x_labels)

        elif chart_type == "scatter":
            if y_keys:
                x = [d.get(x_key) for d in data]
                y = [d.get(y_keys[0]) for d in data]
                ax.scatter(x, y, s=40, alpha=0.6, color="#ef4444")

        else:
            return None

        ax.set_title(viz.get("title", ""), fontsize=11)
        ax.set_xlabel(x_key)
        ax.grid(True, alpha=0.3)
        if y_keys and chart_type != "scatter":
            ax.legend(loc="best", fontsize=8)
        if chart_type in ("bar", "grouped_bar") and len(data) > 5:
            fig.autofmt_xdate(rotation=35)

        buf = io.BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format="png", bbox_inches="tight")
        plt.close(fig)
        return buf.getvalue()
    except Exception:
        plt.close(fig)
        return None


def build_pdf_report(
    sessions: list[dict[str, Any]],
    output_path: str | Path,
    *,
    title: str = "AutoInsight — Session Report",
) -> Path:
    """
    Build a PDF report from a list of session entries.

    Each entry is a dict with:
        - user_query   : str
        - response     : str          (narrative)
        - sql_query    : str (opt)    (shown if non-empty)
        - viz_config   : VizConfig    (used to render a chart)
        - row_count    : int (opt)    (shown in meta)
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak,
            Table, TableStyle,
        )
    except ImportError as e:
        raise RuntimeError("reportlab not installed — run: pip install reportlab") from e

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        title=title,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="SmallCode", parent=styles["Code"],
        fontSize=8, leading=10, backColor=colors.whitesmoke,
    ))
    styles.add(ParagraphStyle(
        name="SmallGrey", parent=styles["BodyText"],
        fontSize=9, textColor=colors.grey,
    ))

    story: list[Any] = []

    # Cover
    story.append(Paragraph(title, styles["Title"]))
    story.append(Paragraph(
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · "
        f"{len(sessions)} queries in this session",
        styles["SmallGrey"],
    ))
    story.append(Spacer(1, 8 * mm))

    # One section per session entry
    for idx, s in enumerate(sessions, start=1):
        story.append(Paragraph(
            f"<b>Q{idx}.</b> {_escape(s.get('user_query', '—'))}",
            styles["Heading3"],
        ))

        resp = s.get("response") or ""
        if resp:
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(_escape(resp), styles["BodyText"]))

        sql = s.get("sql_query") or ""
        if sql:
            story.append(Spacer(1, 3 * mm))
            story.append(Paragraph("<b>SQL</b>", styles["SmallGrey"]))
            story.append(Paragraph(_escape(sql), styles["SmallCode"]))

        viz = s.get("viz_config") or {}
        if viz:
            png = _render_chart_png(viz)
            if png:
                img = Image(io.BytesIO(png), width=160 * mm, height=80 * mm)
                story.append(Spacer(1, 3 * mm))
                story.append(img)

        rc = s.get("row_count")
        if rc is not None:
            story.append(Paragraph(f"Rows affected: {rc}", styles["SmallGrey"]))

        story.append(Spacer(1, 6 * mm))

        # Page break every 2 entries
        if idx % 2 == 0 and idx != len(sessions):
            story.append(PageBreak())

    doc.build(story)
    return output_path


def _escape(text: str) -> str:
    """Escape HTML-ish characters for ReportLab Paragraphs."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


# ===========================================================================
# Service class
# ===========================================================================
class VisualizationService:
    """Public API — one method per output type."""

    def generate_chart_config(self, state: AutoInsightState) -> VizConfig:
        return generate_chart_config(state)

    def build_pdf_report(
        self,
        sessions: list[dict[str, Any]],
        output_path: str | Path,
        *,
        title: str = "AutoInsight — Session Report",
    ) -> Path:
        return build_pdf_report(sessions, output_path, title=title)


# Module-level singleton
_viz_service: VisualizationService | None = None


def get_visualization_service() -> VisualizationService:
    global _viz_service
    if _viz_service is None:
        _viz_service = VisualizationService()
    return _viz_service
