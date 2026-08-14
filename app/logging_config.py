"""Logging setup.

Configures the root logger with a console handler and a rotating file handler
inside the configured log directory.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from app.config import Settings

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(settings: Settings) -> None:
    """Configure the root logger. Idempotent: resets existing root handlers."""
    settings.ensure_directories()
    level = getattr(logging, settings.log_level, logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(LOG_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        settings.log_dir / "funmite.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
