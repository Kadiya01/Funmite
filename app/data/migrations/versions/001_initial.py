"""Initial schema: the approved production schema only.

The approved schema (``funmite_production_candidate.sql``) and the ORM models in
``app/data/models.py`` are the source of truth. This migration creates exactly
the approved tables. It deliberately lists the tables by name so later additive
migrations (e.g. ``002_audit_logs``) are the only place their tables are
created, and so future models never leak into this historical migration.

Future schema changes must be additive migrations in this package and must not
rely on ``create_all``.
"""

from __future__ import annotations

from app.data.models import Base

version = 1
name = "initial_schema"

APPROVED_TABLES = (
    "users",
    "categories",
    "products",
    "customers",
    "sales",
    "sale_items",
    "payments",
    "inventory_logs",
    "suppliers",
    "purchases",
    "purchase_items",
    "expenses",
    "exchanges",
    "exchange_items",
    "sync_queue",
    "sync_state",
)


def upgrade(bind) -> None:
    for table_name in APPROVED_TABLES:
        Base.metadata.tables[table_name].create(bind)


def downgrade(bind) -> None:
    for table_name in reversed(APPROVED_TABLES):
        Base.metadata.tables[table_name].drop(bind)
