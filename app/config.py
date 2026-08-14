"""Application configuration.

Settings are read from environment variables (with an optional ``.env`` file)
and validated through a frozen dataclass. No secrets should ever live here or
in the committed ``.env.example`` template.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


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

    def ensure_directories(self) -> "Settings":
        """Create the runtime directories (data, logs, backups) if missing."""
        for directory in (self.data_dir, self.log_dir, self.backup_dir):
            directory.mkdir(parents=True, exist_ok=True)
        return self


def load_settings() -> Settings:
    """Load settings from the environment and an optional ``.env`` file."""
    load_dotenv(PROJECT_ROOT / ".env")
    return Settings()
