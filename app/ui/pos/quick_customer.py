"""Quick customer dialog used at the till (Phase 05).

A customer record is required for every sale, so the Cashier may register a
new walk-in with just a name (phone optional) from the POS screen. The dialog
is deliberately minimal: full customer-record management stays Admin-only.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.data.models import Customer
from app.domain.errors import ValidationError
from app.ui.theme import C, F, S

GENERIC_SAVE_ERROR = "Could not save the customer. Please try again."


class QuickCustomerDialog(QDialog):
    """Modal form to register a customer during a sale (name, optional phone)."""

    def __init__(
        self,
        save_handler: Callable[[dict], Customer],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._save_handler = save_handler
        self.saved: Customer | None = None

        self.setWindowTitle("New Customer")
        self.setModal(True)
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Amina Yusuf")
        form.addRow("Name:", self.name_input)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("e.g. 0803 123 4567 (optional)")
        form.addRow("Phone:", self.phone_input)
        layout.addLayout(form)

        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("btnPrimary")
        self.save_button.setDefault(True)
        self.save_button.setMinimumHeight(40)
        layout.addWidget(self.save_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("btnSecondary")
        layout.addWidget(cancel_button)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet(
            f"color: {C.DESTRUCTIVE}; background-color: {C.DESTRUCTIVE_LIGHT}; "
            f"border-radius: {S.RADIUS_SM}; padding: {S.MD}; font-size: {F.SIZE_SM};"
        )
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        self.save_button.clicked.connect(self._save)
        cancel_button.clicked.connect(self.reject)
        self.name_input.setFocus()

    def values(self) -> dict:
        return {
            "name": self.name_input.text().strip(),
            "phone": self.phone_input.text().strip(),
        }

    def _save(self) -> None:
        data = self.values()
        if not data["name"]:
            self._show_error("Customer name is required.")
            return
        try:
            customer = self._save_handler(data)
        except ValidationError as exc:
            self._show_error(str(exc))
            return
        except Exception:
            self._show_error(GENERIC_SAVE_ERROR)
            return
        self.saved = customer
        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)
