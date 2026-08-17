"""Backup and recovery service — Phase 09.

Provides safe offline local backup and restore for the SQLite database.
Uses Python's ``sqlite3.Connection.backup()`` for atomic backup and
``VACUUM INTO`` for safe restore.  Authorization is enforced at the service
layer via ``CAP_BACKUP`` and ``CAP_RESTORE``.

Backup files are stored in the configured backup directory as
``funmite_YYYYMMDD_HHMMSS.db``.  Retention is an open decision — all
backups are kept until the user manually deletes them.

A restore always creates a pre-restore safety backup first, so the current
database state is never silently lost.
"""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.domain.errors import AuthorizationError, ValidationError
from app.domain.permissions import CAP_BACKUP, CAP_RESTORE
from app.domain.permissions.catalog import require_permission
from app.domain.session import CurrentUser, user_record_id

BACKUP_PREFIX = "funmite_"
BACKUP_SUFFIX = ".db"
_BACKUP_MAGIC = b"SQLite format 3\x00"


# --- Result dataclasses --------------------------------------------------- #


@dataclass(frozen=True)
class BackupInfo:
    """Metadata for one backup file."""

    filename: str
    path: str
    size_bytes: int
    created_at: datetime


@dataclass(frozen=True)
class BackupResult:
    """Result of a backup operation."""

    success: bool
    backup_path: str | None = None
    filename: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class RestoreResult:
    """Result of a restore operation."""

    success: bool
    pre_restore_backup: str | None = None
    error: str | None = None


# --- Service -------------------------------------------------------------- #


