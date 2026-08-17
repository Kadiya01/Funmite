"""Cloud database engine and session management.

In production the cloud uses PostgreSQL.  For development and tests the cloud
uses SQLite so no external database server is needed.  The ``CLOUD_DB_URL``
environment variable controls which backend is used.

Typical values:
    sqlite:///cloud.db           (file-based dev/test)
    sqlite:///:memory:           (in-memory test)
    postgresql://user:pass@host/funmite_cloud  (production)
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.sync.cloud_models import CloudBase

_DEFAULT_CLOUD_DB = "sqlite:///cloud.db"


def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


def create_cloud_engine(db_url: str | None = None) -> Engine:
    """Create an engine for the cloud database.

    For in-memory SQLite, uses StaticPool so the same connection is shared
    across threads (required by FastAPI TestClient).
    """
    url = db_url or _DEFAULT_CLOUD_DB
    if url == "sqlite:///:memory:":
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(url)
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _set_sqlite_pragmas)
    return engine


def init_cloud_schema(engine: Engine) -> None:
    """Create all cloud tables (idempotent)."""
    CloudBase.metadata.create_all(engine)


def create_cloud_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Return a session factory for the cloud database."""
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def cloud_session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """Open a cloud session, commit on success, roll back on error."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
