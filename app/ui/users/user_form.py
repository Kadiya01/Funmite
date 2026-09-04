"""Add Cashier / edit Cashier dialog (Admin only).

The role is always ``ROLE_CASHIER`` — there is deliberately no role selector,
so this form can never mint another Admin. A password is only required when
creating a new account; editing keeps the existing password.
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

from app.data.models import User
from app.domain.errors import ValidationError
from app.ui.theme import C, F, S

GENERIC_SAVE_ERROR = "Could not save the user. Please try again."


class UserFormDialog(QDialog):
    """Modal form for creating or editing a Cashier account."""

    def __init__(
        self,
        save_handler: Callable[[dict], User],
        existing: User | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._save_handler = save_handler
        self.existing = existing
        self.saved: User | None = None

        self.setWindowTitle("Edit Cashier" if existing else "Add Cashier")
        self.setModal(True)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        role_hint = QLabel("Accounts are created as Cashier (Admin accounts cannot be created here).")
        role_hint.setStyleSheet(f"font-size: {F.SIZE_SM}; color: {C.MUTED_FG};")
        role_hint.setWordWrap(True)
        layout.addWidget(role_hint)

        form = QFormLayout()

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("e.g. kasuwa2")
        self.username_input.setReadOnly(existing is not None)
        form.addRow("Username:", self.username_input)

        self.full_name_input = QLineEdit()
        self.full_name_input.setPlaceholderText("e.g. Amina Bello")
        form.addRow("Full name:", self.full_name_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText(
            "Minimum 6 characters" if existing is None else "Leave blank to keep current"
        )
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setEnabled(existing is None)
        form.addRow("Password:", self.password_input)

        layout.addLayout(form)

        save_button = QPushButton("Save")
        save_button.setObjectName("btnPrimary")
        save_button.setDefault(True)
        save_button.setMinimumHeight(44)
        layout.addWidget(save_button)

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

        save_button.clicked.connect(self._save)
        cancel_button.clicked.connect(self.reject)

        if existing is not None:
            self._populate(existing)

    def _populate(self, user: User) -> None:
        self.username_input.setText(user.username)
        self.full_name_input.setText(user.full_name)

    def values(self) -> dict:
        return {
            "username": self.username_input.text().strip(),
            "full_name": self.full_name_input.text().strip(),
            "password": self.password_input.text(),
        }

    def _save(self) -> None:
        data = self.values()
        if self.existing is None and not data["username"]:
            self._show_error("Username is required.")
            return
        if not data["full_name"]:
            self._show_error("Full name is required.")
            return
        if self.existing is None and not data["password"]:
            self._show_error("Password is required.")
            return
        try:
            user = self._save_handler(data)
        except ValidationError as exc:
            self._show_error(str(exc))
            return
        except Exception:
            self._show_error(GENERIC_SAVE_ERROR)
            return
        self.saved = user
        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)
