"""Application configuration.

Settings are read from environment variables (with an optional ``.env`` file)
and validated through a frozen dataclass.  No secrets should ever live here or
in the committed ``.env.example`` template.

When frozen by PyInstaller, ``PROJECT_ROOT`` resolves to the directory
containing the ``.exe`` so that ``data/``, ``logs/`` and ``backups/`` are
created next to the executable rather than inside the temporary extraction dir.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _frozen_root() -> Path:
    """Return the directory that contains the running executable (or its
    parent for onefile bundles where ``sys.executable`` is the temp dir)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _frozen_root()


def _env_path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    if not value:
        return default
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the application."""

    project_root: Path = PROJECT_ROOT
    data_dir: Path = field(default_factory=lambda: _env_path("FUNMITE_DATA_DIR", PROJECT_ROOT / "data"))
    log_dir: Path = field(default_factory=lambda: _env_path("FUNMITE_LOG_DIR", PROJECT_ROOT / "logs"))
    backup_dir: Path = field(default_factory=lambda: _env_path("FUNMITE_BACKUP_DIR", PROJECT_ROOT / "backups"))
    log_level: str = field(default_factory=lambda: os.getenv("FUNMITE_LOG_LEVEL", "INFO").upper())
    api_host: str = field(default_factory=lambda: os.getenv("FUNMITE_API_HOST", "127.0.0.1"))
    api_port: int = field(default_factory=lambda: _env_int("FUNMITE_API_PORT", 8000))

    # Cloud sync settings (Phase 10C)
    cloud_sync_enabled: bool = field(
        default_factory=lambda: os.getenv("FUNMITE_CLOUD_SYNC", "").lower() in ("1", "true", "yes")
    )
    cloud_db_url: str = field(
        default_factory=lambda: os.getenv("FUNMITE_CLOUD_DB_URL", "sqlite:///cloud.db")
    )
    sync_push_interval: int = field(
        default_factory=lambda: _env_int("FUNMITE_SYNC_PUSH_INTERVAL", 30)
    )
    sync_pull_interval: int = field(
        default_factory=lambda: _env_int("FUNMITE_SYNC_PULL_INTERVAL", 60)
    )

    def ensure_directories(self) -> "Settings":
        """Create the runtime directories (data, logs, backups) if missing."""
        for directory in (self.data_dir, self.log_dir, self.backup_dir):
            directory.mkdir(parents=True, exist_ok=True)
        return self


def load_settings() -> Settings:
    """Load settings from the environment and an optional ``.env`` file."""
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    return Settings()
