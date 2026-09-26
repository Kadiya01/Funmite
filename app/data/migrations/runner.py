"""Versioned schema migration runner.

A small, self-contained alternative to Alembic chosen so the app stays fully
offline, testable and easy to bundle with PyInstaller. Each version module in
``versions/`` exposes an integer ``version`` and ``upgrade(bind)`` /
``downgrade(bind)`` callables. The runner applies missing versions in order,
each inside its own transaction, and records them in the ``schema_version``
table.

Safety:
- ``upgrade`` creates an automatic WAL-safe pre-upgrade backup (the same
  ``sqlite3.Connection.backup()`` mechanism and ``funmite_*`` naming the
  BackupService uses) into ``backup_dir`` before applying any pending
  migration. No backup is made when the database file does not exist yet.
- Both ``upgrade`` and ``downgrade`` refuse to run when the database schema
  version is newer than this build's latest known migration
  (``NewerSchemaError``): a newer database must only be opened by a newer
  build, never downgraded or migrated by an older one.
- Table rebuilds (e.g. migration 005, needed to change a CHECK constraint)
  run on a dedicated AUTOCOMMIT connection and are inherently NON-ATOMIC.
  The pre-upgrade backup is the recovery mechanism; a later re-run is safe
  because each rebuild is individually idempotent and starts by dropping its
  ``<table>_migN`` staging table.
"""

from __future__ import annotations

import importlib
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, text

META_TABLE = "schema_version"
VERSIONS_DIR = Path(__file__).resolve().parent / "versions"

# Filename convention mirrors app.domain.services.backup_service so pre-migration
# backups land in the same scan/retention as manual ones.
_BACKUP_PREFIX = "funmite_"
_BACKUP_SUFFIX = ".db"


class NewerSchemaError(RuntimeError):
    """The database was last opened by a newer build than this one.

    Migrating against a schema this build does not know is unsafe, so the
    runner refuses to proceed. The operator must open the database with a
    newer Funmite build or restore a backup.
    """

    def __init__(self, db_version: int, app_version: int) -> None:
        self.db_version = db_version
        self.app_version = app_version
        super().__init__(
            f"Database schema version {db_version} is newer than the latest "
            f"known schema version ({app_version}) of this application build. "
            "Open this database with a newer Funmite build, or restore a "
            "backup from the backups folder."
        )


_CREATE_META = f"""
CREATE TABLE IF NOT EXISTS {META_TABLE} (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def _ensure_meta(bind) -> None:
    with bind.begin() as connection:
        connection.exec_driver_sql(_CREATE_META)


def _backup_before_upgrade(
    engine: Engine,
    *,
    db_path: Path | None = None,
    backup_dir: Path | None = None,
) -> Path | None:
    """Create a WAL-safe pre-upgrade backup of the local SQLite database.

    Uses ``sqlite3.Connection.backup()`` (atomic, online, WAL-aware) and the
    same ``funmite_YYYYMMDD_HHMMSS_<hex>`` naming as the BackupService, so the
    file enters the normal backup retention. Returns the backup path, or
    ``None`` when there is nothing to protect (in-memory engine or the
    database file does not exist yet).
    """
    path = Path(db_path) if db_path is not None else None
    if path is None:
        url_database = getattr(engine.url, "database", None)
        if url_database in (None, "", ":memory:"):
            return None
        path = Path(url_database)
    if not path.is_file():
        return None

    target_dir = Path(backup_dir) if backup_dir is not None else path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = (
        f"{_BACKUP_PREFIX}{datetime.now().strftime('%Y%m%d_%H%M%S')}_"
        f"{uuid.uuid4().hex[:8]}{_BACKUP_SUFFIX}"
    )
    dest = target_dir / filename
    try:
        source = sqlite3.connect(str(path))
        try:
            target = sqlite3.connect(str(dest))
            try:
                source.backup(target)
            finally:
                target.close()
        finally:
            source.close()
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return dest


def _discover_versions() -> list[tuple[int, str, object, object]]:
    """Load every version module from ``versions/`` sorted by version number."""
    discovered = []
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        if path.name.startswith("__"):
            continue
        module_name = f"{__package__}.versions.{path.stem}"
        module = importlib.import_module(module_name)
        discovered.append(
            (int(module.version), str(module.name), module.upgrade, module.downgrade)
        )
    discovered.sort(key=lambda item: item[0])
    return discovered


def current_version(engine: Engine) -> int:
    """Return the highest applied migration version (0 when none)."""
    _ensure_meta(engine)
    with engine.connect() as connection:
        row = connection.execute(
            text(f"SELECT COALESCE(MAX(version), 0) FROM {META_TABLE}")
        ).scalar()
    return int(row)


def upgrade(
    engine: Engine,
    target: int | None = None,
    *,
    db_path: Path | None = None,
    backup_dir: Path | None = None,
) -> int:
    """Apply pending migrations up to ``target`` (default: the latest one).

    Each migration runs inside its own transaction and is recorded only after
    it succeeds. Before any pending migration is applied, a pre-upgrade backup
    is created (see ``_backup_before_upgrade``). Raises ``NewerSchemaError``
    when the database schema version is newer than this build's latest
    migration, and refuses to touch the database in that case.
    """
    _ensure_meta(engine)
    versions = _discover_versions()
    latest = versions[-1][0] if versions else 0
    limit = latest if target is None else min(int(target), latest)
    current = current_version(engine)
    if current > latest:
        raise NewerSchemaError(current, latest)
    if current >= limit:
        return current

    _backup_before_upgrade(engine, db_path=db_path, backup_dir=backup_dir)

    with engine.begin() as connection:
        for version, name, upgrade_fn, _ in versions:
            if version <= current:
                continue
            if version > limit:
                break
            upgrade_fn(connection)
            connection.execute(
                text(f"INSERT INTO {META_TABLE} (version, name) VALUES (:v, :n)"),
                {"v": version, "n": name},
            )
    return limit


def downgrade(engine: Engine, target: int = 0) -> None:
    """Revert migrations down to (but not past) ``target``. Test/repair use only.

    Refuses to run against a database newer than this build's latest
    migration (``NewerSchemaError``).
    """
    _ensure_meta(engine)
    versions = _discover_versions()
    latest = versions[-1][0] if versions else 0
    current = current_version(engine)
    if current > latest:
        raise NewerSchemaError(current, latest)
    if current <= target:
        return

    with engine.begin() as connection:
        for version, name, _, downgrade_fn in reversed(versions):
            if version > current:
                continue
            if version <= target:
                break
            downgrade_fn(connection)
            connection.execute(
                text(f"DELETE FROM {META_TABLE} WHERE version = :v"),
                {"v": version},
            )
