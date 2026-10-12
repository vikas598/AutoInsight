"""
AutoInsight — Smoke test for the Schema Service
=================================================
Exercises every stage of the schema pipeline against the live Postgres DB.

Prerequisites:
  * Postgres running with the autoinsight DB
  * .env configured with DATABASE_URL_READ and DATABASE_URL_WRITE
  * schema.sql, db_users.sql, and seed.sql all applied

Run from the backend/ directory:
    python test_schema.py
"""

from __future__ import annotations

from app.services.schema_service import SchemaService


# Pretty divider
BAR = "=" * 70


def test_discovery(svc: SchemaService) -> None:
    print(f"\n{BAR}")
    print("STAGE 1 — DISCOVERY")
    print(BAR)
    schema = svc.introspect()
    print(f"  Discovered: {schema.table_count} tables, {schema.total_rows:,} rows total")
    print(f"  Discovered at: {schema.discovered_at.isoformat()}")
    print()
    print(f"  {'Table':<20} {'Cols':>5} {'Rows':>8}  FKs")
    print(f"  {'-'*20} {'-'*5} {'-'*8}  ---")
    for name, tbl in schema.tables.items():
        fk_summary = ", ".join(f"→{fk.references_table}" for fk in tbl.foreign_keys) or "-"
        print(f"  {name:<20} {len(tbl.columns):>5} {tbl.row_count:>8,}  {fk_summary}")


def test_enum_extraction(svc: SchemaService) -> None:
    print(f"\n{BAR}")
    print("CHECK-constraint enum extraction")
    print(BAR)
    schema = svc.get_schema()
    for name, tbl in schema.tables.items():
        for col in tbl.columns:
            if col.check_values:
                vals = ", ".join(col.check_values)
                print(f"  {name}.{col.name}: [{vals}]")


def test_enrichment(svc: SchemaService) -> None:
    print(f"\n{BAR}")
    print("STAGE 2 — ENRICHMENT (stub mode)")
    print(BAR)
    schema = svc.get_schema()
    assert schema.enriched, "Schema should be marked enriched"
    for name, tbl in schema.tables.items():
        print(f"  {name:<16} — {tbl.description}")


def test_injection(svc: SchemaService) -> None:
    print(f"\n{BAR}")
    print("STAGE 3 — INJECTION (first 60 lines)")
    print(BAR)
    text = svc.get_schema_text()
    for line in text.split("\n")[:60]:
        print(f"  {line}")
    print(f"  ...")
    print(f"\n  Full output: {len(text):,} characters (~{len(text)//4:,} tokens)")


def test_validation(svc: SchemaService) -> None:
    print(f"\n{BAR}")
    print("validate_references()")
    print(BAR)

    cases: list[tuple[str, bool]] = [
        # (sql, expected_valid)
        ("SELECT * FROM sales",                                                   True),
        ("SELECT customer_id, sale_price FROM sales WHERE sale_date > '2024-01-01'", True),
        ("SELECT s.customer_id, s.sale_price FROM sales s",                       True),
        ("SELECT s.customer_id, c.name FROM sales s JOIN customers c ON s.customer_id = c.id", True),
        ("SELECT * FROM nonexistent_table",                                       False),
        ("SELECT s.ghost_column FROM sales s",                                    False),
        ("SELECT bad.foo FROM sales s JOIN customers c ON s.customer_id = c.id",  False),
    ]

    for sql, expected in cases:
        ok, errors = svc.validate_references(sql)
        status = "PASS" if ok == expected else "FAIL"
        print(f"\n  [{status}] expected_valid={expected}, got valid={ok}")
        print(f"       SQL: {sql}")
        for err in errors:
            print(f"       error: {err}")


def test_caching(svc: SchemaService) -> None:
    print(f"\n{BAR}")
    print("Cache behavior")
    print(BAR)
    s1 = svc.introspect()
    s2 = svc.introspect()
    assert s1 is s2, "Second call should return cached schema"
    print("  OK — second introspect() returned same object")

    svc.invalidate()
    s3 = svc.introspect()
    assert s3 is not s1, "After invalidate(), should rediscover"
    print("  OK — invalidate() forces fresh discovery")


def main() -> None:
    svc = SchemaService(llm_client=None)   # stub-mode enrichment

    test_discovery(svc)
    test_enum_extraction(svc)
    test_enrichment(svc)
    test_injection(svc)
    test_validation(svc)
    test_caching(svc)

    print(f"\n{BAR}")
    print("All schema service tests complete.")
    print(BAR)


if __name__ == "__main__":
    main()
