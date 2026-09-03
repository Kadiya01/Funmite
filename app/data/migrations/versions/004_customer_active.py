"""Add ``is_active`` to the ``customers`` table (soft deactivation).

Phase 12 hardware-test correction: Admin must be able to deactivate customers.
A customer is never hard-deleted (sales/exchanges reference it historically);
instead a boolean ``is_active`` toggles whether the customer is selectable for
new sales. Existing rows default to active (1) so historical records stay valid.

This migration is idempotent: it checks whether the column already exists.
"""

from __future__ import annotations

from sqlalchemy import text

version = 4
name = "customer_active"


def _column_exists(bind, table: str, column: str) -> bool:
    result = bind.execute(text(f"PRAGMA table_info({table})"))
    for row in result:
        if row[1] == column:
            return True
    return False


def upgrade(bind) -> None:
    if not _column_exists(bind, "customers", "is_active"):
        bind.execute(text(
            "ALTER TABLE customers ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"
        ))


def downgrade(bind) -> None:
    # SQLite does not support DROP COLUMN before 3.35.0.
    # Column remains but is unused after downgrade.
    pass
