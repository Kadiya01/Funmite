"""Customers page: list, search and register/edit customers (Admin).

Includes soft deactivation: an Admin can deactivate (and later re-activate) a
customer. Deactivated customers remain in the system for historical
sales/exchanges but are no longer selectable for new sales. Customers are
never hard-deleted.
"""

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

from app.data.db import session_scope
from app.data.repositories.customer_repository import CustomerRepository
from app.domain.services.customer_service import CustomerService
from app.domain.session import CurrentUser
from app.ui.customers.customer_form import CustomerFormDialog
from app.ui.theme import C, F, S, empty_state_message


class CustomersPage(QWidget):
    """Admin customer-record management screen."""

    def __init__(self, session_factory, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.session_factory = session_factory
        self.current_user = current_user
        self._customers = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Customers", self)
        title.setStyleSheet(f"font-size: {F.SIZE_2XL}; font-weight: {F.WEIGHT_BOLD}; color: {C.FG};")
        layout.addWidget(title)

        subtitle = QLabel("Manage customer records", self)
        subtitle.setStyleSheet(f"font-size: {F.SIZE_SM}; color: {C.MUTED_FG}; margin-bottom: 8px;")
        layout.addWidget(subtitle)

        toolbar = QHBoxLayout()
        self.add_button = QPushButton("+ Add Customer")
        self.add_button.setObjectName("btnPrimary")
        self.deactivate_button = QPushButton("Deactivate")
        self.deactivate_button.setObjectName("btnSecondary")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by name or phone...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(lambda _: self.refresh())
        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.deactivate_button)
        toolbar.addWidget(QLabel("Search:"))
        toolbar.addWidget(self.search_input, 1)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Name", "Code", "Phone", "Address", "Status"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda _: self.edit_selected())
        layout.addWidget(self.table, 1)

        self.empty_label = QLabel("No customers found. Add your first customer.", self)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(empty_state_message(""))
        self.empty_label.setVisible(False)
        layout.addWidget(self.empty_label)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"color: {C.MUTED_FG}; font-size: {F.SIZE_SM};")
        layout.addWidget(self.count_label)

        self.add_button.clicked.connect(self.add_customer)
        self.deactivate_button.clicked.connect(self.toggle_deactivate)

        self.refresh()

    def refresh(self) -> None:
        query = self.search_input.text().strip()
        with session_scope(self.session_factory) as session:
            customers = CustomerRepository(session).search(query, limit=200, include_inactive=True)
        self._customers = customers
        self.table.setRowCount(0)
        for customer in customers:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                customer.name,
                customer.customer_code,
                customer.phone or "",
                customer.address or "",
                "Inactive" if not customer.is_active else "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if not customer.is_active:
                    item.setForeground(Qt.GlobalColor.gray)
                self.table.setItem(row, column, item)
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, customer.id)
        active = sum(1 for c in customers if c.is_active)
        self.count_label.setText(f"{len(customers)} customer(s) — {active} active")
        self.empty_label.setVisible(len(customers) == 0)
        self.deactivate_button.setText("Deactivate" if self._has_selected_active() else "Reactivate")

    def _selected(self):
        by_id = {customer.id: customer for customer in self._customers}
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        for row in sorted(rows):
            customer_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if customer_id in by_id:
                yield by_id[customer_id]

    def _has_selected_active(self) -> bool:
        for customer in self._selected():
            if customer.is_active:
                return True
        return False

    def add_customer(self) -> None:
        dialog = CustomerFormDialog(save_handler=self._create_handler())
        if dialog.exec():
            self.refresh()

    def toggle_deactivate(self) -> None:
        selected = list(self._selected())
        if not selected:
            QMessageBox.information(self, "No selection", "Select a customer row first.")
            return
        customer = selected[0]
        verb = "deactivate" if customer.is_active else "reactivate"
        result = QMessageBox.question(
            self,
            f"{verb.capitalize()} customer",
            f"Are you sure you want to {verb} '{customer.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self._deactivate_handler()(customer.id)
        self.refresh()

    def _deactivate_handler(self):
        """Return a handler that deactivates/reactivates a customer by id."""
        def handler(customer_id: int) -> None:
            with session_scope(self.session_factory) as session:
                service = CustomerService(session)
                customer = service.get(customer_id)
                (service.deactivate if customer.is_active else service.activate)(
                    self.current_user, customer_id
                )
        return handler

    def edit_selected(self) -> None:
        selected = list(self._selected())
        if not selected:
            QMessageBox.information(self, "No selection", "Double-click a customer row to edit it.")
            return
        customer = selected[0]
        with self.session_factory() as session:
            fresh = CustomerRepository(session).get(customer.id)
        if fresh is None:
            QMessageBox.warning(self, "Not found", "That customer no longer exists.")
            self.refresh()
            return
        dialog = CustomerFormDialog(
            save_handler=self._update_handler(fresh.id),
            existing=fresh,
        )
        if dialog.exec():
            self.refresh()

    def _create_handler(self):
        def handler(data: dict):
            with session_scope(self.session_factory) as session:
                return CustomerService(session).create(
                    self.current_user,
                    name=data["name"],
                    phone=data["phone"] or None,
                    address=data["address"] or None,
                    customer_code=data["customer_code"] or None,
                )
        return handler

    def _update_handler(self, customer_id: int):
        def handler(data: dict):
            with session_scope(self.session_factory) as session:
                return CustomerService(session).update(
                    self.current_user,
                    customer_id,
                    name=data["name"],
                    phone=data["phone"] or None,
                    address=data["address"] or None,
                    customer_code=data["customer_code"] or None,
                )
        return handler
