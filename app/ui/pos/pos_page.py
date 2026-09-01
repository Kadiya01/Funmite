"""Cashier POS screen (Phase 05).

Mirrors the approved wireframe: barcode scan + search, cart, customer selection
(or quick registration), discount (Admin only), Bank POS / Bank Transfer
payment and a single atomic COMPLETE SALE action. The cashier never sees cash,
credit or split-payment options.

The page talks only to services through short-lived sessions. Sale completion
is atomic inside ``session_scope``; the receipt is built and printed only after
the transaction commits, and a printing failure never loses the sale.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.data.db import session_scope
from app.data.models import (
    DISCOUNT_FIXED,
    DISCOUNT_PERCENT,
    LOW_STOCK_THRESHOLD,
    PAYMENT_POS,
    PAYMENT_TRANSFER,
    Product,
)
from app.data.repositories.customer_repository import CustomerRepository
from app.data.repositories.product_repository import ProductRepository
from app.domain.errors import NotFoundError, ValidationError
from app.domain.permissions import CAP_CREATE_PRODUCT, CAP_DISCOUNT, CAP_EXCHANGE, CAP_VIEW_REPORTS
from app.domain.services.customer_service import CustomerService
from app.domain.services.product_service import ProductService
from app.domain.services.receipt_service import ReceiptService
from app.domain.services.sale_service import SaleService
from app.domain.session import CurrentUser
from app.printing.printer import NullPrinter, ReceiptPrinter
from app.ui.pos.popups import (
    show_barcode_not_found,
    show_insufficient_stock,
    show_low_stock_note,
    show_sale_complete,
)
from app.ui.pos.quick_customer import QuickCustomerDialog
from app.ui.exchanges.exchange_dialog import ExchangeDialog
from app.ui.widgets import BarcodeScanInput
from app.ui.theme import C, F, S, darken, empty_state_message
from app.utils.formatting import format_money

OFFLINE_STATUS = "● OFFLINE — WORKING LOCALLY"

_POS_PAGE_QSS = f"""
QPushButton[checkable="true"] {{
    background-color: {C.MUTED};
    color: {C.FG_SECONDARY};
    border: 2px solid {C.BORDER};
    border-radius: {S.RADIUS_SM};
    padding: 8px 20px;
    font-size: {F.SIZE_BASE};
    font-weight: {F.WEIGHT_SEMIBOLD};
    min-height: 20px;
}}
QPushButton[checkable="true"]:checked {{
    background-color: {C.ACCENT};
    color: {C.ON_ACCENT};
    border-color: {C.ACCENT};
}}
QPushButton[checkable="true"]:hover:!checked {{
    background-color: {C.BORDER_LIGHT};
    border-color: {C.DIVIDER};
}}
QListWidget {{
    background-color: {C.CARD};
    border: 1px solid {C.BORDER};
    border-radius: {S.RADIUS_SM};
    padding: 2px;
    font-size: {F.SIZE_SM};
}}
QListWidget::item {{
    padding: 6px 8px;
    border-radius: 3px;
}}
QListWidget::item:selected {{
    background-color: {C.ACCENT_LIGHT};
    color: {C.FG};
}}
QListWidget::item:hover:!selected {{
    background-color: {C.BORDER_LIGHT};
}}
"""


class PosPage(QWidget):
    """Barcode-first sales screen for the Cashier (and Admin)."""

    add_product_requested = Signal(str)
    sale_completed = Signal(str)

    def __init__(
        self,
        session_factory,
        current_user: CurrentUser,
        parent=None,
        *,
        printer: ReceiptPrinter | None = None,
        sale_complete_popup: Callable[..., str] = show_sale_complete,
        insufficient_popup: Callable[..., bool] = show_insufficient_stock,
        barcode_not_found_popup: Callable[..., str] = show_barcode_not_found,
        low_stock_notifier: Callable[..., None] = show_low_stock_note,
        quick_customer_dialog: Callable[..., QuickCustomerDialog] = QuickCustomerDialog,
        exchange_dialog_factory: Callable[..., object] | None = None,
    ) -> None:
        super().__init__(parent)
        self.session_factory = session_factory
        self.current_user = current_user
        self.printer = printer or NullPrinter()
        self.sale_complete_popup = sale_complete_popup
        self.insufficient_popup = insufficient_popup
        self.barcode_not_found_popup = barcode_not_found_popup
        self.low_stock_notifier = low_stock_notifier
        self.quick_customer_dialog = quick_customer_dialog
        self._exchange_dialog_factory = exchange_dialog_factory

        self._cart: list[dict] = []
        self._search_results: list[Product] = []
        self.last_receipt = None
        self.setStyleSheet(_POS_PAGE_QSS)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(12)

        self._build_title_row(main_layout)
        
        content_layout = QHBoxLayout()
        content_layout.setSpacing(16)
        
        # --- Left Panel (Input / Setup) ---
        left_panel = QFrame()
        left_panel.setStyleSheet(f"""
            QFrame {{
                background-color: {C.CARD};
                border: 1px solid {C.BORDER_LIGHT};
                border-radius: {S.RADIUS_LG};
            }}
        """)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(24)
        
        self._build_scan_row(left_layout)
        self._build_search_row(left_layout)
        self._build_customer_row(left_layout)
        self._build_discount_row(left_layout)
        left_layout.addStretch(1)
        
        content_layout.addWidget(left_panel, 1)

        # --- Right Panel (Cart / Checkout) ---
        right_panel = QFrame()
        right_panel.setStyleSheet(f"""
            QFrame {{
                background-color: {C.CARD};
                border: 1px solid {C.BORDER_LIGHT};
                border-radius: {S.RADIUS_LG};
            }}
        """)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(16)
        
        self._build_cart(right_layout)
        self._build_summary(right_layout)
        self._build_payment_row(right_layout)
        self._build_complete_row(right_layout)
        
        content_layout.addWidget(right_panel, 1)
        main_layout.addLayout(content_layout)

        self._reload_customers()
        self._rebuild_cart()
        self._refresh_summary()
        self.scan_input.setFocus()

    # --- construction ----------------------------------------------------- #

    def _build_title_row(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(12)
        title = QLabel("NEW SALE", self)
        title.setStyleSheet(f"""
            font-size: {F.SIZE_2XL};
            font-weight: {F.WEIGHT_BOLD};
            color: {C.FG};
        """)
        row.addWidget(title)
        row.addStretch(1)
        self.status_label = QLabel(OFFLINE_STATUS, self)
        self.status_label.setStyleSheet(f"""
            color: {C.WARNING};
            font-size: {F.SIZE_SM};
            font-weight: {F.WEIGHT_MEDIUM};
            padding: 4px 10px;
            background-color: {C.WARNING_LIGHT};
            border-radius: {S.RADIUS_FULL};
        """)
        row.addWidget(self.status_label)
        if self.current_user.can(CAP_VIEW_REPORTS):
            self.reprint_button = QPushButton("Reprint Receipt…", self)
            self.reprint_button.setObjectName("btnSecondary")
            self.reprint_button.clicked.connect(self._prompt_reprint)
            row.addWidget(self.reprint_button)
        if self.current_user.can(CAP_EXCHANGE):
            self.exchange_button = QPushButton("Exchange…", self)
            self.exchange_button.setObjectName("btnSecondary")
            self.exchange_button.clicked.connect(self._open_exchange)
            row.addWidget(self.exchange_button)
        self.new_sale_button = QPushButton("New Sale", self)
        self.new_sale_button.setObjectName("btnSecondary")
        self.new_sale_button.clicked.connect(self._reset_cart)
        row.addWidget(self.new_sale_button)
        layout.addLayout(row)

    def _build_scan_row(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)
        scan_label = QLabel("Scan barcode:", self)
        scan_label.setStyleSheet(f"font-weight: {F.WEIGHT_MEDIUM}; color: {C.FG_SECONDARY};")
        row.addWidget(scan_label)
        self.scan_input = BarcodeScanInput(placeholder="Scan barcode to add product...")
        self.scan_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 10px 12px;
                font-size: {F.SIZE_MD};
                border: 2px solid {C.ACCENT};
                border-radius: {S.RADIUS_SM};
                background-color: {C.CARD};
            }}
        """)
        self.scan_input.barcode_scanned.connect(self._on_scan)
        row.addWidget(self.scan_input, 1)
        layout.addLayout(row)

    def _build_search_row(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)
        search_label = QLabel("Search:", self)
        search_label.setStyleSheet(f"font-weight: {F.WEIGHT_MEDIUM}; color: {C.FG_SECONDARY};")
        row.addWidget(search_label)
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Product name, code or barcode")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._on_search_changed)
        row.addWidget(self.search_input, 1)
        self.search_add_button = QPushButton("Add Selected", self)
        self.search_add_button.setObjectName("btnPrimary")
        self.search_add_button.clicked.connect(self._add_selected_search_result)
        row.addWidget(self.search_add_button)
        layout.addLayout(row)

        self.search_list = QListWidget(self)
        self.search_list.setMaximumHeight(80)
        self.search_list.itemDoubleClicked.connect(lambda _item: self._add_selected_search_result())
        layout.addWidget(self.search_list)

    def _build_cart(self, layout: QVBoxLayout) -> None:
        self.cart_table = QTableWidget(0, 5, self)
        self.cart_table.setHorizontalHeaderLabels(["Product", "Qty", "Price", "Total", ""])
        self.cart_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cart_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.cart_table.verticalHeader().setVisible(False)
        self.cart_table.setAlternatingRowColors(True)
        self.cart_table.setShowGrid(False)
        self.cart_table.verticalHeader().setDefaultSectionSize(42)
        header = self.cart_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.cart_table, 1)

        self.cart_empty = QLabel("No items in cart. Scan a barcode or search to add products.", self)
        self.cart_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cart_empty.setStyleSheet(empty_state_message(""))
        self.cart_empty.setVisible(True)
        layout.addWidget(self.cart_empty)

    def _build_customer_row(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)
        cust_label = QLabel("Customer:", self)
        cust_label.setStyleSheet(f"font-weight: {F.WEIGHT_MEDIUM}; color: {C.FG_SECONDARY};")
        row.addWidget(cust_label)
        self.customer_filter = QLineEdit(self)
        self.customer_filter.setPlaceholderText("Filter customers")
        self.customer_filter.setMaximumWidth(180)
        self.customer_filter.textChanged.connect(self._apply_customer_filter)
        row.addWidget(self.customer_filter)
        self.customer_combo = QComboBox(self)
        self.customer_combo.setMinimumWidth(240)
        row.addWidget(self.customer_combo, 1)
        self.new_customer_button = QPushButton("New Customer…", self)
        self.new_customer_button.setObjectName("btnSecondary")
        self.new_customer_button.clicked.connect(self._new_customer)
        row.addWidget(self.new_customer_button)
        layout.addLayout(row)

    def _build_discount_row(self, layout: QVBoxLayout) -> None:
        self.discount_group = QWidget(self)
        row = QHBoxLayout(self.discount_group)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        disc_label = QLabel("Discount:", self.discount_group)
        disc_label.setStyleSheet(f"font-weight: {F.WEIGHT_MEDIUM}; color: {C.FG_SECONDARY};")
        row.addWidget(disc_label)
        self.discount_type_combo = QComboBox(self.discount_group)
        self.discount_type_combo.addItem("No discount", None)
        self.discount_type_combo.addItem("Percent", DISCOUNT_PERCENT)
        self.discount_type_combo.addItem("Fixed", DISCOUNT_FIXED)
        self.discount_type_combo.currentIndexChanged.connect(self._on_discount_changed)
        row.addWidget(self.discount_type_combo)
        self.discount_value_input = QLineEdit(self.discount_group)
        self.discount_value_input.setPlaceholderText("e.g. 10 or 5000")
        self.discount_value_input.setMaximumWidth(120)
        self.discount_value_input.setEnabled(False)
        self.discount_value_input.textChanged.connect(self._on_discount_changed)
        row.addWidget(self.discount_value_input)
        row.addStretch(1)
        self.discount_group.setVisible(self.current_user.can(CAP_DISCOUNT))
        layout.addWidget(self.discount_group)

    def _build_summary(self, layout: QVBoxLayout) -> None:
        grid = QHBoxLayout()
        grid.addStretch(1)
        column = QVBoxLayout()
        column.setSpacing(4)
        self.subtotal_label = QLabel("Subtotal: \u20A60", self)
        self.subtotal_label.setStyleSheet(f"""
            font-size: {F.SIZE_SM};
            color: {C.MUTED_FG};
        """)
        self.discount_readout = QLabel("Discount: \u20A60", self)
        self.discount_readout.setStyleSheet(f"""
            font-size: {F.SIZE_SM};
            color: {C.MUTED_FG};
        """)
        self.total_label = QLabel("TOTAL: \u20A60", self)
        self.total_label.setStyleSheet(f"""
            font-size: {F.SIZE_2XL};
            font-weight: {F.WEIGHT_BOLD};
            color: {C.FG};
            padding-top: 4px;
        """)
        column.addWidget(self.subtotal_label, alignment=Qt.AlignmentFlag.AlignRight)
        column.addWidget(self.discount_readout, alignment=Qt.AlignmentFlag.AlignRight)
        column.addWidget(self.total_label, alignment=Qt.AlignmentFlag.AlignRight)
        grid.addLayout(column)
        layout.addLayout(grid)

    def _build_payment_row(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)
        pay_label = QLabel("Payment:", self)
        pay_label.setStyleSheet(f"font-weight: {F.WEIGHT_MEDIUM}; color: {C.FG_SECONDARY};")
        row.addWidget(pay_label)
        self.payment_group = QButtonGroup(self)
        self.pos_button = QPushButton("BANK POS", self)
        self.pos_button.setCheckable(True)
        self.pos_button.setChecked(True)
        self.transfer_button = QPushButton("BANK TRANSFER", self)
        self.transfer_button.setCheckable(True)
        self.payment_group.addButton(self.pos_button)
        self.payment_group.addButton(self.transfer_button)
        row.addWidget(self.pos_button)
        row.addWidget(self.transfer_button)
        row.addStretch(1)
        ref_label = QLabel("Reference (optional):", self)
        ref_label.setStyleSheet(f"font-weight: {F.WEIGHT_MEDIUM}; color: {C.FG_SECONDARY};")
        row.addWidget(ref_label)
        self.payment_reference_input = QLineEdit(self)
        self.payment_reference_input.setPlaceholderText("POS/Transfer reference")
        self.payment_reference_input.setMaximumWidth(200)
        row.addWidget(self.payment_reference_input)
        layout.addLayout(row)

    def _build_complete_row(self, layout: QVBoxLayout) -> None:
        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet(f"""
            color: {C.DESTRUCTIVE};
            background-color: {C.DESTRUCTIVE_LIGHT};
            border-radius: {S.RADIUS_SM};
            padding: 8px 12px;
            font-size: {F.SIZE_SM};
            font-weight: {F.WEIGHT_MEDIUM};
        """)
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        self.complete_button = QPushButton("COMPLETE SALE", self)
        self.complete_button.setMinimumHeight(44)
        self.complete_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {C.ACCENT};
                color: {C.ON_ACCENT};
                border: none;
                border-radius: {S.RADIUS_MD};
                padding: 12px 24px;
                font-size: {F.SIZE_LG};
                font-weight: {F.WEIGHT_BOLD};
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background-color: {C.ACCENT_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {darken(C.ACCENT, 20)};
            }}
            QPushButton:disabled {{
                background-color: {C.MUTED};
                color: {C.MUTED_FG};
            }}
        """)
        self.complete_button.clicked.connect(self._complete_sale)
        layout.addWidget(self.complete_button)

    # --- data ------------------------------------------------------------- #

    def _reload_customers(self) -> None:
        with self.session_factory() as session:
            customers = CustomerRepository(session).list_all()
        self._customers = customers
        current = self.customer_combo.currentData()
        self.customer_combo.blockSignals(True)
        try:
            self.customer_combo.clear()
            self.customer_combo.addItem("Select customer", None)
            for customer in customers:
                self.customer_combo.addItem(
                    f"{customer.name} ({customer.customer_code})", customer.id
                )
        finally:
            self.customer_combo.blockSignals(False)
        if isinstance(current, int):
            index = self.customer_combo.findData(current)
            if index >= 0:
                self.customer_combo.setCurrentIndex(index)
        self._apply_customer_filter(self.customer_filter.text())

    def _apply_customer_filter(self, text: str) -> None:
        term = text.strip().lower()
        current = self.customer_combo.currentData()
        self.customer_combo.blockSignals(True)
        try:
            self.customer_combo.clear()
            if not term:
                self.customer_combo.addItem("Select customer", None)
            for customer in self._customers:
                if term and term not in f"{customer.name} {customer.customer_code}".lower():
                    continue
                self.customer_combo.addItem(
                    f"{customer.name} ({customer.customer_code})", customer.id
                )
            if isinstance(current, int):
                index = self.customer_combo.findData(current)
                if index >= 0:
                    self.customer_combo.setCurrentIndex(index)
        finally:
            self.customer_combo.blockSignals(False)

    def _on_search_changed(self, text: str) -> None:
        query = text.strip()
        self.search_list.clear()
        self._search_results = []
        if not query:
            return
        with session_scope(self.session_factory) as session:
            products = ProductService(session).search_products(self.current_user, query, limit=20)
        for product in products:
            self.search_list.addItem(f"{product.name} — {format_money(product.selling_price)}")
            self._search_results.append(product)

    def _add_selected_search_result(self) -> None:
        row = self.search_list.currentRow()
        if row < 0 or row >= len(self._search_results):
            return
        self._add_product(self._search_results[row])
        self.search_list.clear()
        self._search_results = []
        self.search_input.clear()

    # --- cart ------------------------------------------------------------- #

    def _add_product(self, product: Product) -> None:
        if not product.is_active:
            self._show_error(f"'{product.name}' is not active and cannot be sold.")
            return
        if product.quantity <= 0:
            self._show_error(f"'{product.name}' is out of stock.")
            return
        for line in self._cart:
            if line["product_id"] == product.id:
                line["quantity"] += 1
                line["max_quantity"] = max(line["max_quantity"], product.quantity)
                self._rebuild_cart()
                self._refresh_summary()
                return
        self._cart.append(
            {
                "product_id": product.id,
                "name": product.name,
                "price": Decimal(product.selling_price),
                "quantity": 1,
                "max_quantity": product.quantity,
            }
        )
        self._rebuild_cart()
        self._refresh_summary()

    def _rebuild_cart(self) -> None:
        self.cart_table.setRowCount(0)
        self.cart_empty.setVisible(len(self._cart) == 0)
        for row, line in enumerate(self._cart):
            self.cart_table.insertRow(row)

            name_item = QTableWidgetItem(line["name"])
            self.cart_table.setItem(row, 0, name_item)

            spin = QSpinBox(self.cart_table)
            spin.setRange(1, max(line["max_quantity"], 1))
            spin.setValue(line["quantity"])
            spin.valueChanged.connect(lambda value, r=row: self._on_quantity_changed(r, value))
            self.cart_table.setCellWidget(row, 1, spin)

            self.cart_table.setItem(row, 2, QTableWidgetItem(format_money(line["price"])))
            self.cart_table.setItem(
                row, 3, QTableWidgetItem(format_money(line["price"] * line["quantity"]))
            )

            remove_button = QPushButton("Remove", self.cart_table)
            remove_button.clicked.connect(lambda _checked=False, r=row: self._remove_row(r))
            self.cart_table.setCellWidget(row, 4, remove_button)

    def _on_quantity_changed(self, row: int, value: int) -> None:
        if row >= len(self._cart):
            return
        self._cart[row]["quantity"] = value
        self._refresh_summary()
        total_item = self.cart_table.item(row, 3)
        if total_item is not None:
            total_item.setText(format_money(self._cart[row]["price"] * value))

    def _remove_row(self, row: int) -> None:
        if 0 <= row < len(self._cart):
            del self._cart[row]
        self._rebuild_cart()
        self._refresh_summary()

    def _reset_cart(self) -> None:
        self._cart = []
        self._clear_error()
        self._rebuild_cart()
        self._refresh_summary()
        self.pos_button.setChecked(True)
        self.payment_reference_input.clear()
        self.scan_input.clear()
        self.scan_input.setFocus()

    def _clamp_cart_to_stock(self) -> None:
        with self.session_factory() as session:
            available = {
                line["product_id"]: (session.get(Product, line["product_id"]).quantity or 0)
                for line in self._cart
            }
        kept = []
        for line in self._cart:
            stock = available.get(line["product_id"], 0)
            if stock <= 0:
                continue
            line["quantity"] = min(line["quantity"], stock)
            line["max_quantity"] = stock
            kept.append(line)
        self._cart = kept
        self._rebuild_cart()
        self._refresh_summary()

    # --- discount / summary ---------------------------------------------- #

    def _on_discount_changed(self, *_args) -> None:
        self.discount_value_input.setEnabled(self.discount_type_combo.currentData() is not None)
        self._refresh_summary()

    def _discount_selection(self) -> dict | None:
        if not self.current_user.can(CAP_DISCOUNT):
            return None
        discount_type = self.discount_type_combo.currentData()
        value = self.discount_value_input.text().strip()
        if discount_type is None or not value:
            return None
        return {"type": discount_type, "value": value}

    def _subtotal(self) -> Decimal:
        return sum((line["price"] * line["quantity"] for line in self._cart), Decimal("0"))

    def _refresh_summary(self) -> None:
        subtotal = self._subtotal()
        discount = Decimal("0")
        selection = self._discount_selection()
        if selection:
            try:
                value = Decimal(selection["value"])
            except (InvalidOperation, ValueError):
                value = Decimal("0")
            if selection["type"] == DISCOUNT_PERCENT:
                discount = subtotal * value / Decimal("100")
            elif selection["type"] == DISCOUNT_FIXED:
                discount = value
            if discount < 0:
                discount = Decimal("0")
        total = subtotal - discount
        if total < 0:
            total = Decimal("0")
        self.subtotal_label.setText(f"Subtotal: {format_money(subtotal)}")
        self.discount_readout.setText(f"Discount: {format_money(discount)}")
        self.total_label.setText(f"TOTAL: {format_money(total)}")

        if not self._cart:
            self.complete_button.setText("COMPLETE SALE (ADD A PRODUCT)")
            self.complete_button.setEnabled(False)
        else:
            self.complete_button.setText("COMPLETE SALE")
            self.complete_button.setEnabled(True)

    # --- scanning --------------------------------------------------------- #

    def _on_scan(self, barcode: str) -> None:
        with session_scope(self.session_factory) as session:
            product = ProductService(session).lookup_by_barcode(self.current_user, barcode)
        if product is None:
            can_add = self.current_user.can(CAP_CREATE_PRODUCT)
            choice = self.barcode_not_found_popup(self, barcode, can_add=can_add)
            if choice == "add":
                self.add_product_requested.emit(barcode)
            return
        self._add_product(product)

    # --- customer --------------------------------------------------------- #

    def _new_customer(self) -> None:
        dialog = self.quick_customer_dialog(
            save_handler=self._quick_customer_save_handler(),
            parent=self,
        )
        if dialog.exec() and dialog.saved is not None:
            self._reload_customers()
            index = self.customer_combo.findData(dialog.saved.id)
            if index >= 0:
                self.customer_combo.setCurrentIndex(index)
                self.customer_filter.clear()

    def _quick_customer_save_handler(self):
        def handler(data: dict):
            with session_scope(self.session_factory) as session:
                return CustomerService(session).create_for_sale(
                    self.current_user,
                    name=data["name"],
                    phone=data.get("phone"),
                )

        return handler

    # --- completion ------------------------------------------------------- #

    def _payment_method(self) -> str:
        if self.transfer_button.isChecked():
            return PAYMENT_TRANSFER
        return PAYMENT_POS

    def _complete_sale(self) -> None:
        self._clear_error()
        customer_id = self.customer_combo.currentData()
        if not isinstance(customer_id, int):
            self._show_error("Select a customer to complete the sale.")
            return
        if not self._cart:
            self._show_error("Add at least one product to the cart.")
            return

        items = [
            {"product_id": line["product_id"], "quantity": line["quantity"]}
            for line in self._cart
        ]
        payment_method = self._payment_method()
        discount = self._discount_selection()
        reference = self.payment_reference_input.text().strip() or None

        try:
            with session_scope(self.session_factory) as session:
                sale = SaleService(session).complete_sale(
                    self.current_user,
                    customer_id=customer_id,
                    items=items,
                    payment_method=payment_method,
                    discount=discount,
                    reference=reference,
                )
            receipt_no = sale.receipt_no
        except NotFoundError as exc:
            self._show_error(str(exc))
            return
        except ValidationError as exc:
            if "Insufficient stock" in str(exc):
                if self.insufficient_popup(self, str(exc)):
                    self._clamp_cart_to_stock()
                return
            self._show_error(str(exc))
            return
        except Exception:
            self._show_error("Could not complete the sale. Please try again.")
            return

        self.sale_completed.emit(receipt_no)
        self._finish_sale(receipt_no, items)

    def _finish_sale(self, receipt_no: str, sold_items: list[dict]) -> None:
        receipt = None
        printed = False
        try:
            with session_scope(self.session_factory) as session:
                service = ReceiptService(session)
                sale = service.get_by_receipt_no(receipt_no)
                receipt = service.build_receipt(sale)
            self.printer.print_receipt(receipt)
            printed = True
        except Exception:
            printed = False
        self.last_receipt = receipt

        self._notify_sold_low_stock(sold_items)

        action = self.sale_complete_popup(self, receipt_no, printed)
        if action == "new":
            self._reset_cart()
        elif self.last_receipt is not None:
            try:
                self.printer.print_receipt(self.last_receipt)
            except Exception:
                QMessageBox.warning(
                    self,
                    "Print failed",
                    "The receipt could not be printed. Use Reprint when the printer is ready.",
                )

    def _notify_sold_low_stock(self, sold_items: list[dict]) -> None:
        with session_scope(self.session_factory) as session:
            products = []
            for entry in sold_items:
                product = session.get(Product, entry["product_id"])
                if product is not None and product.is_active and product.quantity <= LOW_STOCK_THRESHOLD:
                    products.append(product)
        self.low_stock_notifier(self, products)

    # --- reprint (Admin) -------------------------------------------------- #

    def _prompt_reprint(self) -> None:
        receipt_no, ok = QInputDialog.getText(
            self, "Reprint Receipt", "Receipt number:", text=""
        )
        if ok and receipt_no.strip():
            self.reprint_receipt(receipt_no.strip())

    def reprint_receipt(self, receipt_no: str) -> None:
        """Reprint a completed sale's receipt (Admin only, UC-06)."""
        try:
            with session_scope(self.session_factory) as session:
                ReceiptService(session).reprint(
                    self.current_user, receipt_no, self.printer
                )
        except (NotFoundError, ValidationError) as exc:
            self._show_error(str(exc))
        except Exception:
            self._show_error("Could not reprint the receipt. Please try again.")

    # --- exchange (Admin) -------------------------------------------------- #

    def _open_exchange(self) -> None:
        factory = self._exchange_dialog_factory or ExchangeDialog
        dialog = factory(
            session_factory=self.session_factory,
            current_user=self.current_user,
            parent=self,
        )
        dialog.exec()

    # --- feedback --------------------------------------------------------- #

    def _clear_error(self) -> None:
        self.error_label.setVisible(False)

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)
