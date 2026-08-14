"""Shared test fixtures."""

from __future__ import annotations

import os

import pytest

from app.config import load_settings

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
