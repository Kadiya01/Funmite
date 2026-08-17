"""Popup dialogs used by the POS screen (Phase 05).

Each popup is a plain function so the page can inject a fake in tests. The
wireframe popup table drives the choices:

- Sale Complete: Print / Reprint / New Sale
- Insufficient Stock: Reduce Quantity / Cancel
- Barcode Not Found: Search / Add Product (Admin only)
- Low-stock note after a sale (the full View Stock list is Admin-only)
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from app.data.models import Product
from app.ui.theme import C, F, S


def show_sale_complete(parent, receipt_no: str, printed: bool) -> str:
    """Ask what to do after a successful sale. Returns ``"print"`` or ``"new"``."""
    box = QMessageBox(parent)
    box.setWindowTitle("Sale Complete")
    box.setIcon(QMessageBox.Icon.Information)
    status = (
        "The receipt has been printed."
        if printed
        else "The sale is saved, but the receipt could not be printed.\nUse Reprint when the printer is ready."
    )
    box.setText(f"Sale {receipt_no} completed.\n\n{status}")
    box.addButton("Print", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Reprint", QMessageBox.ButtonRole.AcceptRole)
    new_button = box.addButton("New Sale", QMessageBox.ButtonRole.DestructiveRole)
    box.setDefaultButton(new_button)
    box.exec()
    return "new" if box.clickedButton() is new_button else "print"


def show_insufficient_stock(parent, message: str) -> bool:
    """Insufficient-stock popup. Returns True when the user chose Reduce Quantity."""
    box = QMessageBox(parent)
    box.setWindowTitle("Insufficient Stock")
    box.setIcon(QMessageBox.Icon.Warning)
    box.setText(message)
    reduce_button = box.addButton("Reduce Quantity", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(reduce_button)
    box.exec()
    return box.clickedButton() is reduce_button


def show_barcode_not_found(parent, barcode: str, *, can_add: bool) -> str:
    """Barcode-not-found popup. Returns ``"add"`` or ``"dismiss"``."""
    box = QMessageBox(parent)
    box.setWindowTitle("Barcode Not Found")
    box.setIcon(QMessageBox.Icon.Information)
    box.setText(f"No product has barcode '{barcode}'.")
    if can_add:
        add_button = box.addButton("Add Product", QMessageBox.ButtonRole.AcceptRole)
    close_button = box.addButton("Close", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(close_button)
    box.exec()
    if can_add and box.clickedButton() is add_button:
        return "add"
    return "dismiss"


def show_low_stock_note(parent, products: list[Product]) -> None:
    """Note after a sale when a sold product is now at the low-stock level."""
    if not products:
        return
    lines = [f"{product.name} — {product.quantity} left" for product in products]
    QMessageBox.information(
        parent,
        "Low Stock",
        "These sold products are now low on stock (3 or fewer):\n\n" + "\n".join(lines),
    )
