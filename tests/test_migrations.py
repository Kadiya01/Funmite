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
