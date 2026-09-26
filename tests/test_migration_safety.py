"""Phase 3 migration-safety tests: pre-upgrade backup, schema-version fencing,
and 005 table-rebuild failure handling.

The 005 AUTOCOMMIT rebuild is intentionally non-atomic (documented in the
migration module). These tests assert the guarantees that ARE provided: a
pre-upgrade backup exists, failures surface cleanly, the connection's
``foreign_keys`` pragma is restored, ``schema_version`` is not silently
advanced, the database is left in a known/documented state, and recovery from
the backup is possible. They deliberately do NOT assert atomicity of the
rebuild itself.
"""

from __future__ import annotations

import importlib
import sqlite3

import pytest
from sqlalchemy.engine import Connection

from app.data.db import create_db_engine
from app.data.migrations import runner


def _migration_005():
    return importlib.import_module(
        "app.data.migrations.versions.005_store_credit_and_sale_cancellation"
    )


def _backups(directory) -> set:
    return set(directory.glob("funmite_*.db"))


def _max_schema_version(db_path) -> int:
    source = sqlite3.connect(str(db_path))
    try:
        return source.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_version"
        ).fetchone()[0]
    finally:
        source.close()


def _table_names(engine) -> set[str]:
    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    return {name for (name,) in rows}


def test_upgrade_creates_a_pre_upgrade_backup(tmp_path):
    db = tmp_path / "app.db"
    eng = create_db_engine(db)
    runner.upgrade(eng, target=4)
    eng.dispose()

    before = _backups(tmp_path)
    assert before  # the 0 -> 4 upgrade already backed the database up

    eng = create_db_engine(db)
    runner.upgrade(eng)  # pending migration 005 only
    eng.dispose()

    added = _backups(tmp_path) - before
    assert len(added) == 1
    backup = added.pop()

    # The new backup captured the pre-upgrade (version 4) state, not version 5.
    assert _max_schema_version(backup) == 4
    source = sqlite3.connect(str(backup))
    try:
        assert source.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        source.close()

    eng = create_db_engine(db)
    try:
        assert runner.current_version(eng) == 5
    finally:
        eng.dispose()


def test_database_newer_than_known_schema_is_rejected(tmp_path):
    db = tmp_path / "newer.db"
    eng = create_db_engine(db)
    runner.upgrade(eng, target=5)
    with eng.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO schema_version (version, name) VALUES (999, 'future')"
        )
    eng.dispose()

    backups_before = _backups(tmp_path)
    eng = create_db_engine(db)
    with pytest.raises(runner.NewerSchemaError, match="newer than the latest") as excinfo:
        runner.upgrade(eng)
    assert excinfo.value.db_version == 999
    assert excinfo.value.app_version == 5
    eng.dispose()

    # Refusal happens BEFORE any backup or write against the newer database.
    assert _backups(tmp_path) == backups_before
    eng = create_db_engine(db)
    try:
        assert runner.current_version(eng) == 999
    finally:
        eng.dispose()


def test_downgrade_refuses_newer_schema(tmp_path):
    db = tmp_path / "newer.db"
    eng = create_db_engine(db)
    runner.upgrade(eng, target=5)
    with eng.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO schema_version (version, name) VALUES (999, 'future')"
        )
    eng.dispose()

    eng = create_db_engine(db)
    with pytest.raises(runner.NewerSchemaError):
        runner.downgrade(eng, target=0)
    eng.dispose()


