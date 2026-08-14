"""Application entry point.

Launches the minimal desktop shell. No business features are implemented in
this phase.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

from app import __version__
from app.config import load_settings
from app.logging_config import setup_logging

APP_TITLE = "Funmite POS"


class MainWindow(QMainWindow):
    """Minimal application shell."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(900, 600)

        central = QWidget(self)
        layout = QVBoxLayout(central)

        title = QLabel(APP_TITLE, central)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.setCentralWidget(central)
        self.statusBar().showMessage(f"version {__version__}")


def main() -> int:
    """Run the application and return its exit code."""
    settings = load_settings()
    setup_logging(settings)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
