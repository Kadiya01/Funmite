"""SQLite engine, sessions, transaction helpers and schema bootstrap.

The local operational database is a single SQLite ``.db`` file. Foreign-key
enforcement is switched on for every connection (SQLite's default is off).
Timestamps are set by the application in shop-local naive time, so the two-day
exchange window and daily reports follow the shop calendar.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.data.migrations import runner

DB_FILENAME = "funmite.db"


def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def create_db_engine(db_path: Path | str) -> Engine:
    """Create a SQLite engine with the required connection pragmas."""
    engine = create_engine(
        f"sqlite:///{Path(db_path).as_posix()}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _set_sqlite_pragmas)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a session factory bound to ``engine``.

    ``expire_on_commit=False`` keeps loaded objects usable after commit, which
    the UI and services rely on when showing just-saved records.
    """
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Open a session, commit on success, roll back on error.

    This is the preferred way for service code to obtain a session when no
    session is already active.
    """
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def transaction(session: Session) -> Iterator[Session]:
    """Commit the current session on success, roll back on error.

    Use inside an already-open session for multi-table work so the caller can
    decide when the unit of work ends.
    """
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise


def database_path(settings) -> Path:
    """Resolve the single operational database file from settings."""
    return settings.data_dir / DB_FILENAME


def initialize_database(settings) -> Engine:
    """Create runtime directories, build the engine and apply migrations."""
    settings.ensure_directories()
    db_path = database_path(settings)
    engine = create_db_engine(db_path)
    runner.upgrade(engine, db_path=db_path, backup_dir=settings.backup_dir)
    return engine


def _cli_usage() -> str:
    return (
        "Funmite POS database utility.\n"
        "\n"
        "This module is NOT the desktop application entry point. Start the\n"
        "application with:\n"
        "    python -m app.main              (development)\n"
        "    dist\\FunmitePOS\\FunmitePOS.exe  (packaged build)\n"
        "\n"
        "Commands:\n"
        "    init      Create or upgrade the database without starting the UI\n"
        "    help      Show this help\n"
    )


def _cli_main(argv: list[str] | None = None) -> int:
    """Handle ``python -m app.data.db [help|init]`` without importing Qt."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(_cli_usage())
        return 0
    if args[0] == "init":
        from app.config import load_settings

        settings = load_settings()
        engine = initialize_database(settings)
        try:
            version = runner.current_version(engine)
        finally:
            engine.dispose()
        print(
            f"Funmite database ready: {database_path(settings)} "
            f"(schema version {version})"
        )
        print(f"Pre-upgrade backups are stored in: {settings.backup_dir}")
        return 0
    print(f"Unknown command: {args[0]}\n")
    print(_cli_usage())
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli_main())
