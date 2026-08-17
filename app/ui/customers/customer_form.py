"""Add/edit customer dialog (Admin only, see OPEN_DECISIONS).

A customer may be registered without a phone number; the code is generated
automatically when the field is left blank.
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


class CustomerFormDialog(QDialog):
    """Modal form for creating or editing a customer."""

    def __init__(
        self,
        save_handler: Callable[[dict], Customer],
        existing: Customer | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._save_handler = save_handler
        self.existing = existing
        self.saved: Customer | None = None

        self.setWindowTitle("Edit Customer" if existing else "Add Customer")
        self.setModal(True)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Amina Yusuf")
        form.addRow("Name:", self.name_input)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("e.g. 0803 123 4567 (optional)")
        form.addRow("Phone:", self.phone_input)

        self.address_input = QLineEdit()
        self.address_input.setPlaceholderText("e.g. No. 79 NAK Plaza, Kano (optional)")
        form.addRow("Address:", self.address_input)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Leave blank to auto-generate")
        form.addRow("Customer Code:", self.code_input)

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
            f"color: {C.DESTRUCTIVE}; background: {C.DESTRUCTIVE_LIGHT}; "
            f"border-radius: {S.RADIUS_SM}; padding: 8px;"
        )
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        self.save_button.clicked.connect(self._save)
        cancel_button.clicked.connect(self.reject)

        if existing is not None:
            self._populate(existing)

    def _populate(self, customer: Customer) -> None:
        self.name_input.setText(customer.name)
        self.phone_input.setText(customer.phone or "")
        self.address_input.setText(customer.address or "")
        self.code_input.setText(customer.customer_code)

    def values(self) -> dict:
        return {
            "name": self.name_input.text().strip(),
            "phone": self.phone_input.text().strip(),
            "address": self.address_input.text().strip(),
            "customer_code": self.code_input.text().strip(),
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