def _create_legacy_v4_db(db_path) -> None:
    """Build a version-4 database whose tables predate migration 005.

    Migration 001 normally bootstraps from the current ORM models, so a
    migrated v4 DB already carries the 005 schema. Real pre-005 shops,
    however, have legacy ``sales``/``payments``/``exchanges`` tables without
    the CREDIT payment method — that is exactly the shape 005 must rebuild.
    """
    eng = create_db_engine(db_path)
    with eng.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE schema_version ("
            "version INTEGER PRIMARY KEY, name TEXT NOT NULL, "
            "applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        connection.exec_driver_sql("INSERT INTO schema_version (version, name) VALUES (4, 'legacy-v4')")
        connection.exec_driver_sql("CREATE TABLE customers (id INTEGER NOT NULL PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE users (id INTEGER NOT NULL PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO customers (id) VALUES (1)")
        connection.exec_driver_sql("INSERT INTO users (id) VALUES (1)")
        connection.exec_driver_sql(
            "CREATE TABLE sales ("
            "id INTEGER NOT NULL PRIMARY KEY, receipt_no VARCHAR(50) NOT NULL, "
            "customer_id INTEGER NOT NULL REFERENCES customers (id), "
            "cashier_id INTEGER NOT NULL REFERENCES users (id), "
            "sale_date DATETIME NOT NULL, subtotal NUMERIC(12, 2) NOT NULL, "
            "discount_type VARCHAR(20), discount_value NUMERIC(12, 2) NOT NULL DEFAULT 0, "
            "discount_amount NUMERIC(12, 2) NOT NULL DEFAULT 0, "
            "total NUMERIC(12, 2) NOT NULL, payment_method VARCHAR(20) NOT NULL, "
            "amount_paid NUMERIC(12, 2) NOT NULL, sync_uuid VARCHAR(36), "
            "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE payments ("
            "id INTEGER NOT NULL PRIMARY KEY, sale_id INTEGER NOT NULL REFERENCES sales (id), "
            "payment_method VARCHAR(20) NOT NULL, amount NUMERIC(12, 2) NOT NULL, "
            "reference VARCHAR(100), payment_date DATETIME NOT NULL, "
            "recorded_by INTEGER NOT NULL REFERENCES users (id), sync_uuid VARCHAR(36))"
        )
        connection.exec_driver_sql(
            "CREATE TABLE exchanges ("
            "id INTEGER NOT NULL PRIMARY KEY, original_sale_id INTEGER NOT NULL REFERENCES sales (id), "
            "customer_id INTEGER NOT NULL REFERENCES customers (id), "
            "approved_by INTEGER NOT NULL REFERENCES users (id), "
            "exchange_date DATETIME NOT NULL, difference_amount NUMERIC(12, 2) NOT NULL DEFAULT 0, "
            "difference_type VARCHAR(20) NOT NULL, payment_method VARCHAR(20), "
            "sync_uuid VARCHAR(36) NOT NULL, created_at DATETIME NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO sales (receipt_no, customer_id, cashier_id, sale_date, subtotal, total,"
            " payment_method, amount_paid, sync_uuid, created_at, updated_at)"
            " VALUES ('RC-001', 1, 1, '2026-01-01 10:00:00', 100, 100, 'POS', 100, NULL,"
            " '2026-01-01 10:00:00', '2026-01-01 10:00:00')"
        )
        connection.exec_driver_sql(
            "INSERT INTO payments (sale_id, payment_method, amount, payment_date, recorded_by,"
            " sync_uuid) VALUES (1, 'POS', 100, '2026-01-01 10:00:00', 1, NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO exchanges (original_sale_id, customer_id, approved_by, exchange_date,"
            " difference_type, sync_uuid, created_at)"
            " VALUES (1, 1, 1, '2026-01-02 10:00:00', 'NONE',"
            " 'bbbbbbbb-cccc-dddd-eeee-ffffffffffff', '2026-01-02 10:00:00')"
        )
    eng.dispose()


def test_005_rebuild_failure_is_clean_and_recoverable(tmp_path, monkeypatch):
    v005 = _migration_005()

    db = tmp_path / "app.db"
    _create_legacy_v4_db(db)
    backups_before = _backups(tmp_path)

    def boom(bind, table):
        raise RuntimeError("simulated rebuild failure")

    monkeypatch.setattr(v005, "_table_columns", boom)

    # Spy on the AUTOCOMMIT connection used by the rebuild so we can read the
    # foreign_keys pragma back right after the finally clause restores it.
    observed = {"fk_after_restore": None}
    original_exec = Connection.exec_driver_sql

    def spy(conn, statement, parameters=None, execution_options=None):
        result = original_exec(conn, statement, parameters, execution_options)
        if str(statement).strip().upper() == "PRAGMA FOREIGN_KEYS=ON":
            observed["fk_after_restore"] = conn.exec_driver_sql(
                "PRAGMA foreign_keys"
            ).scalar()
        return result

    monkeypatch.setattr(Connection, "exec_driver_sql", spy)

    eng = create_db_engine(db)
    with pytest.raises(RuntimeError, match="simulated rebuild failure"):
        runner.upgrade(eng)
    eng.dispose()

    # A pre-005 (version 4) backup exists.
    added = _backups(tmp_path) - backups_before
    assert len(added) == 1
    backup = added.pop()
    assert _max_schema_version(backup) == 4

    # The AUTOCOMMIT connection restored foreign_keys=ON even though the
    # rebuild raised, before the exception propagated.
    assert observed["fk_after_restore"] == 1

    # The database is not silently treated as migrated: schema_version stays 4
    # (SQLite DDL auto-commits under SQLAlchemy's sqlite3 dialect, so 005's
    # table DDL persists — but the runner never records the version row it
    # did not complete). The documented mid-rebuild state is: original data
    # table intact + a staging table leftover, still re-runnable later.
    eng = create_db_engine(db)
    try:
        assert runner.current_version(eng) == 4
        names = _table_names(eng)
        assert "sales" in names  # original data table intact
        assert "sales_mig5" in names  # documented staging leftover
        source = sqlite3.connect(str(db))
        try:
            assert source.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 1
        finally:
            source.close()
    finally:
        eng.dispose()

    # Recovery path A — re-run after the environment is restored: the rebuild
    # is idempotent, drops its own leftover staging table and completes.
    monkeypatch.undo()
    eng = create_db_engine(db)
    runner.upgrade(eng)
    assert runner.current_version(eng) == 5
    assert _table_names(eng).isdisjoint({"sales_mig5"})
    eng.dispose()

    # Recovery path B — restore the pre-upgrade backup: works, version 4 again.
    source = sqlite3.connect(str(backup))
    target = sqlite3.connect(str(db))
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()

    eng = create_db_engine(db)
    try:
        assert runner.current_version(eng) == 4
        assert _table_names(eng).isdisjoint({"sales_mig5"})
        source = sqlite3.connect(str(db))
        try:
            assert source.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            source.close()
    finally:
        eng.dispose()