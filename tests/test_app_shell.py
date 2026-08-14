"""Application shell smoke tests (Qt)."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from app import __version__
from app.main import APP_TITLE, MainWindow


def test_main_window_creates(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == APP_TITLE
    assert window.isVisible() is False
    assert f"version {__version__}" in window.statusBar().currentMessage()


def test_application_singleton(qtbot):
    assert QApplication.instance() is not None
