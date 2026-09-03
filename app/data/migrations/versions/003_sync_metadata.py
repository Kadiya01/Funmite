"""Add sync metadata columns for Phase 10.

Adds ``sync_uuid`` (globally unique identifier) to all synced entities,
``version`` (optimistic locking) to mutable reference tables, and
``device_id`` to the sync queue.  These columns support the dual-PC
synchronization architecture without altering existing business logic.

This migration is idempotent: it checks whether columns already exist
before attempting to add them.  This handles both fresh databases (where
001_initial creates tables via Base.metadata, which now includes these
columns) and existing Phase 09 databases (where the columns don't exist
yet).
"""

from __future__ import annotations

from sqlalchemy import text

version = 3
name = "sync_metadata"

_SYNC_UUID_TABLES = (
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
)

_VERSION_TABLES = ("categories", "products", "customers", "suppliers")


def _column_exists(bind, table: str, column: str) -> bool:
    """Check if a column already exists in a table (SQLite-specific)."""
    result = bind.execute(
        text(f"PRAGMA table_info({table})")
    )
    for row in result:
        if row[1] == column:
            return True
    return False


def upgrade(bind) -> None:
    for table in _SYNC_UUID_TABLES:
        if not _column_exists(bind, table, "sync_uuid"):
            bind.execute(text(f'ALTER TABLE {table} ADD COLUMN sync_uuid TEXT'))
        bind.execute(text(
            f'CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_sync_uuid ON {table}(sync_uuid)'
        ))

    for table in _VERSION_TABLES:
        if not _column_exists(bind, table, "version"):
            bind.execute(text(f'ALTER TABLE {table} ADD COLUMN version INTEGER NOT NULL DEFAULT 1'))

    if not _column_exists(bind, "sync_queue", "device_id"):
        bind.execute(text('ALTER TABLE sync_queue ADD COLUMN device_id TEXT'))


def downgrade(bind) -> None:
    for table in _SYNC_UUID_TABLES:
        bind.execute(text(f'DROP INDEX IF EXISTS idx_{table}_sync_uuid'))
    # SQLite does not support DROP COLUMN before 3.35.0.
    # Columns remain but are unused after downgrade.
