"""Versioned schema migration runner.

A small, self-contained alternative to Alembic chosen so the app stays fully
offline, testable and easy to bundle with PyInstaller. Each version module in
``versions/`` exposes an integer ``version`` and ``upgrade(bind)`` /
``downgrade(bind)`` callables. The runner applies missing versions in order,
each inside its own transaction, and records them in the ``schema_version``
table.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from sqlalchemy import Engine, text

META_TABLE = "schema_version"
VERSIONS_DIR = Path(__file__).resolve().parent / "versions"

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


def upgrade(engine: Engine, target: int | None = None) -> int:
    """Apply pending migrations up to ``target`` (default: the latest one).

    Each migration runs inside its own transaction and is recorded only after
    it succeeds.
    """
    _ensure_meta(engine)
    versions = _discover_versions()
    latest = versions[-1][0] if versions else 0
    limit = latest if target is None else min(int(target), latest)
    current = current_version(engine)
    if current >= limit:
        return current

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
    """Revert migrations down to (but not past) ``target``. Test/repair use only."""
    _ensure_meta(engine)
    versions = _discover_versions()
    current = current_version(engine)
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
