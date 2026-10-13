"""
AutoInsight — Test for the Dashboard Service
=============================================
Cross-checks every number get_overview() returns against independently
written SQL (different formulations: EXTRACT instead of ranges, Python-side
sums of the monthly series, a separate ranking query), plus the period
rules and the HTTP route. Read-only - touches nothing in the database.

Run from backend/:
    python test/test_dashboard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import get_connection_manager
from app.services.dashboard_service import get_overview

BAR = "=" * 72
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}{' - ' + detail if detail else ''}")
    if not ok:
        failures.append(name)


def close(a: float | None, b: float | None, tol: float = 0.01) -> bool:
    return a is not None and b is not None and abs(a - b) <= tol


def q(sql: str, **params):
    with get_connection_manager().read_engine.connect() as c:
        return c.execute(text(sql), params).fetchall()


def main() -> int:
    print(BAR, "\nDashboard service\n", BAR, sep="")

    years = [r[0] for r in q("SELECT DISTINCT EXTRACT(YEAR FROM sale_date)::int FROM sales ORDER BY 1")]
    latest = years[-1]

    # ---- Default period = latest year with sales ----
    ov = get_overview()
    check("default period is latest sales year", ov["period"]["id"] == str(latest), ov["period"]["id"])

    for pid in [str(y) for y in years] + ["all"]:
        ov = get_overview(pid)
        print(f"\nPeriod {pid}: {ov['period']['start']} -> {ov['period']['end_exclusive']} (exclusive)")

        where = "TRUE" if pid == "all" else f"EXTRACT(YEAR FROM sale_date) = {int(pid)}"
        units, revenue, discount = q(
            f"SELECT COUNT(*), COALESCE(SUM(sale_price),0)::float, COALESCE(SUM(discount),0)::float FROM sales WHERE {where}"
        )[0]
        k = ov["kpis"]

        check("units_sold", k["units_sold"]["value"] == units, f"{k['units_sold']['value']} vs {units}")
        check("total_revenue", close(k["total_revenue"]["value"], revenue), f"{k['total_revenue']['value']:.2f} vs {revenue:.2f}")
        check("total_discount", close(k["total_discount"]["value"], discount))
        check("average_sale_value = revenue / units",
              close(k["average_sale_value"]["value"], revenue / units if units else None))

        # Monthly series: zero-filled, contiguous, sums to the KPIs
        m = ov["monthly"]
        check("monthly sums to units", sum(x["units"] for x in m) == units)
        check("monthly sums to revenue", close(sum(x["revenue"] for x in m), revenue, tol=0.05))
        expected_months = q(
            "SELECT COUNT(*) FROM generate_series(CAST(:s AS date), CAST(:e AS date) - INTERVAL '1 day', INTERVAL '1 month')",
            s=ov["period"]["start"], e=ov["period"]["end_exclusive"],
        )[0][0]
        check("monthly has every month in period", len(m) == expected_months, f"{len(m)} months")
        check("months strictly increasing", all(a["month"] < b["month"] for a, b in zip(m, m[1:])))

        # Top models: independent ranking query
        ref = q(
            f"""SELECT v.make, v.model, COUNT(*) AS units, SUM(s.sale_price)::float AS revenue
                FROM sales s JOIN vehicles v ON v.id = s.vehicle_id
                WHERE {where.replace('sale_date', 's.sale_date')}
                GROUP BY v.make, v.model ORDER BY units DESC, revenue DESC, v.make, v.model LIMIT 10"""
        )
        got = [(t["make"], t["model"], t["units"]) for t in ov["top_models"]]
        check("top models match (make, model, units)", got == [(r[0], r[1], r[2]) for r in ref])
        check("top model labels unique", len({(t["make"], t["model"]) for t in ov["top_models"]}) == len(ov["top_models"]))

    # ---- Comparison rules ----
    print()
    ov = get_overview(str(years[0]))
    check("earliest year has no comparison", ov["comparison"] is None, ov["comparison_unavailable_reason"] or "")
    ov = get_overview("all")
    check("'all' has no comparison", ov["comparison"] is None)
    if len(years) > 1:
        ov = get_overview(str(latest))
        prev_units = q("SELECT COUNT(*) FROM sales WHERE EXTRACT(YEAR FROM sale_date) = :y", y=latest - 1)[0][0]
        if ov["comparison"]:
            check("comparison is previous year", ov["comparison"]["id"] == str(latest - 1))
            check("previous units correct", ov["kpis"]["units_sold"]["previous"] == prev_units)
        else:
            print("  [INFO] latest year has no comparison:", ov["comparison_unavailable_reason"])

    # ---- Inventory ----
    print()
    status_rows = dict(q("SELECT status, COUNT(*) FROM vehicles GROUP BY status"))
    inv = ov["inventory"]
    check("inventory total", inv["total"] == sum(status_rows.values()), str(inv["total"]))
    check("available = status 'available' only", inv["available"] == status_rows.get("available", 0), str(inv["available"]))
    check("allowed statuses from CHECK constraint",
          set(inv["allowed_statuses"]) == {"available", "sold", "reserved", "in_transit"}, str(inv["allowed_statuses"]))
    check("status breakdown sums to total (no double counting)", sum(s["count"] for s in inv["by_status"]) == inv["total"])

    # ---- Validation + HTTP route ----
    print()
    try:
        get_overview("1999")
        check("unknown period rejected", False)
    except ValueError as e:
        check("unknown period rejected", True, str(e))

    from app.api.main import app
    client = TestClient(app)
    r = client.get("/api/dashboard/overview")
    check("GET /api/dashboard/overview -> 200", r.status_code == 200)
    r = client.get("/api/dashboard/overview", params={"period": "2019"})
    check("invalid period -> 400", r.status_code == 400, r.json().get("detail", ""))
    r = client.get("/api/dashboard/overview", params={"period": "x" * 20})
    check("over-long period -> 422", r.status_code == 422)

    print("\n" + BAR)
    print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
