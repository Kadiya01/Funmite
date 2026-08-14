"""Logging setup tests."""

from __future__ import annotations

import logging

from app.logging_config import setup_logging


def test_setup_logging_creates_log_file(settings):
    setup_logging(settings)
    assert (settings.log_dir / "funmite.log").is_file()


def test_setup_logging_is_idempotent(settings):
    setup_logging(settings)
    root = logging.getLogger()
    handler_count = len(root.handlers)
    setup_logging(settings)
    assert len(root.handlers) == handler_count


def test_messages_are_written(settings):
    setup_logging(settings)
    logger = logging.getLogger("funmite.test")
    logger.info("foundation smoke message")
    content = (settings.log_dir / "funmite.log").read_text(encoding="utf-8")
    assert "foundation smoke message" in content
