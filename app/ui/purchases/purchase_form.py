"""Create purchase dialog (Admin only).

The dialog lets the Admin select a supplier, add purchase items (product,
quantity, unit cost), set the amount paid and complete the purchase.  The
purchase is recorded atomically through ``PurchaseService.complete_purchase``.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.ui.theme import C, F, S
from app.data.db import session_scope
from app.data.repositories.product_repository import ProductRepository
from app.data.repositories.supplier_repository import SupplierRepository
from app.domain.errors import ValidationError
from app.domain.services.purchase_service import PurchaseLine
from app.utils.formatting import format_money


class PurchaseFormDialog(QDialog):
    """Modal form for creating a new purchase."""

    def __init__(
        self,
        session_factory,
        complete_handler: Callable[[dict], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._session_factory = session_factory
        self._complete_handler = complete_handler
        self.completed = False

        self.setWindowTitle("Record Purchase")
        self.setModal(True)
        self.setMinimumSize(750, 550)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        supplier_row = QHBoxLayout()
        supplier_row.addWidget(QLabel("Supplier:"))
        self.supplier_combo = QComboBox()
        self.supplier_combo.setMinimumWidth(200)
        supplier_row.addWidget(self.supplier_combo, 1)
        layout.addLayout(supplier_row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Product", "Qty", "Unit Cost", "Line Total"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        add_row = QHBoxLayout()
        self.product_combo = QComboBox()
        self.product_combo.setMinimumWidth(200)
        add_row.addWidget(QLabel("Product:"))
        add_row.addWidget(self.product_combo, 1)
        self.qty_input = QLineEdit()
        self.qty_input.setPlaceholderText("Qty")
        self.qty_input.setMaximumWidth(80)
        add_row.addWidget(QLabel("Qty:"))
        add_row.addWidget(self.qty_input)
        self.cost_input = QLineEdit()
        self.cost_input.setPlaceholderText("Unit Cost")
        self.cost_input.setMaximumWidth(120)
        add_row.addWidget(QLabel("Cost:"))
        add_row.addWidget(self.cost_input)
        self.add_line_button = QPushButton("Add")
        self.add_line_button.setObjectName("btnPrimary")
        add_row.addWidget(self.add_line_button)
        layout.addLayout(add_row)

        summary_row = QHBoxLayout()
        summary_row.addStretch(1)
        self.total_label = QLabel("Total: ₦0")
        self.total_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {C.FG};")
        summary_row.addWidget(self.total_label)
        layout.addLayout(summary_row)

        paid_row = QHBoxLayout()
        paid_row.addWidget(QLabel("Amount Paid:"))
        self.paid_input = QLineEdit()
        self.paid_input.setPlaceholderText("0")
        self.paid_input.setMaximumWidth(150)
        paid_row.addWidget(self.paid_input)
        paid_row.addStretch(1)
        layout.addLayout(paid_row)

        button_row = QHBoxLayout()
        self.complete_button = QPushButton("Complete Purchase")
        self.complete_button.setObjectName("btnSuccess")
        self.complete_button.setMinimumHeight(42)
        button_row.addWidget(self.complete_button)
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("btnSecondary")
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet(
            f"color: {C.DESTRUCTIVE}; background-color: {C.DESTRUCTIVE_LIGHT}; border-radius: {S.RADIUS_SM}; padding: 8px;"
        )
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        self.add_line_button.clicked.connect(self._add_line)
        self.complete_button.clicked.connect(self._complete)
        cancel_button.clicked.connect(self.reject)

        self._lines: list[dict] = []
        self._products: dict[int, dict] = {}
        self._load_data()

    def _load_data(self) -> None:
        with self._session_factory() as session:
            suppliers = SupplierRepository(session).list_suppliers()
            products = ProductRepository(session).search("", limit=500)
        self.supplier_combo.addItem("-- Select Supplier --", None)
        for s in suppliers:
            self.supplier_combo.addItem(s.name, s.id)

        self.product_combo.addItem("-- Select Product --", None)
        for p in products:
            label = f"{p.name}"
            if p.product_code:
                label += f" ({p.product_code})"
            label += f" — {format_money(p.cost_price)}"
            self.product_combo.addItem(label, p.id)
            self._products[p.id] = {
                "name": p.name,
                "cost_price": Decimal(str(p.cost_price)),
            }

    def _add_line(self) -> None:
        self.error_label.setVisible(False)
        product_id = self.product_combo.currentData()
        if product_id is None:
            self._show_error("Select a product.")
            return
        qty_text = self.qty_input.text().strip()
        cost_text = self.cost_input.text().strip()
        if not qty_text:
            self._show_error("Enter a quantity.")
            return
        if not cost_text:
            self._show_error("Enter a unit cost.")
            return
        try:
            qty = int(qty_text)
            if qty <= 0:
                raise ValueError
        except ValueError:
            self._show_error("Quantity must be a positive whole number.")
            return
        try:
            unit_cost = Decimal(cost_text)
            if unit_cost < 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            self._show_error("Unit cost must be a valid non-negative number.")
            return

        for line in self._lines:
            if line["product_id"] == product_id:
                self._show_error("This product is already on the purchase. Remove it first.")
                return

        product_info = self._products[product_id]
        line_total = unit_cost * qty
        self._lines.append({
            "product_id": product_id,
            "product_name": product_info["name"],
            "quantity": qty,
            "unit_cost": unit_cost,
            "line_total": line_total,
        })
        self._refresh_table()
        self.qty_input.clear()
        self.cost_input.clear()

    def _refresh_table(self) -> None:
        self.table.setRowCount(0)
        grand_total = Decimal("0")
        for line in self._lines:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(line["product_name"]))
            self.table.setItem(row, 1, QTableWidgetItem(str(line["quantity"])))
            self.table.setItem(row, 2, QTableWidgetItem(format_money(line["unit_cost"])))
            self.table.setItem(row, 3, QTableWidgetItem(format_money(line["line_total"])))
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, line["product_id"])
            grand_total += line["line_total"]
        self.total_label.setText(f"Total: {format_money(grand_total)}")

    def _remove_selected(self) -> None:
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        for row in sorted(rows, reverse=True):
            if 0 <= row < len(self._lines):
                self._lines.pop(row)
        self._refresh_table()

    def _complete(self) -> None:
        self.error_label.setVisible(False)
        supplier_id = self.supplier_combo.currentData()
        if supplier_id is None:
            self._show_error("Select a supplier.")
            return
        if not self._lines:
            self._show_error("Add at least one item to the purchase.")
            return
        paid_text = self.paid_input.text().strip() or "0"
        try:
            amount_paid = Decimal(paid_text)
            if amount_paid < 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            self._show_error("Amount paid must be a valid non-negative number.")
            return
        try:
            items = [
                PurchaseLine(
                    product_id=line["product_id"],
                    quantity=line["quantity"],
                    unit_cost=line["unit_cost"],
                )
                for line in self._lines
            ]
            self._complete_handler({
                "supplier_id": supplier_id,
                "items": items,
                "amount_paid": amount_paid,
            })
        except ValidationError as exc:
            self._show_error(str(exc))
            return
        except NotFoundError as exc:
            self._show_error(str(exc))
            return
        except Exception:
            self._show_error("Could not complete the purchase. Please try again.")
            return
        self.completed = True
        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)


from app.domain.errors import NotFoundError  # noqa: E402
