"""Purchases page: list and record supplier purchases (Admin only)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import C, F, S, empty_state_message
from app.data.db import session_scope
from app.domain.services.purchase_service import PurchaseService
from app.domain.session import CurrentUser
from app.ui.purchases.purchase_form import PurchaseFormDialog
from app.utils.formatting import format_money


class PurchasesPage(QWidget):
    """Admin purchase management screen."""

    def __init__(self, session_factory, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.session_factory = session_factory
        self.current_user = current_user
        self._purchases = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Purchases", self)
        title.setStyleSheet(f"font-size: {F.SIZE_2XL}; font-weight: {F.WEIGHT_BOLD}; color: {C.FG};")
        layout.addWidget(title)

        subtitle = QLabel("Record supplier purchases and manage stock intake", self)
        subtitle.setStyleSheet(f"font-size: {F.SIZE_SM}; color: {C.MUTED_FG}; margin-bottom: 8px;")
        layout.addWidget(subtitle)

        toolbar = QHBoxLayout()
        self.add_button = QPushButton("+ Record Purchase")
        self.add_button.setObjectName("btnPrimary")
        toolbar.addWidget(self.add_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Date", "Supplier", "Total Cost", "Amount Paid", "Balance"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        self.empty_label = QLabel("No purchases found. Record your first purchase.", self)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(empty_state_message(""))
        self.empty_label.setVisible(False)
        layout.addWidget(self.empty_label)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"color: {C.MUTED_FG};")
        layout.addWidget(self.count_label)

        self.add_button.clicked.connect(self.add_purchase)

        self.refresh()

    def refresh(self) -> None:
        with session_scope(self.session_factory) as session:
            purchases = PurchaseService(session).list_purchases(self.current_user)
        self._purchases = purchases
        self.table.setRowCount(0)
        for purchase in purchases:
            row = self.table.rowCount()
            self.table.insertRow(row)
            supplier_name = purchase.supplier.name if purchase.supplier else ""
            values = [
                purchase.purchase_date.strftime("%d/%m/%Y"),
                supplier_name,
                format_money(purchase.total_cost),
                format_money(purchase.amount_paid),
                format_money(purchase.balance),
            ]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, purchase.id)
        self.count_label.setText(f"{len(purchases)} purchase(s)")
        self.empty_label.setVisible(len(purchases) == 0)

    def add_purchase(self) -> None:
        dialog = PurchaseFormDialog(
            session_factory=self.session_factory,
            complete_handler=self._complete_handler(),
        )
        if dialog.exec():
            self.refresh()

    def _complete_handler(self):
        def handler(data: dict):
            with session_scope(self.session_factory) as session:
                return PurchaseService(session).complete_purchase(
                    self.current_user,
                    supplier_id=data["supplier_id"],
                    items=data["items"],
                    amount_paid=data["amount_paid"],
                )
        return handler
