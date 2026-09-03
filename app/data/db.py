"""SQLite engine, sessions, transaction helpers and schema bootstrap.

The local operational database is a single SQLite ``.db`` file. Foreign-key
enforcement is switched on for every connection (SQLite's default is off).
Timestamps are set by the application in shop-local naive time, so the two-day
exchange window and daily reports follow the shop calendar.
"""

from __future__ import annotations

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
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
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
    engine = create_db_engine(database_path(settings))
    runner.upgrade(engine)
    return engine
