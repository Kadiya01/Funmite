"""Add store credit, sale cancellation fields and widen payment methods.

Migration 005 (Shop-Use Decisions batch) adds three capability groups:

1. Store credit: a ``customer_credits`` ledger table. The no-cash rule means a
   customer-owed exchange refund becomes store credit the customer spends on a
   future sale.
2. Sale cancellation: ``sales`` gains ``status`` (COMPLETED/CANCELLED),
   ``cancelled_at``, ``cancelled_by_user_id`` and ``cancel_reason`` so an
   Admin may reverse + void a finished sale (``CAP_CANCEL_SALE``).
3. Widen payment methods: ``sales``, ``payments`` and ``exchanges`` now accept
   CREDIT (own-store credit) alongside POS and TRANSFER. ``exchanges`` also
   gains ``override_reason`` for the Admin 2-day-window override.

Fresh databases created from the current ORM models already have every column
and constraint (migration 001 builds from ``Base.metadata``), so the rebuild
helpers are idempotent: they detect the new schema before doing anything.

SQLite cannot alter a CHECK constraint and refuses to toggle
``PRAGMA foreign_keys`` inside a transaction, so the three table rebuilds run
on a dedicated AUTOCOMMIT connection with foreign keys disabled, following
SQLite's documented table-swap recipe. The migration-runner transaction only
records ``schema_version`` afterwards.
"""

from __future__ import annotations

version = 5
name = "store_credit_and_sale_cancellation"

_CUSTOMER_CREDITS_DDL = """
CREATE TABLE customer_credits (
    id INTEGER NOT NULL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers (id),
    amount NUMERIC(12, 2) NOT NULL,
    source VARCHAR(20) NOT NULL,
    exchange_id INTEGER REFERENCES exchanges (id),
    sale_id INTEGER REFERENCES sales (id),
    created_by INTEGER NOT NULL REFERENCES users (id),
    sync_uuid VARCHAR(36) NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT ck_customer_credits_source
        CHECK (source IN ('EXCHANGE', 'SALE_PAYMENT')),
    CONSTRAINT ck_customer_credits_amount_positive CHECK (amount > 0)
)
"""

_SALES_DDL = """
CREATE TABLE {name} (
    id INTEGER NOT NULL PRIMARY KEY,
    receipt_no VARCHAR(50) NOT NULL,
    customer_id INTEGER NOT NULL REFERENCES customers (id),
    cashier_id INTEGER NOT NULL REFERENCES users (id),
    sale_date DATETIME NOT NULL,
    subtotal NUMERIC(12, 2) NOT NULL,
    discount_type VARCHAR(20),
    discount_value NUMERIC(12, 2) NOT NULL DEFAULT 0,
    discount_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    total NUMERIC(12, 2) NOT NULL,
    payment_method VARCHAR(20) NOT NULL,
    amount_paid NUMERIC(12, 2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'COMPLETED',
    cancelled_at DATETIME,
    cancelled_by_user_id INTEGER REFERENCES users (id),
    cancel_reason VARCHAR(255),
    sync_uuid VARCHAR(36) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT ck_sales_payment_method
        CHECK (payment_method IN ('POS', 'TRANSFER', 'CREDIT')),
    CONSTRAINT ck_sales_status
        CHECK (status IN ('COMPLETED', 'CANCELLED')),
    CONSTRAINT ck_sales_subtotal CHECK (subtotal >= 0),
    CONSTRAINT ck_sales_discount_type
        CHECK (discount_type IS NULL OR discount_type IN ('PERCENT', 'FIXED')),
    CONSTRAINT ck_sales_discount_value CHECK (discount_value >= 0),
    CONSTRAINT ck_sales_discount_amount CHECK (discount_amount >= 0),
    CONSTRAINT ck_sales_total CHECK (total >= 0),
    CONSTRAINT ck_sales_amount_paid CHECK (amount_paid >= 0)
)
"""

_PAYMENTS_DDL = """
CREATE TABLE {name} (
    id INTEGER NOT NULL PRIMARY KEY,
    sale_id INTEGER NOT NULL REFERENCES sales (id),
    payment_method VARCHAR(20) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    reference VARCHAR(100),
    payment_date DATETIME NOT NULL,
    recorded_by INTEGER NOT NULL REFERENCES users (id),
    sync_uuid VARCHAR(36) NOT NULL,
    CONSTRAINT ck_payments_payment_method
        CHECK (payment_method IN ('POS', 'TRANSFER', 'CREDIT')),
    CONSTRAINT ck_payments_amount CHECK (amount > 0)
)
"""

