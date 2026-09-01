"""Expenses page: list and record business expenses (Admin only)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import C, F, S, empty_state_message
from app.data.db import session_scope
from app.domain.services.expense_service import ExpenseService
from app.domain.session import CurrentUser
from app.ui.expenses.expense_form import ExpenseFormDialog
from app.utils.formatting import format_money


class ExpensesPage(QWidget):
    """Admin expense management screen."""

    def __init__(self, session_factory, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.session_factory = session_factory
        self.current_user = current_user
        self._expenses = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Expenses", self)
        title.setStyleSheet(f"font-size: {F.SIZE_2XL}; font-weight: {F.WEIGHT_BOLD}; color: {C.FG};")
        layout.addWidget(title)

        subtitle = QLabel("Record and track business expenses", self)
        subtitle.setStyleSheet(f"font-size: {F.SIZE_SM}; color: {C.MUTED_FG}; margin-bottom: 8px;")
        layout.addWidget(subtitle)

        toolbar = QHBoxLayout()
        self.add_button = QPushButton("+ Record Expense")
        self.add_button.setObjectName("btnPrimary")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by category...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(lambda _: self.refresh())
        toolbar.addWidget(self.add_button)
        toolbar.addWidget(QLabel("Category:"))
        toolbar.addWidget(self.search_input, 1)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Category", "Amount", "Description", "Date"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda _: self.edit_selected())
        layout.addWidget(self.table, 1)

        self.empty_label = QLabel("No expenses found. Record your first expense.", self)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(empty_state_message(""))
        self.empty_label.setVisible(False)
        layout.addWidget(self.empty_label)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"color: {C.MUTED_FG};")
        layout.addWidget(self.count_label)

        self.add_button.clicked.connect(self.add_expense)

        self.refresh()

    def refresh(self) -> None:
        category = self.search_input.text().strip() or None
        with session_scope(self.session_factory) as session:
            expenses = ExpenseService(session).list_expenses(
                self.current_user, category=category,
            )
        self._expenses = expenses
        self.table.setRowCount(0)
        total = 0
        for expense in expenses:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for column, value in enumerate(
                [
                    expense.category,
                    format_money(expense.amount),
                    expense.description or "",
                    expense.expense_date.strftime("%d/%m/%Y"),
                ]
            ):
                item = QTableWidgetItem(value)
                if column == 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, column, item)
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, expense.id)
            total += expense.amount
        self.count_label.setText(f"{len(expenses)} expense(s) — Total: {format_money(total)}")
        self.empty_label.setVisible(len(expenses) == 0)

    def _selected(self):
        by_id = {e.id: e for e in self._expenses}
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        for row in sorted(rows):
            expense_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if expense_id in by_id:
                yield by_id[expense_id]

    def add_expense(self) -> None:
        dialog = ExpenseFormDialog(save_handler=self._create_handler())
        if dialog.exec():
            self.refresh()

    def edit_selected(self) -> None:
        selected = list(self._selected())
        if not selected:
            QMessageBox.information(self, "No selection", "Double-click an expense row to edit it.")
            return
        expense = selected[0]
        with self.session_factory() as session:
            fresh = ExpenseService(session).get_expense(self.current_user, expense.id)
        if fresh is None:
            QMessageBox.warning(self, "Not found", "That expense no longer exists.")
            self.refresh()
            return
        dialog = ExpenseFormDialog(
            save_handler=self._update_handler(fresh.id),
            existing=fresh,
        )
        if dialog.exec():
            self.refresh()

    def _create_handler(self):
        def handler(data: dict):
            with session_scope(self.session_factory) as session:
                return ExpenseService(session).create_expense(
                    self.current_user,
                    category=data["category"],
                    amount=data["amount"],
                    description=data["description"],
                    expense_date=data["expense_date"],
                )
        return handler

    def _update_handler(self, expense_id: int):
        def handler(data: dict):
            with session_scope(self.session_factory) as session:
                return ExpenseService(session).update_expense(
                    self.current_user,
                    expense_id,
                    category=data["category"],
                    amount=data["amount"],
                    description=data["description"],
                )
        return handler
