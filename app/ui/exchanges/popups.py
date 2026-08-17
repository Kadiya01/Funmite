"""Popup dialogs used by the Exchange screen (Phase 06).

Each popup is a plain function so the page can inject a fake in tests.
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from app.ui.theme import C, F, S


def show_exchange_confirmation(parent, receipt_no: str, summary: str) -> bool:
    """Ask the Admin to confirm the exchange before it is committed.

    Returns ``True`` when the user chose Confirm, ``False`` for Cancel.
    """
    box = QMessageBox(parent)
    box.setWindowTitle("Exchange Confirmation")
    box.setIcon(QMessageBox.Icon.Question)
    box.setText(
        f"Complete the exchange for receipt {receipt_no}?\n\n{summary}"
    )
    confirm = box.addButton("Confirm", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(confirm)
    box.exec()
    return box.clickedButton() is confirm


def show_exchange_complete(parent, receipt_no: str) -> None:
    """Inform the Admin that the exchange has been recorded."""
    QMessageBox.information(
        parent,
        "Exchange Complete",
        f"Exchange for receipt {receipt_no} completed successfully.",
    )
