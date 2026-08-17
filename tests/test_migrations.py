"""Migration tests for the Phase 02 ``audit_logs`` and Phase 10 sync metadata additions."""

from __future__ import annotations

from sqlalchemy import inspect

from app.data.migrations import runner


def test_schema_is_up_to_date(engine):
    assert runner.current_version(engine) == 3


def test_audit_logs_table_is_created_by_migration(engine):
    assert "audit_logs" in set(inspect(engine).get_table_names())


def test_downgrade_to_one_removes_audit_logs_then_upgrade_restores(engine):
    runner.downgrade(engine, target=1)
    assert runner.current_version(engine) == 1
    assert "audit_logs" not in set(inspect(engine).get_table_names())

    runner.upgrade(engine)
    assert runner.current_version(engine) == 3
    assert "audit_logs" in set(inspect(engine).get_table_names())


def test_audit_logs_columns(engine):
    columns = {col["name"] for col in inspect(engine).get_columns("audit_logs")}
    assert columns == {"id", "user_id", "username", "action", "details", "created_at"}
