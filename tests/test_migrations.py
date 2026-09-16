"""Migration tests for the Phase 02 ``audit_logs``, Phase 10 sync metadata,
and Phase 12 customer ``is_active`` additions."""

from __future__ import annotations

from sqlalchemy import inspect, text

from app.data.migrations import runner


def test_schema_is_up_to_date(engine):
    assert runner.current_version(engine) == 5


def test_audit_logs_table_is_created_by_migration(engine):
    assert "audit_logs" in set(inspect(engine).get_table_names())


def test_downgrade_to_one_removes_audit_logs_then_upgrade_restores(engine):
    runner.downgrade(engine, target=1)
    assert runner.current_version(engine) == 1
    assert "audit_logs" not in set(inspect(engine).get_table_names())

    runner.upgrade(engine)
    assert runner.current_version(engine) == 5
    assert "audit_logs" in set(inspect(engine).get_table_names())


def test_audit_logs_columns(engine):
    columns = {col["name"] for col in inspect(engine).get_columns("audit_logs")}
    assert columns == {"id", "user_id", "username", "action", "details", "created_at"}


def test_customers_is_active_column_exists(engine):
    columns = {col["name"] for col in inspect(engine).get_columns("customers")}
    assert "is_active" in columns


def test_customer_active_column_defaults_for_new_rows(session_factory):
    """New customers are active by default through the ORM."""
    from app.data.models import Customer
    from sqlalchemy import select

    with session_factory() as s:
        c = Customer(customer_code="CUS-001", name="New Buyer")
        s.add(c)
        s.commit()
        s.refresh(c)
        assert c.is_active is True


def test_customer_active_migration_is_idempotent(engine):
    """Migration 004 re-runs cleanly when is_active already exists (001 path)."""
    import importlib

    mod = importlib.import_module(
        "app.data.migrations.versions.004_customer_active"
    )
    with engine.begin() as connection:
        mod.upgrade(connection)
    with engine.connect() as connection:
        cols = connection.execute(
            text("SELECT name FROM pragma_table_info('customers') WHERE name='is_active'")
        ).scalar()
    assert cols == "is_active"


def test_005_rebuild_backfills_null_sync_uuid(tmp_path):
    """Migration 005's table rebuild must survive legacy rows whose sync_uuid is NULL.

    Pre-005 databases could contain rows where ``sync_uuid`` was never set
    (the column was added nullable). The rebuild-sync recipe copies those rows
    into a fresh ``NOT NULL`` table, so the run must backfill a UUID while
    preserving every row and never duplicating values.
    """
    import importlib

    from app.data.db import create_db_engine

    mod = importlib.import_module(
        "app.data.migrations.versions.005_store_credit_and_sale_cancellation"
    )
    legacy = create_db_engine(tmp_path / "legacy.db")

    legacy_sales = """
    CREATE TABLE sales (
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
        sync_uuid VARCHAR(36),
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL
    )
    """
    with legacy.begin() as setup:
        setup.exec_driver_sql(
            "CREATE TABLE customers (id INTEGER NOT NULL PRIMARY KEY)"
        )
        setup.exec_driver_sql(
            "CREATE TABLE users (id INTEGER NOT NULL PRIMARY KEY)"
        )
        setup.exec_driver_sql("INSERT INTO customers (id) VALUES (1)")
        setup.exec_driver_sql("INSERT INTO users (id) VALUES (1)")
        setup.exec_driver_sql(legacy_sales)
        setup.exec_driver_sql(
            "INSERT INTO sales (receipt_no, customer_id, cashier_id, sale_date, subtotal, total,"
            " payment_method, amount_paid, sync_uuid, created_at, updated_at)"
            " VALUES ('RC-001', 1, 1, '2026-01-01 10:00:00', 100, 100, 'POS', 100, NULL,"
            " '2026-01-01 10:00:00', '2026-01-01 10:00:00')"
        )
        setup.exec_driver_sql(
            "INSERT INTO sales (receipt_no, customer_id, cashier_id, sale_date, subtotal, total,"
            " payment_method, amount_paid, sync_uuid, created_at, updated_at)"
            " VALUES ('RC-002', 1, 1, '2026-01-02 10:00:00', 50, 50, 'TRANSFER', 50,"
            " 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',"
            " '2026-01-02 10:00:00', '2026-01-02 10:00:00')"
        )

    with legacy.begin() as connection:
        mod._rebuild_table(connection, "sales", mod._SALES_DDL)

    with legacy.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT sync_uuid FROM sales ORDER BY id"
        ).fetchall()
        uuids = [uuid for (uuid,) in rows]
        assert len(rows) == 2
        assert all(uuids)
        assert len(set(uuids)) == 2
        table_sql = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='sales'"
        ).scalar()
        assert "CREDIT" in (table_sql or "")
    legacy.dispose()