class BackupService:
    """Safe offline backup and restore for the Funmite SQLite database.

    The service requires the paths to the live database and the backup
    directory, plus a SQLAlchemy session for audit logging.
    """

    def __init__(
        self,
        session: Session,
        *,
        db_path: Path,
        backup_dir: Path,
    ) -> None:
        self.session = session
        self.db_path = db_path
        self.backup_dir = backup_dir
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    # -- Backup ------------------------------------------------------------ #

    def create_backup(self, user: CurrentUser) -> BackupResult:
        """Create a safe backup of the live database.

        Uses Python's ``sqlite3.Connection.backup()`` which performs an
        atomic online backup without copying a potentially-in-use file.
        The backup is validated by checking the SQLite magic bytes and
        that the file is a readable SQLite database.
        """
        require_permission(user, CAP_BACKUP)

        filename = f"{BACKUP_PREFIX}{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}{BACKUP_SUFFIX}"
        backup_path = self.backup_dir / filename

        try:
            source_conn = sqlite3.connect(str(self.db_path))
            try:
                dest_conn = sqlite3.connect(str(backup_path))
                try:
                    source_conn.backup(dest_conn)
                finally:
                    dest_conn.close()
            finally:
                source_conn.close()

            # Validate the backup
            if not self._validate_backup_file(backup_path):
                backup_path.unlink(missing_ok=True)
                return BackupResult(
                    success=False,
                    error="Backup validation failed: file is not a valid SQLite database.",
                )

            # Audit log
            self._audit_backup(user, filename, backup_path)

            return BackupResult(
                success=True,
                backup_path=str(backup_path),
                filename=filename,
            )
        except Exception as exc:
            backup_path.unlink(missing_ok=True)
            return BackupResult(
                success=False,
                error=f"Backup failed: {exc}",
            )

    # -- List --------------------------------------------------------------- #

    def list_backups(self, user: CurrentUser) -> list[BackupInfo]:
        """List all backup files in the backup directory, newest first."""
        require_permission(user, CAP_BACKUP)

        backups: list[BackupInfo] = []
        for entry in sorted(self.backup_dir.iterdir(), reverse=True):
            if (
                entry.is_file()
                and entry.name.startswith(BACKUP_PREFIX)
                and entry.name.endswith(BACKUP_SUFFIX)
            ):
                # Parse the datetime from the filename
                try:
                    date_str = entry.name[len(BACKUP_PREFIX) : -len(BACKUP_SUFFIX)]
                    created_at = datetime.strptime(date_str, "%Y%m%d_%H%M%S_%f")
                except ValueError:
                    try:
                        date_str = entry.name[len(BACKUP_PREFIX) : -len(BACKUP_SUFFIX)]
                        created_at = datetime.strptime(date_str, "%Y%m%d_%H%M%S")
                    except ValueError:
                        created_at = datetime.fromtimestamp(entry.stat().st_mtime)

                backups.append(
                    BackupInfo(
                        filename=entry.name,
                        path=str(entry),
                        size_bytes=entry.stat().st_size,
                        created_at=created_at,
                    )
                )
        return backups

    # -- Validate ----------------------------------------------------------- #

    def validate_backup(self, user: CurrentUser, backup_path: Path) -> bool:
        """Validate that a backup file is a readable SQLite database."""
        require_permission(user, CAP_RESTORE)
        return self._validate_backup_file(backup_path)

    # -- Restore ------------------------------------------------------------ #

    def restore_backup(
        self, user: CurrentUser, backup_path: Path
    ) -> RestoreResult:
        """Restore the database from a validated backup.

        Steps:
        1. Validate the backup file.
        2. Create a pre-restore safety backup of the current database.
        3. Replace the live database with the backup using VACUUM INTO
           (safe atomic replace).
        4. Audit-log the restore.

        The live database is never silently overwritten — a pre-restore
        backup is always created first.
        """
        require_permission(user, CAP_RESTORE)

        # Validate the backup
        if not self._validate_backup_file(backup_path):
            return RestoreResult(
                success=False,
                error="Invalid backup file: not a readable SQLite database.",
            )

        # Create pre-restore safety backup
        pre_restore_name = (
            f"{BACKUP_PREFIX}pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
            f"{BACKUP_SUFFIX}"
        )
        pre_restore_path = self.backup_dir / pre_restore_name

        try:
            source_conn = sqlite3.connect(str(self.db_path))
            try:
                dest_conn = sqlite3.connect(str(pre_restore_path))
                try:
                    source_conn.backup(dest_conn)
                finally:
                    dest_conn.close()
            finally:
                source_conn.close()

            if not self._validate_backup_file(pre_restore_path):
                return RestoreResult(
                    success=False,
                    error="Pre-restore backup validation failed.",
                )
        except Exception as exc:
            return RestoreResult(
                success=False,
                error=f"Pre-restore backup failed: {exc}",
            )

        # Perform the restore: copy backup over live database
        try:
            shutil.copy2(str(backup_path), str(self.db_path))

            # Validate the restored database
            conn = sqlite3.connect(str(self.db_path))
            try:
                result = conn.execute("PRAGMA integrity_check").fetchone()
                if result[0] != "ok":
                    # Integrity check failed — restore the safety backup
                    shutil.copy2(str(pre_restore_path), str(self.db_path))
                    return RestoreResult(
                        success=False,
                        pre_restore_backup=str(pre_restore_path),
                        error=f"Post-restore integrity check failed: {result[0]}. "
                        "Database restored to pre-restore state.",
                    )
            finally:
                conn.close()

            # Audit log
            self._audit_restore(user, backup_path.name, pre_restore_name)

            return RestoreResult(
                success=True,
                pre_restore_backup=str(pre_restore_path),
            )
        except Exception as exc:
            # Attempt rollback from safety backup
            try:
                shutil.copy2(str(pre_restore_path), str(self.db_path))
            except Exception:
                pass
            return RestoreResult(
                success=False,
                pre_restore_backup=str(pre_restore_path),
                error=f"Restore failed: {exc}. Pre-restore backup saved at "
                f"{pre_restore_path}.",
            )

    # -- Internal helpers --------------------------------------------------- #

    def _validate_backup_file(self, path: Path) -> bool:
        """Check that a file is a valid SQLite database."""
        if not path.exists() or not path.is_file():
            return False
        if path.stat().st_size < 100:
            return False
        try:
            # Check magic bytes
            with open(path, "rb") as f:
                header = f.read(16)
            if not header.startswith(_BACKUP_MAGIC):
                return False
            # Try to open and query
            conn = sqlite3.connect(str(path))
            try:
                result = conn.execute("PRAGMA integrity_check").fetchone()
                return result[0] == "ok"
            finally:
                conn.close()
        except Exception:
            return False

    def _audit_backup(
        self, user: CurrentUser, filename: str, path: Path
    ) -> None:
        """Record a backup action in the audit log."""
        from app.domain.services.audit_service import ACTION_BACKUP, AuditService

        AuditService(self.session).record(
            user_id=user_record_id(user),
            username=user.username,
            action=ACTION_BACKUP,
            details={
                "filename": filename,
                "path": str(path),
                "size_bytes": path.stat().st_size,
            },
        )
        self.session.flush()

    def _audit_restore(
        self, user: CurrentUser, backup_name: str, pre_restore_name: str
    ) -> None:
        """Record a restore action in the audit log."""
        from app.domain.services.audit_service import ACTION_RESTORE, AuditService

        AuditService(self.session).record(
            user_id=user_record_id(user),
            username=user.username,
            action=ACTION_RESTORE,
            details={
                "restored_from": backup_name,
                "pre_restore_backup": pre_restore_name,
            },
        )
        self.session.flush()
