"""Suppliers page: list, search and register/edit suppliers (Admin only)."""

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
from app.data.repositories.supplier_repository import SupplierRepository
from app.domain.services.supplier_service import SupplierService
from app.domain.session import CurrentUser
from app.ui.suppliers.supplier_form import SupplierFormDialog
from app.ui.theme import C, F, S


class SuppliersPage(QWidget):
    """Admin supplier management screen."""

    def __init__(self, session_factory, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.session_factory = session_factory
        self.current_user = current_user
        self._suppliers = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        self.add_button = QPushButton("+ Add Supplier")
        self.add_button.setObjectName("btnPrimary")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by name or phone...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(lambda _: self.refresh())
        toolbar.addWidget(self.add_button)
        toolbar.addWidget(QLabel("Search:"))
        toolbar.addWidget(self.search_input, 1)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "Phone", "Address"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda _: self.edit_selected())
        layout.addWidget(self.table, 1)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"color: {C.MUTED_FG};")
        layout.addWidget(self.count_label)

        self.add_button.clicked.connect(self.add_supplier)

        self.refresh()

    def refresh(self) -> None:
        query = self.search_input.text().strip() or None
        with session_scope(self.session_factory) as session:
            suppliers = SupplierService(session).list_suppliers(
                self.current_user, search=query,
            )
        self._suppliers = suppliers
        self.table.setRowCount(0)
        for supplier in suppliers:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for column, value in enumerate(
                [supplier.name, supplier.phone or "", supplier.address or ""]
            ):
                self.table.setItem(row, column, QTableWidgetItem(value))
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, supplier.id)
        self.count_label.setText(f"{len(suppliers)} supplier(s)")

    def _selected(self):
        by_id = {s.id: s for s in self._suppliers}
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        for row in sorted(rows):
            supplier_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if supplier_id in by_id:
                yield by_id[supplier_id]

    def add_supplier(self) -> None:
        dialog = SupplierFormDialog(save_handler=self._create_handler())
        if dialog.exec():
            self.refresh()

    def edit_selected(self) -> None:
        selected = list(self._selected())
        if not selected:
            QMessageBox.information(self, "No selection", "Double-click a supplier row to edit it.")
            return
        supplier = selected[0]
        with self.session_factory() as session:
            fresh = SupplierService(session).get_supplier(self.current_user, supplier.id)
        if fresh is None:
            QMessageBox.warning(self, "Not found", "That supplier no longer exists.")
            self.refresh()
            return
        dialog = SupplierFormDialog(
            save_handler=self._update_handler(fresh.id),
            existing=fresh,
        )
        if dialog.exec():
            self.refresh()

    def _create_handler(self):
        def handler(data: dict):
            with session_scope(self.session_factory) as session:
                return SupplierService(session).create_supplier(
                    self.current_user,
                    name=data["name"],
                    phone=data["phone"] or None,
                    address=data["address"] or None,
                )
        return handler

    def _update_handler(self, supplier_id: int):
        def handler(data: dict):
            with session_scope(self.session_factory) as session:
                return SupplierService(session).update_supplier(
                    self.current_user,
                    supplier_id,
                    name=data["name"],
                    phone=data["phone"] or None,
                    address=data["address"] or None,
                )
        return handler
