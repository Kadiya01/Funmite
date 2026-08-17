"""Modal Exchange dialog wrapper (Phase 06).

Wraps the ExchangePage in a QDialog so the POS screen can open it without
managing a full page switch in the QStackedWidget.  Keeps the exchange flow
self-contained and testable.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QPushButton, QVBoxLayout

from app.ui.exchanges.exchange_page import ExchangePage
from app.ui.theme import C, F, S


class ExchangeDialog(QDialog):
    """Modal dialog containing a full ExchangePage."""

    def __init__(self, session_factory, current_user, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Exchange")
        self.resize(720, 560)
        self.setModal(True)
        self.setStyleSheet(f"background-color: {C.BG};")

        layout = QVBoxLayout(self)
        self.page = ExchangePage(session_factory, current_user, parent=self)
        layout.addWidget(self.page)

        self.close_button = QPushButton("Close", self)
        self.close_button.setObjectName("btnSecondary")
        self.close_button.clicked.connect(self.accept)
        layout.addWidget(self.close_button, alignment=Qt.AlignmentFlag.AlignRight)
