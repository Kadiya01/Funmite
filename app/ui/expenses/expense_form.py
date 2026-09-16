"""Add/edit expense dialog (Admin only)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.ui.theme import C, F, S
from app.data.models import Expense
from app.domain.errors import ValidationError
from app.domain.services.expense_service import (
    OTHER_CATEGORY_LABEL,
    STANDARD_EXPENSE_CATEGORIES,
)
from app.utils.formatting import format_money

GENERIC_SAVE_ERROR = "Could not save the expense. Please try again."
_CATEGORY_PROMPT = "-- Select category --"


class ExpenseFormDialog(QDialog):
    """Modal form for creating or editing an expense."""

    def __init__(
        self,
        save_handler: Callable[[dict], Expense],
        existing: Expense | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._save_handler = save_handler
        self.existing = existing
        self.saved: Expense | None = None

        self.setWindowTitle("Edit Expense" if existing else "Record Expense")
        self.setModal(True)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()

        self.category_combo = QComboBox()
        self.category_combo.addItem(_CATEGORY_PROMPT, None)
        for category in STANDARD_EXPENSE_CATEGORIES:
            display = f"{OTHER_CATEGORY_LABEL}…" if category == OTHER_CATEGORY_LABEL else category
            self.category_combo.addItem(display, category)
        self.other_input = QLineEdit()
        self.other_input.setPlaceholderText("Type the expense category")
        self.other_input.setVisible(False)
        self.category_combo.currentIndexChanged.connect(self._toggle_other_field)
        form.addRow("Category:", self.category_combo)
        form.addRow("", self.other_input)

        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("e.g. 5000")
        form.addRow("Amount:", self.amount_input)

        self.description_input = QLineEdit()
        self.description_input.setPlaceholderText("Optional description")
        form.addRow("Description:", self.description_input)

        self.date_input = QLineEdit()
        self.date_input.setPlaceholderText("DD/MM/YYYY (defaults to today)")
        self.date_input.setText(datetime.now().strftime("%d/%m/%Y"))
        form.addRow("Date:", self.date_input)

        layout.addLayout(form)

        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("btnPrimary")
        self.save_button.setDefault(True)
        self.save_button.setMinimumHeight(44)
        layout.addWidget(self.save_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("btnSecondary")
        layout.addWidget(cancel_button)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet(
            f"color: {C.DESTRUCTIVE}; background-color: {C.DESTRUCTIVE_LIGHT}; border-radius: {S.RADIUS_SM}; padding: 8px;"
        )
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        self.save_button.clicked.connect(self._save)
        cancel_button.clicked.connect(self.reject)

        if existing is not None:
            self._populate(existing)

    def _populate(self, expense: Expense) -> None:
        self._select_category(expense.category or "")
        self.amount_input.setText(str(expense.amount))
        self.description_input.setText(expense.description or "")
        self.date_input.setText(expense.expense_date.strftime("%d/%m/%Y"))

    def _select_category(self, category: str) -> None:
        if category and category != OTHER_CATEGORY_LABEL:
            index = self.category_combo.findData(category)
            if index >= 0:
                self.category_combo.setCurrentIndex(index)
                return
        other_index = self.category_combo.findData(OTHER_CATEGORY_LABEL)
        self.category_combo.setCurrentIndex(other_index)
        self.other_input.setText(category)
        self.other_input.setVisible(True)

    def _toggle_other_field(self) -> None:
        is_other = self.category_combo.currentData() == OTHER_CATEGORY_LABEL
        self.other_input.setVisible(is_other)
        if not is_other:
            self.other_input.clear()

    def _selected_category(self) -> str:
        selected = self.category_combo.currentData()
        if selected is None:
            return ""
        if selected == OTHER_CATEGORY_LABEL:
            return self.other_input.text().strip()
        return selected

    def values(self) -> dict:
        return {
            "category": self._selected_category(),
            "amount": self.amount_input.text().strip(),
            "description": self.description_input.text().strip(),
            "date": self.date_input.text().strip(),
        }

    def _parse_date(self, text: str) -> datetime:
        try:
            return datetime.strptime(text, "%d/%m/%Y")
        except ValueError:
            raise ValidationError("Date must be in DD/MM/YYYY format.") from None

    def _save(self) -> None:
        data = self.values()
        if not data["category"]:
            self._show_error("Expense category is required.")
            return
        if not data["amount"]:
            self._show_error("Amount is required.")
            return
        try:
            expense_date = self._parse_date(data["date"])
        except ValidationError as exc:
            self._show_error(str(exc))
            return
        try:
            expense = self._save_handler({
                "category": data["category"],
                "amount": data["amount"],
                "description": data["description"] or None,
                "expense_date": expense_date,
            })
        except ValidationError as exc:
            self._show_error(str(exc))
            return
        except Exception:
            self._show_error(GENERIC_SAVE_ERROR)
            return
        self.saved = expense
        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)
