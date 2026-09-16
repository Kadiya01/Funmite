"""UI tests for the expense form dialog (dropdown + free-text Other)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from app.ui.expenses.expense_form import (
    OTHER_CATEGORY_LABEL,
    STANDARD_EXPENSE_CATEGORIES,
    ExpenseFormDialog,
)


def _noop_save(data):
    return SimpleNamespace(**data)


def _expense_stub(category="Transport", amount=5000, description=None):
    return SimpleNamespace(
        category=category,
        amount=Decimal(str(amount)),
        description=description,
        expense_date=datetime(2026, 3, 15),
    )


class TestExpenseFormDropdown:
    def test_standard_categories_present(self, qtbot):
        dialog = ExpenseFormDialog(_noop_save)
        qtbot.addWidget(dialog)
        dialog.show()

        display_items = [
            dialog.category_combo.itemText(i) for i in range(dialog.category_combo.count())
        ]
        assert "-- Select category --" in display_items
        for cat in STANDARD_EXPENSE_CATEGORIES:
            assert cat in display_items or f"{cat}…" in display_items
        assert f"{OTHER_CATEGORY_LABEL}…" in display_items

    def test_default_is_prompt(self, qtbot):
        dialog = ExpenseFormDialog(_noop_save)
        qtbot.addWidget(dialog)
        dialog.show()

        assert dialog.category_combo.currentText() == "-- Select category --"
        assert dialog.other_input.isHidden()

    def test_selecting_other_shows_free_text_field(self, qtbot):
        dialog = ExpenseFormDialog(_noop_save)
        qtbot.addWidget(dialog)
        dialog.show()

        dialog.category_combo.setCurrentIndex(dialog.category_combo.findData(OTHER_CATEGORY_LABEL))
        assert dialog.other_input.isVisible()

    def test_deselecting_other_hides_and_clears_free_text(self, qtbot):
        dialog = ExpenseFormDialog(_noop_save)
        qtbot.addWidget(dialog)
        dialog.show()

        dialog.category_combo.setCurrentIndex(dialog.category_combo.findData(OTHER_CATEGORY_LABEL))
        dialog.other_input.setText("Custom")
        dialog.category_combo.setCurrentIndex(1)  # first standard item

        assert dialog.other_input.isHidden()
        assert dialog.other_input.text() == ""

    def test_category_required_when_prompt_selected(self, qtbot):
        dialog = ExpenseFormDialog(_noop_save)
        qtbot.addWidget(dialog)
        dialog.show()

        dialog.amount_input.setText("1000")
        dialog.save_button.click()

        assert dialog.error_label.isVisible()
        assert "category" in dialog.error_label.text().lower()

    def test_other_empty_blocks_save(self, qtbot):
        dialog = ExpenseFormDialog(_noop_save)
        qtbot.addWidget(dialog)
        dialog.show()

        dialog.category_combo.setCurrentIndex(dialog.category_combo.findData(OTHER_CATEGORY_LABEL))
        dialog.amount_input.setText("1000")
        dialog.save_button.click()

        assert dialog.error_label.isVisible()
        assert "category" in dialog.error_label.text().lower()

    def test_other_category_passes_free_text(self, qtbot):
        dialog = ExpenseFormDialog(_noop_save)
        qtbot.addWidget(dialog)
        dialog.show()

        dialog.category_combo.setCurrentIndex(dialog.category_combo.findData(OTHER_CATEGORY_LABEL))
        dialog.other_input.setText("Security")
        dialog.amount_input.setText("2000")
        dialog.date_input.setText("15/03/2026")
        dialog.save_button.click()

        assert dialog.accepted
        assert dialog.saved is not None
        assert dialog.saved.category == "Security"

    def test_standard_category_passes_selected_value(self, qtbot):
        dialog = ExpenseFormDialog(_noop_save)
        qtbot.addWidget(dialog)
        dialog.show()

        rent_index = dialog.category_combo.findData("Rent")
        dialog.category_combo.setCurrentIndex(rent_index)
        dialog.amount_input.setText("50000")
        dialog.date_input.setText("15/03/2026")
        dialog.save_button.click()

        assert dialog.accepted
        assert dialog.saved.category == "Rent"


class TestExpenseFormPrefill:
    def test_prefill_standard_category(self, qtbot):
        dialog = ExpenseFormDialog(_noop_save, existing=_expense_stub(category="Utilities"))
        qtbot.addWidget(dialog)
        dialog.show()

        assert dialog.category_combo.currentData() == "Utilities"
        assert dialog.other_input.isHidden()

    def test_prefill_custom_category(self, qtbot):
        dialog = ExpenseFormDialog(_noop_save, existing=_expense_stub(category="Security"))
        qtbot.addWidget(dialog)
        dialog.show()

        assert dialog.category_combo.currentData() == OTHER_CATEGORY_LABEL
        assert dialog.other_input.isVisible()
        assert dialog.other_input.text() == "Security"

    def test_prefill_other_label_category(self, qtbot):
        dialog = ExpenseFormDialog(_noop_save, existing=_expense_stub(category=OTHER_CATEGORY_LABEL))
        qtbot.addWidget(dialog)
        dialog.show()

        assert dialog.category_combo.currentData() == OTHER_CATEGORY_LABEL
        assert dialog.other_input.isVisible()
        assert dialog.other_input.text() == OTHER_CATEGORY_LABEL