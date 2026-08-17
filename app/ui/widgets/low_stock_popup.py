"""Low-stock popup/notification (Phase 04).

The confirmed rule is ``quantity <= 3``. After any stock-changing operation
(Phase 04: stock-in/adjustment; Phase 05: sales) the UI calls
``show_low_stock_alert`` so the affected products are brought to the user's
attention without needing to open a report.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtWidgets import QMessageBox, QWidget

from app.data.models import Product, LOW_STOCK_THRESHOLD
from app.ui.theme import C, F, S

POPUP_TITLE = "Low Stock Alert"


def low_stock_summary(products: Sequence[Product]) -> str:
    """Human-readable popup body listing the low-stock products."""
    if not products:
        return ""
    lines = [
        f"- {product.name} — {product.quantity} left"
        for product in products
    ]
    return "\n".join(lines)


def show_low_stock_alert(parent: QWidget | None, products: Sequence[Product]) -> bool:
    """Show the low-stock popup. Returns ``True`` if the user chose "View Stock".

    No popup is shown when ``products`` is empty, so callers can invoke this
    unconditionally after a stock change.
    """
    if not products:
        return False
    message = QMessageBox(parent)
    message.setWindowTitle(POPUP_TITLE)
    message.setIcon(QMessageBox.Icon.Warning)
    message.setText(
        f"{len(products)} product(s) are low on stock "
        f"({LOW_STOCK_THRESHOLD} or fewer left):"
    )
    message.setInformativeText(low_stock_summary(products))
    view_button = message.addButton("View Stock", QMessageBox.ButtonRole.AcceptRole)
    message.addButton("Dismiss", QMessageBox.ButtonRole.RejectRole)
    message.exec()
    return message.clickedButton() is view_button