_EXCHANGES_DDL = """
CREATE TABLE {name} (
    id INTEGER NOT NULL PRIMARY KEY,
    original_sale_id INTEGER NOT NULL REFERENCES sales (id),
    customer_id INTEGER NOT NULL REFERENCES customers (id),
    approved_by INTEGER NOT NULL REFERENCES users (id),
    exchange_date DATETIME NOT NULL,
    difference_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
    difference_type VARCHAR(20) NOT NULL,
    payment_method VARCHAR(20),
    override_reason VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'COMPLETED',
    sync_uuid VARCHAR(36) NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT ck_exchanges_difference_type
        CHECK (difference_type IN ('NONE', 'CUSTOMER_PAYS', 'CUSTOMER_RECEIVES')),
    CONSTRAINT ck_exchanges_payment_method
        CHECK (payment_method IS NULL OR payment_method IN ('POS', 'TRANSFER', 'CREDIT')),
    CONSTRAINT ck_exchanges_status
        CHECK (status IN ('COMPLETED', 'CANCELLED'))
)
"""

_REBUILD_TABLES = (
    ("sales", _SALES_DDL),
    ("payments", _PAYMENTS_DDL),
    ("exchanges", _EXCHANGES_DDL),
)


def _table_exists(bind, table: str) -> bool:
    row = bind.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _table_columns(bind, table: str) -> set[str]:
    rows = bind.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def _table_indexes(bind, table: str) -> list[str]:
    rows = bind.exec_driver_sql(
        "SELECT sql FROM sqlite_master "
        "WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL",
        (table,),
    ).fetchall()
    return [r[0] for r in rows]


def _check_accepts_credit(bind, table: str) -> bool:
    """Whether the table's payment-method CHECK already includes CREDIT."""
    row = bind.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None and "CREDIT" in (row[0] or "")


def upgrade(bind) -> None:
    if not _table_exists(bind, "customer_credits"):
        bind.exec_driver_sql(_CUSTOMER_CREDITS_DDL)
    bind.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_credits_sync_uuid "
        "ON customer_credits(sync_uuid)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_customer_credits_customer "
        "ON customer_credits(customer_id)"
    )
    bind.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS idx_customer_credits_source "
        "ON customer_credits(source)"
    )

    for table, ddl in _REBUILD_TABLES:
        if not _check_accepts_credit(bind, table):
            _rebuild_table(bind, table, ddl)


def _rebuild_table(bind, table: str, ddl: str) -> None:
    """Swap a SQLite table for a new-schema table, preserving data and indexes.

    Runs on a dedicated AUTOCOMMIT connection with foreign keys disabled
    (SQLite's required recipe for changing a CHECK constraint on a referenced
    table). The columns copied are the intersection of the old and new schema,
    so any non-additive changes would need to be handled explicitly here.
    """
    engine = bind.engine
    new_name = f"{table}_mig5"
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
        try:
            conn.exec_driver_sql(f"DROP TABLE IF EXISTS {new_name}")
            conn.exec_driver_sql(ddl.format(name=new_name))

            old_cols = _table_columns(conn, table)
            new_cols = _table_columns(conn, new_name)
            shared = sorted(old_cols & new_cols)
            if shared:
                select_exprs = [
                    (
                        f"COALESCE({col}, lower(hex(randomblob(16)))) AS {col}"
                        if col == "sync_uuid"
                        else col
                    )
                    for col in shared
                ]
                cols = ", ".join(shared)
                selects = ", ".join(select_exprs)
                conn.exec_driver_sql(
                    f"INSERT INTO {new_name} ({cols}) SELECT {selects} FROM {table}"
                )

            indexes = _table_indexes(conn, table)
            conn.exec_driver_sql(f"DROP TABLE {table}")
            conn.exec_driver_sql(f"ALTER TABLE {new_name} RENAME TO {table}")

            for index_sql in indexes:
                if index_sql:
                    conn.exec_driver_sql(index_sql)
        finally:
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")


def downgrade(bind) -> None:
    # SQLite does not support removing columns or recreating old CHECK
    # constraints without a full rebuild; columns remain but are unused.
    pass