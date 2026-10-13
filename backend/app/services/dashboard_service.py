"""
AutoInsight — Dashboard Service
================================
Deterministic, read-only aggregations for the Overview dashboard. No LLM is
involved: every number comes from fixed, parameterized SQL on the restricted
reader engine.

Metric definitions (all sales metrics share one reporting period):

    total_revenue       SUM(sales.sale_price)  — the amount actually charged.
                        In this schema sale_price is already net of discount
                        (seed: sale_price = vehicles.price - discount), so the
                        discount is NOT subtracted again.
    units_sold          COUNT(sales.id)        — one row per sale. Vehicle
                        rows can appear in several sales, so this is not
                        COUNT(DISTINCT vehicle_id).
    average_sale_value  total_revenue / units_sold (null when no sales).
    available_inventory COUNT(vehicles) WHERE status = 'available' — a current
                        snapshot, not filtered by the reporting period.

Reporting period:
    Derived from the data, never from today's date. `period` is either a
    calendar year that contains sales ("2024") or "all" (first to last month
    with sales). Default: the latest year with sales. Ranges are half-open
    [start, end) on sales.sale_date.

Comparison:
    Only for a calendar-year period whose previous year also has sales, and
    only when the dataset's sale dates fully span both years — so a partial
    year is never compared against a full one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import text

from app.db import get_connection_manager
from app.services.schema_service import _extract_check_values

AVAILABLE_STATUS = "available"
TOP_MODELS_LIMIT = 10


@dataclass(frozen=True)
class Period:
    id: str
    label: str
    start: date          # inclusive
    end: date            # exclusive

    def as_dict(self, complete: bool | None = None) -> dict[str, Any]:
        d = {"id": self.id, "label": self.label,
             "start": self.start.isoformat(), "end_exclusive": self.end.isoformat()}
        if complete is not None:
            d["complete"] = complete
        return d


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def _next_month(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def _year_period(year: int) -> Period:
    return Period(str(year), str(year), date(year, 1, 1), date(year + 1, 1, 1))


def _covers(first: date, last: date, p: Period) -> bool:
    """True if the dataset's sale dates span the whole period."""
    return first <= p.start and last >= date.fromordinal(p.end.toordinal() - 1)


def _f(v: Any) -> float:
    return float(v) if v is not None else 0.0


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------
_SQL_EXTENT = text("""
    SELECT MIN(sale_date) AS first, MAX(sale_date) AS last, COUNT(*) AS n
    FROM sales
""")

_SQL_YEARS = text("""
    SELECT DISTINCT EXTRACT(YEAR FROM sale_date)::int AS y
    FROM sales ORDER BY y
""")

_SQL_TOTALS = text("""
    SELECT COUNT(*)                         AS units,
           COALESCE(SUM(sale_price), 0)     AS revenue,
           COALESCE(SUM(discount), 0)       AS discount
    FROM sales
    WHERE sale_date >= :start AND sale_date < :end
""")

# Every month in the period appears, with zeros where there were no sales
_SQL_MONTHLY = text("""
    SELECT to_char(m.month, 'YYYY-MM')        AS month,
           COUNT(s.id)                        AS units,
           COALESCE(SUM(s.sale_price), 0)     AS revenue
    FROM generate_series(CAST(:start AS date), CAST(:last_month AS date), INTERVAL '1 month') AS m(month)
    LEFT JOIN sales s
           ON s.sale_date >= m.month
          AND s.sale_date <  m.month + INTERVAL '1 month'
    GROUP BY m.month
    ORDER BY m.month
""")

_SQL_TOP_MODELS = text("""
    SELECT v.make, v.model,
           COUNT(*)            AS units,
           SUM(s.sale_price)   AS revenue
    FROM sales s
    JOIN vehicles v ON v.id = s.vehicle_id
    WHERE s.sale_date >= :start AND s.sale_date < :end
    GROUP BY v.make, v.model
    ORDER BY units DESC, revenue DESC, v.make, v.model
    LIMIT :limit
""")

