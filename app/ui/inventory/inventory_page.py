"""Inventory screen: current stock, stock-in, adjustment, movement and low stock.

Mirrors the approved wireframe: one screen with Current Stock / Stock In /
Adjust / Movement / Low Stock sections. Writes go through ``InventoryService``
(Admin-only capabilities enforced in the service layer); the page shows
success/error feedback and raises the low-stock popup after a change.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import C, F, S, empty_state_message

from app.data.db import session_scope
from app.data.models import LOW_STOCK_THRESHOLD, Product
from app.data.repositories.product_repository import ProductRepository
from app.domain.errors import ValidationError
from app.domain.services.inventory_service import InventoryService
from app.domain.session import CurrentUser
from app.ui.widgets import show_low_stock_alert


def _all_active_products(session_factory) -> list[Product]:
    with session_factory() as session:
        return ProductRepository(session).list_active()


class InventoryPage(QWidget):
    """Admin stock-management screen (Phase 04)."""

    def __init__(
        self,
        session_factory,
        current_user: CurrentUser,
        parent=None,
        *,
        low_stock_alerter: Callable[[QWidget | None, list[Product]], bool] = show_low_stock_alert,
    ) -> None:
        super().__init__(parent)
        self.session_factory = session_factory
        self.current_user = current_user
        self.low_stock_alerter = low_stock_alerter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs, 1)

        self._build_current_stock_tab()
        self._build_stock_in_tab()
        self._build_adjust_tab()
        self._build_movement_tab()
        self._build_low_stock_tab()

        self._refresh_all()

    # --- tab construction ------------------------------------------------- #

    def _build_current_stock_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 8, 12, 8)

        toolbar = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("btnSecondary")
        self.refresh_button.clicked.connect(self._refresh_all)
        toolbar.addWidget(self.refresh_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.stock_table = QTableWidget(0, 4)
        self.stock_table.setHorizontalHeaderLabels(["Product", "Current", "Min", "Status"])
        self.stock_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.stock_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.stock_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.stock_table.verticalHeader().setVisible(False)
        self.stock_table.setAlternatingRowColors(True)
        self.stock_table.setShowGrid(False)
        self.stock_table.verticalHeader().setDefaultSectionSize(40)
        header = self.stock_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.stock_table, 1)

        self.stock_empty = QLabel("No products found.", tab)
        self.stock_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stock_empty.setStyleSheet(empty_state_message(""))
        self.stock_empty.setVisible(False)
        layout.addWidget(self.stock_empty)

        self.stock_count_label = QLabel("")
        layout.addWidget(self.stock_count_label)

        self.tabs.addTab(tab, "Current Stock")

    def _build_stock_in_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 8, 12, 8)

        info = QLabel(
            "Add stock to a product. Enter how many pieces you received.",
            tab,
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QVBoxLayout()

        self.stock_in_product = QComboBox(tab)
        form.addWidget(QLabel("Product:"))
        form.addWidget(self.stock_in_product)

        self.stock_in_quantity = QLineEdit(tab)
        self.stock_in_quantity.setPlaceholderText("e.g. 10")
        form.addWidget(QLabel("Quantity to add:"))
        form.addWidget(self.stock_in_quantity)

        self.stock_in_reason = QLineEdit(tab)
        self.stock_in_reason.setPlaceholderText("e.g. Delivery from supplier")
        form.addWidget(QLabel("Reason (optional):"))
        form.addWidget(self.stock_in_reason)

        layout.addLayout(form)

        self.stock_in_button = QPushButton("Save Stock In", tab)
        self.stock_in_button.setObjectName("btnPrimary")
        self.stock_in_button.setMinimumHeight(36)
        self.stock_in_button.clicked.connect(self._do_stock_in)
        layout.addWidget(self.stock_in_button)

        self.stock_in_error = QLabel("", tab)
        self.stock_in_error.setStyleSheet(
            f"color: {C.DESTRUCTIVE}; background-color: {C.DESTRUCTIVE_LIGHT}; "
            f"border-radius: {S.RADIUS_SM}; padding: 8px 12px;"
        )
        self.stock_in_error.setWordWrap(True)
        self.stock_in_error.setVisible(False)
        layout.addWidget(self.stock_in_error)

        layout.addStretch(1)
        self.tabs.addTab(tab, "Stock In")

    def _build_adjust_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 8, 12, 8)

        info = QLabel(
            "Fix the quantity to what you actually counted. "
            "A reason is required.",
            tab,
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QVBoxLayout()

        self.adjust_product = QComboBox(tab)
        self.adjust_product.currentIndexChanged.connect(self._update_adjust_current)
        form.addWidget(QLabel("Product:"))
        form.addWidget(self.adjust_product)

        self.adjust_current_label = QLabel("Current: —", tab)
        self.adjust_current_label.setStyleSheet(
            f"font-size: {F.SIZE_MD}; font-weight: {F.WEIGHT_SEMIBOLD}; color: {C.ACCENT};"
        )
        form.addWidget(self.adjust_current_label)

        self.adjust_new_quantity = QLineEdit(tab)
        self.adjust_new_quantity.setPlaceholderText("e.g. 5")
        form.addWidget(QLabel("New Quantity:"))
        form.addWidget(self.adjust_new_quantity)

        self.adjust_reason = QLineEdit(tab)
        self.adjust_reason.setPlaceholderText("e.g. Physical count")
        form.addWidget(QLabel("Reason:"))
        form.addWidget(self.adjust_reason)

        layout.addLayout(form)

        self.adjust_button = QPushButton("Save Adjustment", tab)
        self.adjust_button.setObjectName("btnPrimary")
        self.adjust_button.setMinimumHeight(36)
        self.adjust_button.clicked.connect(self._do_adjust)
        layout.addWidget(self.adjust_button)

        self.adjust_error = QLabel("", tab)
        self.adjust_error.setStyleSheet(
            f"color: {C.DESTRUCTIVE}; background-color: {C.DESTRUCTIVE_LIGHT}; "
            f"border-radius: {S.RADIUS_SM}; padding: 8px 12px;"
        )
        self.adjust_error.setWordWrap(True)
        self.adjust_error.setVisible(False)
        layout.addWidget(self.adjust_error)

        layout.addStretch(1)
        self.tabs.addTab(tab, "Adjust")

    def _build_movement_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 8, 12, 8)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Product:"))
        self.movement_filter = QComboBox(tab)
        self.movement_filter.addItem("All products", None)
        self.movement_filter.currentIndexChanged.connect(lambda _: self._refresh_movements())
        toolbar.addWidget(self.movement_filter)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.movement_table = QTableWidget(0, 8)
        self.movement_table.setHorizontalHeaderLabels(
            ["Date/Time", "Product", "Change", "Before", "After", "Reason", "Type", "User"]
        )
        self.movement_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.movement_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.movement_table.verticalHeader().setVisible(False)
        self.movement_table.setAlternatingRowColors(True)
        self.movement_table.setShowGrid(False)
        self.movement_table.verticalHeader().setDefaultSectionSize(40)
        header = self.movement_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.movement_table, 1)

        self.movement_empty = QLabel("No movements recorded.", tab)
        self.movement_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.movement_empty.setStyleSheet(empty_state_message(""))
        self.movement_empty.setVisible(False)
        layout.addWidget(self.movement_empty)

        self.movement_count_label = QLabel("")
        layout.addWidget(self.movement_count_label)

        self.tabs.addTab(tab, "Movement")

    def _build_low_stock_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 8, 12, 8)

        self.low_stock_label = QLabel("", tab)
        layout.addWidget(self.low_stock_label)

        self.low_stock_table = QTableWidget(0, 4)
        self.low_stock_table.setHorizontalHeaderLabels(["Product", "Current", "Min", "Status"])
        self.low_stock_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.low_stock_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.low_stock_table.verticalHeader().setVisible(False)
        self.low_stock_table.setAlternatingRowColors(True)
        self.low_stock_table.setShowGrid(False)
        self.low_stock_table.verticalHeader().setDefaultSectionSize(40)
        header = self.low_stock_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.low_stock_table, 1)

        self.tabs.addTab(tab, "Low Stock")

    # --- data ------------------------------------------------------------- #

    def _refresh_all(self) -> None:
        self._reload_product_selectors()
        self._refresh_stock_table()
        self._refresh_low_stock()
        self._refresh_movements()

    def _reload_product_selectors(self) -> None:
        products = _all_active_products(self.session_factory)
        for combo in (self.stock_in_product, self.adjust_product):
            current = combo.currentData()
            combo.blockSignals(True)
            try:
                combo.clear()
                for product in products:
                    combo.addItem(f"{product.name} ({product.product_code})", product.id)
            finally:
                combo.blockSignals(False)
            if current is not None:
                index = combo.findData(current)
                if index >= 0:
                    combo.setCurrentIndex(index)
            elif combo.count():
                combo.setCurrentIndex(0)

        current = self.movement_filter.currentData()
        self.movement_filter.blockSignals(True)
        try:
            self.movement_filter.clear()
            self.movement_filter.addItem("All products", None)
            for product in products:
                self.movement_filter.addItem(product.name, product.id)
        finally:
            self.movement_filter.blockSignals(False)
        if current is not None:
            index = self.movement_filter.findData(current)
            if index >= 0:
                self.movement_filter.setCurrentIndex(index)

        self._update_adjust_current()

    def _refresh_stock_table(self) -> None:
        products = _all_active_products(self.session_factory)
        self.stock_table.setRowCount(0)
        for product in products:
            row = self.stock_table.rowCount()
            self.stock_table.insertRow(row)
            low = product.quantity <= LOW_STOCK_THRESHOLD
            values = [
                product.name,
                str(product.quantity),
                str(product.minimum_stock),
                "LOW" if low else "OK",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column in (1, 2):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if column == 3 and low:
                    item.setForeground(Qt.GlobalColor.red)
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.stock_table.setItem(row, column, item)
            self.stock_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, product.id)
        self.stock_count_label.setText(f"{len(products)} product(s)")
        self.stock_empty.setVisible(len(products) == 0)

    def _refresh_low_stock(self) -> None:
        with session_scope(self.session_factory) as session:
            products = InventoryService(session).list_low_stock(self.current_user)
        self.low_stock_table.setRowCount(0)
        for product in products:
            row = self.low_stock_table.rowCount()
            self.low_stock_table.insertRow(row)
            for column, value in enumerate(
                [product.name, str(product.quantity), str(product.minimum_stock), "LOW"]
            ):
                item = QTableWidgetItem(value)
                if column in (1, 2):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                if column == 3:
                    item.setForeground(Qt.GlobalColor.red)
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                self.low_stock_table.setItem(row, column, item)
        if products:
            self.low_stock_label.setText(
                f"{len(products)} product(s) are low on stock "
                f"({LOW_STOCK_THRESHOLD} or fewer)."
            )
            self.low_stock_table.setVisible(True)
        else:
            self.low_stock_label.setText("All products are well stocked.")
            self.low_stock_table.setVisible(False)

    def _refresh_movements(self) -> None:
        product_id = self.movement_filter.currentData()
        with session_scope(self.session_factory) as session:
            logs = InventoryService(session).list_movements(
                self.current_user,
                product_id=product_id,
                limit=300,
            )
        self.movement_table.setRowCount(0)
        for log in logs:
            row = self.movement_table.rowCount()
            self.movement_table.insertRow(row)
            product = log.product.name if log.product else f"#{log.product_id}"
            user = log.user.full_name if log.user else ""
            created = log.created_at.strftime("%d/%m/%Y %H:%M")
            values = [
                created,
                product,
                f"{log.change_quantity:+d}",
                str(log.previous_quantity),
                str(log.new_quantity),
                log.reason,
                log.reference_type or "",
                user,
            ]
            for column, value in enumerate(values):
                self.movement_table.setItem(row, column, QTableWidgetItem(value))
        self.movement_count_label.setText(f"{len(logs)} movement(s)")
        self.movement_empty.setVisible(len(logs) == 0)

    # --- actions ---------------------------------------------------------- #

    def _selected_product_id(self, combo: QComboBox) -> int | None:
        value = combo.currentData()
        return value if isinstance(value, int) else None

    def _update_adjust_current(self) -> None:
        product_id = self._selected_product_id(self.adjust_product)
        if product_id is None:
            self.adjust_current_label.setText("Current: —")
            return
        for product in _all_active_products(self.session_factory):
            if product.id == product_id:
                self.adjust_current_label.setText(f"Current: {product.quantity}")
                return
        self.adjust_current_label.setText("Current: —")

    def _do_stock_in(self) -> None:
        self._clear_errors()
        product_id = self._selected_product_id(self.stock_in_product)
        if product_id is None:
            self._show_error(self.stock_in_error, "Choose a product.")
            return
        quantity = self.stock_in_quantity.text().strip()
        reason = self.stock_in_reason.text().strip()
        try:
            with session_scope(self.session_factory) as session:
                InventoryService(session).stock_in(
                    self.current_user,
                    product_id,
                    quantity,
                    reason=reason or None,
                )
        except ValidationError as exc:
            self._show_error(self.stock_in_error, str(exc))
            return
        except Exception:
            self._show_error(
                self.stock_in_error,
                "Could not save the stock in. Please try again.",
            )
            return

        self.stock_in_quantity.clear()
        self.stock_in_reason.clear()
        self._after_stock_change()

    def _do_adjust(self) -> None:
        self._clear_errors()
        product_id = self._selected_product_id(self.adjust_product)
        if product_id is None:
            self._show_error(self.adjust_error, "Choose a product.")
            return
        new_quantity = self.adjust_new_quantity.text().strip()
        reason = self.adjust_reason.text().strip()
        if not reason:
            self._show_error(self.adjust_error, "A reason is required for an adjustment.")
            return
        try:
            with session_scope(self.session_factory) as session:
                InventoryService(session).adjust(
                    self.current_user,
                    product_id,
                    new_quantity,
                    reason,
                )
        except ValidationError as exc:
            self._show_error(self.adjust_error, str(exc))
            return
        except Exception:
            self._show_error(
                self.adjust_error,
                "Could not save the adjustment. Please try again.",
            )
            return

        self.adjust_new_quantity.clear()
        self.adjust_reason.clear()
        self._after_stock_change()

    def _after_stock_change(self) -> None:
        self._refresh_all()
        with session_scope(self.session_factory) as session:
            low = InventoryService(session).list_low_stock(self.current_user)
        if low and self.low_stock_alerter(self, low):
            self.tabs.setCurrentIndex(self.tabs.count() - 1)

    def _clear_errors(self) -> None:
        self.stock_in_error.setVisible(False)
        self.adjust_error.setVisible(False)

    def _show_error(self, label: QLabel, message: str) -> None:
        label.setText(message)
        label.setVisible(True)
