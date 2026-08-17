"""Backup and recovery service tests (Phase 09).

Covers authorization, backup creation, listing, validation, restore with
pre-restore safety backup, integrity checks, audit logging, and edge cases.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from app.data.db import session_scope
from app.data.models import ROLE_ADMIN, ROLE_CASHIER, AuditLog
from app.domain.errors import AuthorizationError
from app.domain.services.audit_service import ACTION_BACKUP, ACTION_RESTORE
from app.domain.services.backup_service import (
    BACKUP_PREFIX,
    BACKUP_SUFFIX,
    BackupInfo,
    BackupResult,
    BackupService,
    RestoreResult,
)
from app.domain.session import CurrentUser
from tests.factories import make_user


# -- helpers --------------------------------------------------------------- #


def _admin_user(session) -> CurrentUser:
    user = make_user(session, role=ROLE_ADMIN, full_name="Admin User")
    return CurrentUser(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
    )


def _cashier_user(session) -> CurrentUser:
    user = make_user(session, role=ROLE_CASHIER, full_name="Cashier User")
    return CurrentUser(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
    )


def _make_db(path: Path, *, products: int = 0) -> None:
    """Create a minimal valid SQLite database at ``path``."""
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY)")
    for i in range(products):
        conn.execute("INSERT INTO test VALUES (?)", (i + 1,))
    conn.commit()
    conn.close()


def _service(
    session, db_path: Path, backup_dir: Path
) -> BackupService:
    return BackupService(session, db_path=db_path, backup_dir=backup_dir)


# -- Authorization -------------------------------------------------------- #


class TestAuthorization:
    """Backup and restore require Admin role."""

    def test_admin_can_backup(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        result = svc.create_backup(user)
        assert result.success is True

    def test_cashier_cannot_backup(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _cashier_user(session)
        svc = _service(session, db, tmp_path / "backups")
        with pytest.raises(AuthorizationError):
            svc.create_backup(user)

    def test_admin_can_restore(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        # Create a backup first
        backup = svc.create_backup(user)
        session.commit()
        result = svc.restore_backup(user, Path(backup.backup_path))
        assert result.success is True

    def test_cashier_cannot_restore(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _cashier_user(session)
        svc = _service(session, db, tmp_path / "backups")
        with pytest.raises(AuthorizationError):
            svc.restore_backup(user, db)

    def test_cashier_cannot_list_backups(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _cashier_user(session)
        svc = _service(session, db, tmp_path / "backups")
        with pytest.raises(AuthorizationError):
            svc.list_backups(user)

    def test_cashier_cannot_validate_backup(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _cashier_user(session)
        svc = _service(session, db, tmp_path / "backups")
        with pytest.raises(AuthorizationError):
            svc.validate_backup(user, db)


# -- Backup creation ------------------------------------------------------- #


class TestBackupCreation:
    """create_backup produces valid SQLite backup files."""

    def test_creates_backup_file(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        result = svc.create_backup(user)
        assert result.success is True
        assert result.backup_path is not None
        assert result.filename is not None
        assert Path(result.backup_path).exists()

    def test_backup_filename_has_correct_prefix(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        result = svc.create_backup(user)
        assert result.filename.startswith(BACKUP_PREFIX)
        assert result.filename.endswith(BACKUP_SUFFIX)

    def test_backup_filename_has_datetime(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        result = svc.create_backup(user)
        # Extract the date part from the filename
        date_str = result.filename[len(BACKUP_PREFIX) : -len(BACKUP_SUFFIX)]
        datetime.strptime(date_str, "%Y%m%d_%H%M%S_%f")  # Should not raise

    def test_backup_is_valid_sqlite(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db, products=5)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        result = svc.create_backup(user)
        conn = sqlite3.connect(result.backup_path)
        rows = conn.execute("SELECT COUNT(*) FROM test").fetchone()[0]
        conn.close()
        assert rows == 5

    def test_backup_captures_data(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db, products=10)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        result = svc.create_backup(user)
        conn = sqlite3.connect(result.backup_path)
        rows = conn.execute("SELECT COUNT(*) FROM test").fetchone()[0]
        conn.close()
        assert rows == 10

    def test_multiple_backups_all_valid(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        for _ in range(3):
            result = svc.create_backup(user)
            assert result.success is True
        session.commit()
        backups = svc.list_backups(user)
        assert len(backups) == 3

    def test_backup_failure_cleans_up(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        # Use a directory as the source path — sqlite3.connect fails on directories
        svc = _service(session, tmp_path, tmp_path / "backups")
        result = svc.create_backup(user)
        assert result.success is False
        assert result.error is not None


# -- Backup listing -------------------------------------------------------- #


class TestBackupListing:
    """list_backups returns backups ordered newest-first."""

    def test_empty_directory(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        backups = svc.list_backups(user)
        assert backups == []

    def test_lists_backups_newest_first(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        svc.create_backup(user)
        svc.create_backup(user)
        session.commit()
        backups = svc.list_backups(user)
        assert len(backups) == 2
        assert backups[0].created_at >= backups[1].created_at

    def test_backup_info_fields(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        svc.create_backup(user)
        session.commit()
        backups = svc.list_backups(user)
        assert len(backups) == 1
        b = backups[0]
        assert isinstance(b, BackupInfo)
        assert b.filename.startswith(BACKUP_PREFIX)
        assert b.size_bytes > 0
        assert isinstance(b.created_at, datetime)

    def test_ignores_non_backup_files(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        # Create a non-matching file
        (tmp_path / "backups" / "random_file.txt").write_text("not a backup")
        backups = svc.list_backups(user)
        assert backups == []


# -- Backup validation ----------------------------------------------------- #


class TestBackupValidation:
    """validate_backup checks for valid SQLite database files."""

    def test_valid_backup(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        result = svc.create_backup(user)
        session.commit()
        assert svc.validate_backup(user, Path(result.backup_path)) is True

    def test_nonexistent_file(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        assert svc.validate_backup(user, tmp_path / "nonexistent.db") is False

    def test_corrupt_file(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        corrupt = tmp_path / "backups" / "corrupt.db"
        corrupt.write_bytes(b"not a sqlite database at all")
        assert svc.validate_backup(user, corrupt) is False

    def test_empty_file(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        empty = tmp_path / "backups" / "empty.db"
        empty.write_bytes(b"")
        assert svc.validate_backup(user, empty) is False

    def test_truncated_sqlite(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        truncated = tmp_path / "backups" / "truncated.db"
        truncated.write_bytes(b"SQLite format 3\x00")
        assert svc.validate_backup(user, truncated) is False


# -- Restore --------------------------------------------------------------- #


class TestRestore:
    """restore_backup replaces the live database safely."""

    def test_restore_replaces_database(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db, products=5)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        # Create backup
        backup = svc.create_backup(user)
        session.commit()

        # Modify the live database
        conn = sqlite3.connect(str(db))
        conn.execute("DELETE FROM test")
        conn.commit()
        conn.close()

        # Restore
        result = svc.restore_backup(user, Path(backup.backup_path))
        assert result.success is True

        # Verify data is restored
        conn = sqlite3.connect(str(db))
        rows = conn.execute("SELECT COUNT(*) FROM test").fetchone()[0]
        conn.close()
        assert rows == 5

    def test_creates_pre_restore_backup(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db, products=3)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        backup = svc.create_backup(user)
        session.commit()

        result = svc.restore_backup(user, Path(backup.backup_path))
        assert result.pre_restore_backup is not None
        assert Path(result.pre_restore_backup).exists()
        assert "pre_restore" in Path(result.pre_restore_backup).name

    def test_pre_restore_backup_captures_current_state(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db, products=10)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        backup = svc.create_backup(user)
        session.commit()

        # Add more data to the live database
        conn = sqlite3.connect(str(db))
        conn.execute("INSERT INTO test VALUES (99)")
        conn.commit()
        conn.close()

        result = svc.restore_backup(user, Path(backup.backup_path))
        assert result.success is True

        # Pre-restore backup should have the extra row
        conn = sqlite3.connect(result.pre_restore_backup)
        rows = conn.execute("SELECT COUNT(*) FROM test").fetchone()[0]
        conn.close()
        assert rows == 11  # 10 original + 1 added

    def test_restore_with_invalid_backup(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        corrupt = tmp_path / "backups" / "bad.db"
        corrupt.write_bytes(b"not valid")
        result = svc.restore_backup(user, corrupt)
        assert result.success is False
        assert "Invalid backup" in result.error

    def test_restore_integrity_check_failure(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db, products=5)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        backup = svc.create_backup(user)
        session.commit()

        # Corrupt the backup file after validation
        with open(backup.backup_path, "rb") as f:
            data = f.read()
        # Write truncated data
        with open(backup.backup_path, "wb") as f:
            f.write(data[: len(data) // 2])

        result = svc.restore_backup(user, Path(backup.backup_path))
        assert result.success is False

    def test_restore_preserves_live_database_on_failure(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db, products=7)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        backup = svc.create_backup(user)
        session.commit()

        # Try to restore from a corrupt backup
        corrupt = tmp_path / "backups" / "corrupt.db"
        corrupt.write_bytes(b"not a database")

        result = svc.restore_backup(user, corrupt)
        assert result.success is False

        # Live database should be untouched
        conn = sqlite3.connect(str(db))
        rows = conn.execute("SELECT COUNT(*) FROM test").fetchone()[0]
        conn.close()
        assert rows == 7


# -- Audit logging --------------------------------------------------------- #


class TestAuditLogging:
    """Backup and restore actions are recorded in the audit log."""

    def test_backup_creates_audit_entry(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        svc.create_backup(user)
        session.commit()

        entry = (
            session.query(AuditLog)
            .filter(AuditLog.action == ACTION_BACKUP)
            .first()
        )
        assert entry is not None
        assert entry.user_id == user.user_id
        assert entry.username == user.username

    def test_restore_creates_audit_entry(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        backup = svc.create_backup(user)
        session.commit()

        svc.restore_backup(user, Path(backup.backup_path))
        session.commit()

        entry = (
            session.query(AuditLog)
            .filter(AuditLog.action == ACTION_RESTORE)
            .first()
        )
        assert entry is not None
        assert entry.user_id == user.user_id
        assert "restored_from" in entry.details

    def test_backup_audit_includes_filename(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        result = svc.create_backup(user)
        session.commit()

        entry = (
            session.query(AuditLog)
            .filter(AuditLog.action == ACTION_BACKUP)
            .first()
        )
        assert entry is not None
        assert entry.details is not None
        assert result.filename in entry.details

    def test_restore_audit_includes_backup_name(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        backup = svc.create_backup(user)
        session.commit()

        svc.restore_backup(user, Path(backup.backup_path))
        session.commit()

        entry = (
            session.query(AuditLog)
            .filter(AuditLog.action == ACTION_RESTORE)
            .first()
        )
        assert entry is not None
        assert backup.filename in entry.details


# -- Edge cases ------------------------------------------------------------ #


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_backup_directory_auto_created(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        new_dir = tmp_path / "new_backups"
        svc = _service(session, db, new_dir)
        assert new_dir.exists()
        result = svc.create_backup(user)
        assert result.success is True

    def test_concurrent_backups_unique_names(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        result1 = svc.create_backup(user)
        result2 = svc.create_backup(user)
        session.commit()
        assert result1.filename != result2.filename

    def test_empty_database_backup(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        result = svc.create_backup(user)
        assert result.success is True
        # Verify backup is valid
        conn = sqlite3.connect(result.backup_path)
        result_check = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        assert result_check == "ok"

    def test_large_database_backup(self, session, tmp_path):
        db = tmp_path / "funmite.db"
        _make_db(db, products=1000)
        user = _admin_user(session)
        svc = _service(session, db, tmp_path / "backups")
        result = svc.create_backup(user)
        assert result.success is True
        conn = sqlite3.connect(result.backup_path)
        rows = conn.execute("SELECT COUNT(*) FROM test").fetchone()[0]
        conn.close()
        assert rows == 1000
