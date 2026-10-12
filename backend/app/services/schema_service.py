"""
AutoInsight — Schema Service
=============================
Three-stage pipeline that turns a live Postgres schema into something an LLM
can usefully read:

    1. DISCOVERY   SQLAlchemy Inspector + raw pg_catalog queries
                   → tables, columns, types, PKs, FKs, CHECK enums, row counts

    2. ENRICHMENT  LLM (Groq / OpenAI / Together) adds one-line descriptions
                   per table and column — or hand-written stub when LLM is off

    3. INJECTION   Format the enriched schema as compact markdown ready to
                   drop into an LLM prompt

The SchemaService class caches the output of 1+2 (the schema does not change
between queries), and exposes `.get_schema_text()` for the SQL agent and
`.validate_references(sql)` for the Safety Pipeline.

Cache invalidation: call `.invalidate()` after any DDL change.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import Engine, inspect, text

from app.db import get_connection_manager
from app.llm import chat, is_llm_available


# ===========================================================================
# Dataclasses — the shape of a discovered + enriched schema
# ===========================================================================
@dataclass
class ColumnInfo:
    name: str
    type: str
    nullable: bool
    primary_key: bool = False
    default: str | None = None
    description: str = ""                                  # filled by enrichment
    check_values: list[str] = field(default_factory=list)  # from CHECK constraints


@dataclass
class ForeignKeyInfo:
    column: str
    references_table: str
    references_column: str


@dataclass
class TableInfo:
    name: str
    columns: list[ColumnInfo]
    foreign_keys: list[ForeignKeyInfo]
    primary_key: list[str]
    row_count: int = 0
    description: str = ""                                  # filled by enrichment


@dataclass
class Schema:
    tables: dict[str, TableInfo]
    discovered_at: datetime
    enriched: bool = False

    @property
    def table_count(self) -> int:
        return len(self.tables)

    @property
    def total_rows(self) -> int:
        return sum(t.row_count for t in self.tables.values())


# ===========================================================================
# STAGE 1 — Discovery
# ===========================================================================
def discover_schema(engine: Engine) -> Schema:
    """Pull raw schema metadata from Postgres via SQLAlchemy Inspector."""
    inspector = inspect(engine)
    tables: dict[str, TableInfo] = {}

    for table_name in inspector.get_table_names(schema="public"):

        # ---- Columns ----
        columns: list[ColumnInfo] = []
        for col in inspector.get_columns(table_name, schema="public"):
            columns.append(ColumnInfo(
                name=col["name"],
                type=str(col["type"]),
                nullable=col["nullable"],
                default=str(col["default"]) if col["default"] is not None else None,
            ))

        # ---- Primary key ----
        pk_info = inspector.get_pk_constraint(table_name, schema="public")
        pk_cols = pk_info.get("constrained_columns") or []
        for col in columns:
            if col.name in pk_cols:
                col.primary_key = True

        # ---- Foreign keys ----
        fks: list[ForeignKeyInfo] = []
        for fk in inspector.get_foreign_keys(table_name, schema="public"):
            for i, col_name in enumerate(fk["constrained_columns"]):
                fks.append(ForeignKeyInfo(
                    column=col_name,
                    references_table=fk["referred_table"],
                    references_column=fk["referred_columns"][i],
                ))

        # ---- Row count ----
        row_count = _safe_row_count(engine, table_name)

        # ---- CHECK constraint enum values ----
        check_values = _extract_check_values(engine, table_name)
        for col in columns:
            if col.name in check_values:
                col.check_values = check_values[col.name]

        tables[table_name] = TableInfo(
            name=table_name,
            columns=columns,
            foreign_keys=fks,
            primary_key=pk_cols,
            row_count=row_count,
        )

    return Schema(tables=tables, discovered_at=datetime.utcnow())


def _safe_row_count(engine: Engine, table_name: str) -> int:
    """Count rows safely — quote the identifier, fall back to 0 on error."""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
            return result.scalar() or 0
    except Exception:
        return 0


# Regex patterns for Postgres CHECK constraint definitions.
_CHECK_PATTERNS = [
    re.compile(
        r"\(?(?P<col>\w+)\)?::\w+\s*=\s*ANY\s*\(\s*ARRAY\[(?P<vals>.*?)\]\s*\)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<col>\w+)\s*=\s*ANY\s*\(\s*ARRAY\[(?P<vals>.*?)\]\s*\)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<col>\w+)\s+IN\s*\(\s*(?P<vals>[^)]+?)\s*\)",
        re.IGNORECASE,
    ),
]
_VAL_PATTERN = re.compile(r"'([^']*)'")


def _extract_check_values(engine: Engine, table_name: str) -> dict[str, list[str]]:
    """Parse CHECK constraints to recover enum-like allowed values."""
    sql = """
        SELECT con.conname,
               pg_get_constraintdef(con.oid, true) AS definition
        FROM   pg_constraint con
        JOIN   pg_class     rel ON rel.oid = con.conrelid
        JOIN   pg_namespace ns  ON ns.oid  = rel.relnamespace
        WHERE  rel.relname = :tbl
          AND  ns.nspname  = 'public'
          AND  con.contype = 'c'
    """
    result: dict[str, list[str]] = {}
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(sql), {"tbl": table_name}).fetchall()
    except Exception:
        return result

    for _, definition in rows:
        for pattern in _CHECK_PATTERNS:
            m = pattern.search(definition)
            if m:
                col = m.group("col")
                values = _VAL_PATTERN.findall(m.group("vals"))
                if values:
                    result.setdefault(col, values)
                    break
    return result


# ===========================================================================
# STAGE 2 — Enrichment  (Groq / OpenAI / Together / stub)
# ===========================================================================
#
# NOTE on Groq JSON mode: Groq enforces that the literal word "JSON" must
# appear in the prompt whenever response_format={"type": "json_object"} is
# used. Our prompt below satisfies this. Keep it in if you edit the prompt.
#
ENRICHMENT_PROMPT = """You are a database documentation assistant.

