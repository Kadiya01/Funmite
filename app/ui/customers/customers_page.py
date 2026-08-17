"""Customers page: list, search and register/edit customers (Admin)."""

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
from app.ui.theme import C, F, S


class CustomersPage(QWidget):
    """Admin customer-record management screen."""

    def __init__(self, session_factory, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.session_factory = session_factory
        self.current_user = current_user
        self._customers = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        self.add_button = QPushButton("+ Add Customer")
        self.add_button.setObjectName("btnPrimary")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by name or phone...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(lambda _: self.refresh())
        toolbar.addWidget(self.add_button)
        toolbar.addWidget(QLabel("Search:"))
        toolbar.addWidget(self.search_input, 1)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Name", "Code", "Phone", "Address"])
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

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"color: {C.MUTED_FG}; font-size: {F.SIZE_SM};")
        layout.addWidget(self.count_label)

        self.add_button.clicked.connect(self.add_customer)

        self.refresh()

    def refresh(self) -> None:
        query = self.search_input.text().strip()
        with session_scope(self.session_factory) as session:
            customers = CustomerRepository(session).search(query, limit=200)
        self._customers = customers
        self.table.setRowCount(0)
        for customer in customers:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for column, value in enumerate(
                [customer.name, customer.customer_code, customer.phone or "", customer.address or ""]
            ):
                self.table.setItem(row, column, QTableWidgetItem(value))
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, customer.id)
        self.count_label.setText(f"{len(customers)} customer(s)")

    def _selected(self):
        by_id = {customer.id: customer for customer in self._customers}
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        for row in sorted(rows):
            customer_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if customer_id in by_id:
                yield by_id[customer_id]

    def add_customer(self) -> None:
        dialog = CustomerFormDialog(save_handler=self._create_handler())
        if dialog.exec():
            self.refresh()

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
