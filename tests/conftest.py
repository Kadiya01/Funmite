"""Shared test fixtures."""

from __future__ import annotations

import os

import pytest

from app.config import load_settings
from app.data.db import create_db_engine, create_session_factory
from app.data.migrations import runner

ENV_OVERRIDES = ("FUNMITE_DATA_DIR", "FUNMITE_LOG_DIR", "FUNMITE_BACKUP_DIR")


@pytest.fixture
def settings(tmp_path):
    """Settings pointing at an isolated temporary directory."""
    for name, sub in zip(ENV_OVERRIDES, ("data", "logs", "backups")):
        os.environ[name] = str(tmp_path / sub)
    try:
        yield load_settings()
    finally:
        for name in ENV_OVERRIDES:
            os.environ.pop(name, None)


@pytest.fixture
def db_path(tmp_path):
    """Path to a fresh, empty database file for this test."""
    return tmp_path / "funmite_test.db"


@pytest.fixture
def engine(db_path):
    """Engine over a freshly migrated database."""
    eng = create_db_engine(db_path)
    runner.upgrade(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    return create_session_factory(engine)


@pytest.fixture
def session(session_factory):
    """An open session. Changes must be committed explicitly by the test."""
    with session_factory() as s:
        yield s