_SQL_INVENTORY = text("""
    SELECT status, COUNT(*) AS n FROM vehicles GROUP BY status
""")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def get_overview(period: str | None = None) -> dict[str, Any]:
    """
    Build the Overview payload. Raises ValueError for an unknown period.
    """
    engine = get_connection_manager().read_engine

    with engine.connect() as conn:
        extent = conn.execute(_SQL_EXTENT).mappings().one()
        years = [r.y for r in conn.execute(_SQL_YEARS)]

        inventory_rows = {r.status: int(r.n) for r in conn.execute(_SQL_INVENTORY)}
        allowed = _extract_check_values(engine, "vehicles").get("status", [])

        inventory = _inventory(inventory_rows, allowed)

        # ---- Empty dataset: still report inventory; no sales sections ----
        if not extent["n"]:
            if period not in (None, "all"):
                raise ValueError("There are no sales records, so no reporting period is available.")
            return {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "data_extent": None,
                "periods": [],
                "period": None,
                "comparison": None,
                "comparison_unavailable_reason": "There are no sales records.",
                "kpis": _kpis(None, None, inventory),
                "monthly": [],
                "top_models": [],
                "inventory": inventory,
            }

        first: date = extent["first"]
        last: date = extent["last"]

        all_period = Period(
            "all",
            f"{first.strftime('%b %Y')} – {last.strftime('%b %Y')}",
            _month_start(first),
            _next_month(last),
        )
        options = [_year_period(y) for y in reversed(years)] + [all_period]
        by_id = {p.id: p for p in options}

        selected_id = period or str(years[-1])
        if selected_id not in by_id:
            raise ValueError(
                f"Unknown period '{period}'. Choose one of: {', '.join(by_id)}."
            )
        selected = by_id[selected_id]

        # ---- Comparison period (previous calendar year, only if fair) ----
        comparison: Period | None = None
        reason: str | None = None
        if selected.id == "all":
            reason = "Comparison is not available for the full date range."
        else:
            prev = _year_period(int(selected.id) - 1)
            if prev.id not in by_id:
                reason = f"There are no sales in {prev.label} to compare against."
            elif not (_covers(first, last, selected) and _covers(first, last, prev)):
                reason = "The recorded data does not cover both full years, so a comparison would be misleading."
            else:
                comparison = prev

        current = _totals(conn, selected)
        previous = _totals(conn, comparison) if comparison else None

        monthly = [
            {"month": r.month, "units": int(r.units), "revenue": _f(r.revenue)}
            for r in conn.execute(_SQL_MONTHLY, {
                "start": selected.start,
                "last_month": date.fromordinal(selected.end.toordinal() - 1).replace(day=1),
            })
        ]

        top_models = [
            {"make": r.make, "model": r.model, "units": int(r.units), "revenue": _f(r.revenue)}
            for r in conn.execute(_SQL_TOP_MODELS, {
                "start": selected.start, "end": selected.end, "limit": TOP_MODELS_LIMIT,
            })
        ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_extent": {
            "first_sale_date": first.isoformat(),
            "last_sale_date": last.isoformat(),
            "total_sales": int(extent["n"]),
        },
        "periods": [p.as_dict(complete=_covers(first, last, p)) for p in options],
        "period": selected.as_dict(complete=_covers(first, last, selected)),
        "comparison": comparison.as_dict() if comparison else None,
        "comparison_unavailable_reason": reason,
        "kpis": _kpis(current, previous, inventory),
        "monthly": monthly,
        "top_models": top_models,
        "inventory": inventory,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _totals(conn, p: Period) -> dict[str, float | int]:
    r = conn.execute(_SQL_TOTALS, {"start": p.start, "end": p.end}).mappings().one()
    units = int(r["units"])
    revenue = _f(r["revenue"])
    return {
        "units": units,
        "revenue": revenue,
        "discount": _f(r["discount"]),
        "average": revenue / units if units else None,
    }


def _kpis(current: dict | None, previous: dict | None, inventory: dict) -> dict[str, Any]:
    def metric(key: str) -> dict[str, Any]:
        return {
            "value": current[key] if current else None,
            "previous": previous[key] if previous else None,
        }

    return {
        "total_revenue": metric("revenue"),
        "units_sold": metric("units"),
        "average_sale_value": metric("average"),
        "total_discount": metric("discount"),
        "available_inventory": {"value": inventory["available"], "previous": None},
    }


def _inventory(counts: dict[str, int], allowed: list[str]) -> dict[str, Any]:
    """Status breakdown, zero-filled with every status the CHECK constraint allows."""
    statuses = list(allowed) + sorted(s for s in counts if s not in allowed)
    return {
        "total": sum(counts.values()),
        "available": counts.get(AVAILABLE_STATUS, 0),
        "allowed_statuses": list(allowed),
        "by_status": [{"status": s, "count": counts.get(s, 0)} for s in statuses],
    }