Given this automobile dealership schema, write:
- ONE short sentence (<= 15 words) describing what each table holds
- ONE short phrase (<= 8 words) describing what each column represents

Return a JSON object with exactly this shape (output valid JSON only):
{{
  "tables": {{
    "<table_name>": {{
      "description": "<one sentence>",
      "columns": {{"<col_name>": "<phrase>", ...}}
    }}, ...
  }}
}}

Schema:
{schema_json}

Return ONLY the JSON object, no prose, no markdown fences."""


def enrich_schema(schema: Schema, use_llm: bool = True) -> Schema:
    """
    Add one-line descriptions to every table and column.

    If `use_llm` is False or no LLM is configured, falls back to hand-written
    descriptions keyed on table name. This keeps the service usable offline
    and during dev.
    """
    if not use_llm or not is_llm_available():
        return _enrich_from_stub(schema)

    schema_json = json.dumps(
        {
            tbl: {"columns": [{"name": c.name, "type": c.type} for c in info.columns]}
            for tbl, info in schema.tables.items()
        },
        indent=2,
    )

    prompt = ENRICHMENT_PROMPT.format(schema_json=schema_json)

    try:
        content = chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            json_mode=True,
        )
        enrichment = json.loads(content)
    except Exception as e:
        print(f"[schema_service] LLM enrichment failed ({e}); falling back to stub.")
        return _enrich_from_stub(schema)

    for tbl_name, tbl_data in enrichment.get("tables", {}).items():
        if tbl_name not in schema.tables:
            continue
        table = schema.tables[tbl_name]
        table.description = tbl_data.get("description", "")
        col_descs = tbl_data.get("columns", {})
        for col in table.columns:
            col.description = col_descs.get(col.name, "")

    schema.enriched = True
    return schema


# ---- Stub descriptions (used when no LLM configured) ----
_STUB: dict[str, dict[str, Any]] = {
    "customers": {
        "description": "People who have bought vehicles or booked services at the dealership.",
        "columns": {
            "id": "Primary key", "name": "Full name of the customer",
            "email": "Unique contact email", "phone": "Mobile number with country code",
            "city": "City where the customer resides", "state": "Indian state of residence",
            "created_at": "When the record was created", "updated_at": "Last modification timestamp",
        },
    },
    "vehicles": {
        "description": "Cars in dealership inventory — available, sold, or reserved.",
        "columns": {
            "id": "Primary key", "make": "Manufacturer brand (Maruti Suzuki, Hyundai, etc.)",
            "model": "Model name (Swift, Creta, etc.)", "year": "Model year", "variant": "Trim level",
            "colour": "Exterior colour", "fuel_type": "Fuel type",
            "price": "Listed selling price in INR", "cost_price": "Dealer acquisition cost in INR",
            "vin": "Vehicle Identification Number (unique)", "status": "Inventory status",
            "created_at": "When the record was created", "updated_at": "Last modification timestamp",
        },
    },
    "sales": {
        "description": "Completed vehicle sale transactions.",
        "columns": {
            "id": "Primary key", "customer_id": "Buyer (FK to customers)",
            "vehicle_id": "Vehicle sold (FK to vehicles)",
            "salesperson_id": "Salesperson who closed (FK to salespersons)",
            "sale_date": "Date of the sale", "sale_price": "Final price paid in INR",
            "discount": "Discount offered in INR", "payment_method": "Mode of payment",
            "created_at": "When the record was created", "updated_at": "Last modification timestamp",
        },
    },
    "salespersons": {
        "description": "Staff who sell vehicles or handle service bookings.",
        "columns": {
            "id": "Primary key", "name": "Full name", "email": "Work email",
            "phone": "Contact number", "hire_date": "Date they joined the dealership",
            "department": "Department they work in", "commission_rate": "Percentage commission on sales",
            "is_active": "Whether currently employed",
            "created_at": "When the record was created", "updated_at": "Last modification timestamp",
        },
    },
    "services": {
        "description": "Workshop service and maintenance jobs on vehicles.",
        "columns": {
            "id": "Primary key", "vehicle_id": "Vehicle serviced (FK to vehicles)",
            "customer_id": "Customer who requested (FK to customers)",
            "service_date": "Date of service", "service_type": "Category of service performed",
            "description": "Free-text description of work done",
            "cost": "Billed amount in INR", "status": "Service status",
            "created_at": "When the record was created", "updated_at": "Last modification timestamp",
        },
    },
    "inventory_log": {
        "description": "Audit log of vehicle inventory movements.",
        "columns": {
            "id": "Primary key", "vehicle_id": "Vehicle involved (FK to vehicles)",
            "action": "Type of inventory action", "notes": "Optional free-text notes",
            "logged_at": "When the action occurred", "created_at": "When the record was created",
        },
    },
    "leads": {
        "description": "Sales lead funnel — prospective buyers and their status.",
        "columns": {
            "id": "Primary key", "customer_id": "Prospect (FK to customers)",
            "vehicle_id": "Vehicle of interest (FK to vehicles)",
            "salesperson_id": "Assigned salesperson (FK to salespersons)",
            "source": "Channel the lead came through", "status": "Lead funnel stage",
            "notes": "Free-text notes", "created_at": "When the lead was captured",
            "updated_at": "Last modification timestamp",
        },
    },
    "expenses": {
        "description": "Operational expenses — rent, utilities, marketing, etc.",
        "columns": {
            "id": "Primary key", "category": "Expense category", "amount": "Amount in INR",
            "description": "Free-text description", "expense_date": "Date the expense occurred",
            "created_at": "When the record was created", "updated_at": "Last modification timestamp",
        },
    },
}


def _enrich_from_stub(schema: Schema) -> Schema:
    """Hand-written descriptions for the dealership schema."""
    for tbl_name, table in schema.tables.items():
        stub = _STUB.get(tbl_name, {})
        table.description = stub.get("description", f"Table: {tbl_name}")
        col_descs = stub.get("columns", {})
        for col in table.columns:
            col.description = col_descs.get(col.name, "")
    schema.enriched = True
    return schema


# ===========================================================================
# STAGE 3 — Injection (format for LLM prompt)
# ===========================================================================
def format_schema_for_prompt(schema: Schema) -> str:
    """Format the schema as compact markdown for LLM prompt injection."""
    lines: list[str] = ["# Database Schema", ""]

    for tbl_name, table in schema.tables.items():
        lines.append(f"## `{tbl_name}`  — {table.row_count:,} rows")
        if table.description:
            lines.append(f"_{table.description}_")
        lines.append("")

        lines.append("| Column | Type | Null | Notes |")
        lines.append("|---|---|---|---|")
        for col in table.columns:
            notes: list[str] = []
            if col.primary_key:
                notes.append("**PK**")
            if col.check_values:
                vals = ", ".join(f"`{v}`" for v in col.check_values)
                notes.append(f"one of: {vals}")
            if col.description:
                notes.append(col.description)
            nullable = "Y" if col.nullable else "N"
            lines.append(f"| `{col.name}` | {col.type} | {nullable} | {' · '.join(notes)} |")

        if table.foreign_keys:
            lines.append("")
            lines.append("**Foreign keys:**")
            for fk in table.foreign_keys:
                lines.append(f"- `{fk.column}` → `{fk.references_table}.{fk.references_column}`")

        lines.append("")

    return "\n".join(lines)


# ===========================================================================
# SchemaService — public interface
# ===========================================================================
class SchemaService:
    """
    Caches the discovered + enriched schema and exposes:
      * introspect()              — run (or reuse) the pipeline
      * get_schema_text()         — markdown for LLM prompt injection
      * get_schema()              — the Schema dataclass
      * invalidate()              — clear cache after DDL migrations
      * validate_references(sql)  — check tables/columns exist (for Safety Pipeline)
    """

    def __init__(self, use_llm: bool = True):
        self._use_llm = use_llm
        self._cache: Schema | None = None
        self._cache_text: str | None = None

    def introspect(self, force_refresh: bool = False) -> Schema:
        """Run (or reuse cached) discovery + enrichment."""
        if self._cache is not None and not force_refresh:
            return self._cache

        engine = get_connection_manager().read_engine
        schema = discover_schema(engine)
        schema = enrich_schema(schema, use_llm=self._use_llm)

        self._cache = schema
        self._cache_text = format_schema_for_prompt(schema)
        return schema

    def get_schema(self) -> Schema:
        if self._cache is None:
            self.introspect()
        return self._cache  # type: ignore[return-value]

    def get_schema_text(self) -> str:
        if self._cache_text is None:
            self.introspect()
        return self._cache_text  # type: ignore[return-value]

    def invalidate(self) -> None:
        self._cache = None
        self._cache_text = None

    def validate_references(self, sql: str) -> tuple[bool, list[str]]:
        """
        Check that every table and qualified column reference in `sql`
        exists in the cached schema. Returns (is_valid, error_messages).
        """
        if self._cache is None:
            self.introspect()
        assert self._cache is not None

        errors: list[str] = []

        try:
            import sqlglot
            import sqlglot.expressions as exp
        except ImportError:
            errors.append("sqlglot not installed — skipping reference validation")
            return (False, errors)

        try:
            parsed = sqlglot.parse_one(sql, read="postgres")
        except Exception as e:
            return (False, [f"SQL parse error: {e}"])

        valid_tables = {t.lower() for t in self._cache.tables}

        for tbl in parsed.find_all(exp.Table):
            tbl_name = tbl.name.lower()
            if tbl_name not in valid_tables:
                errors.append(f"Unknown table: `{tbl_name}`")

        alias_to_table: dict[str, str] = {}
        for tbl in parsed.find_all(exp.Table):
            name = tbl.name.lower()
            alias = (tbl.alias or name).lower()
            alias_to_table[alias] = name

        for col in parsed.find_all(exp.Column):
            if not col.table:
                continue
            tbl_alias = col.table.lower()
            resolved = alias_to_table.get(tbl_alias, tbl_alias)
            if resolved not in valid_tables:
                continue
            table_info = self._cache.tables[resolved]
            table_cols = {c.name.lower() for c in table_info.columns}
            col_name = col.name.lower()
            if col_name != "*" and col_name not in table_cols:
                errors.append(f"Unknown column: `{resolved}.{col_name}`")

        return (len(errors) == 0, errors)


_schema_service: SchemaService | None = None


def get_schema_service(use_llm: bool = True) -> SchemaService:
    """Return the process-wide SchemaService singleton."""
    global _schema_service
    if _schema_service is None:
        _schema_service = SchemaService(use_llm=use_llm)
    return _schema_service
