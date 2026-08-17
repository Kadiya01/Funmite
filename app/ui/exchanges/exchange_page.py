"""Exchange screen (Phase 06).

Wireframe-faithful single-pair exchange page: Admin looks up the original receipt,
selects one returned item from the sale and one replacement product, the difference
is computed live, and a single ADMIN APPROVE & COMPLETE EXCHANGE action commits the
exchange atomically. The service layer supports multiple exchange lines; this page
covers the confirmed single-pair workflow.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.data.db import session_scope
from app.data.models import PAYMENT_POS, PAYMENT_TRANSFER
from app.domain.errors import AuthorizationError, NotFoundError, ValidationError
from app.domain.services.exchange_service import ExchangeService
from app.domain.services.product_service import ProductService
from app.domain.session import CurrentUser
from app.ui.exchanges.popups import show_exchange_complete, show_exchange_confirmation
from app.ui.theme import C, F, S
from app.utils.formatting import format_money


class ExchangePage(QWidget):
    """Single-pair exchange page matching the approved wireframe."""

    exchange_completed = Signal()

    def __init__(
        self,
        session_factory,
        current_user: CurrentUser,
        parent=None,
        *,
        confirm_popup: Callable[..., bool] = show_exchange_confirmation,
        complete_popup: Callable[..., None] = show_exchange_complete,
    ) -> None:
        super().__init__(parent)
        self.session_factory = session_factory
        self.current_user = current_user
        self.confirm_popup = confirm_popup
        self.complete_popup = complete_popup

        self._sale = None
        self._return_options: dict[int, dict] = {}
        self._return_product_id: int | None = None
        self._return_price = Decimal("0")
        self._replacement_product_id: int | None = None
        self._replacement_price = Decimal("0")
        self._replacement_stock = 0
        self._search_results: list = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        self._build_title(layout)
        self._build_find(layout)
        self._build_sale_info(layout)
        self._build_return(layout)
        self._build_replacement(layout)
        self._build_summary(layout)
        self._build_payment(layout)
        self._build_complete(layout)

    # --- construction ------------------------------------------------------ #

    def _build_title(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        title = QLabel("EXCHANGE", self)
        title.setStyleSheet(f"font-size: {F.SIZE_2XL}; font-weight: {F.WEIGHT_BOLD}; color: {C.FG};")
        row.addWidget(title)
        row.addStretch(1)
        layout.addLayout(row)

    def _build_find(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.addWidget(QLabel("Receipt No:", self))
        self.receipt_input = QLineEdit(self)
        self.receipt_input.setPlaceholderText("Enter receipt number")
        row.addWidget(self.receipt_input, 1)
        self.find_button = QPushButton("FIND", self)
        self.find_button.setObjectName("btnPrimary")
        self.find_button.clicked.connect(self._find_sale)
        row.addWidget(self.find_button)
        layout.addLayout(row)

    def _build_sale_info(self, layout: QVBoxLayout) -> None:
        self.sale_info_label = QLabel("", self)
        self.sale_info_label.setStyleSheet(f"font-size: {F.SIZE_SM}; color: {C.MUTED_FG};")
        self.sale_info_label.setWordWrap(True)
        self.sale_info_label.setVisible(False)
        layout.addWidget(self.sale_info_label)

    def _build_return(self, layout: QVBoxLayout) -> None:
        section = QLabel("RETURN ITEM", self)
        section.setStyleSheet(f"font-size: {F.SIZE_MD}; font-weight: {F.WEIGHT_BOLD}; color: {C.FG_SECONDARY}; padding-top: 8px;")
        layout.addWidget(section)

        row = QHBoxLayout()
        row.addWidget(QLabel("Product:", self))
        self.return_combo = QComboBox(self)
        self.return_combo.setMinimumWidth(220)
        row.addWidget(self.return_combo, 1)
        row.addWidget(QLabel("Qty:", self))
        self.return_qty_spin = QSpinBox(self)
        self.return_qty_spin.setRange(1, 1)
        self.return_qty_spin.setValue(1)
        row.addWidget(self.return_qty_spin)
        self.return_price_label = QLabel("", self)
        row.addWidget(self.return_price_label)
        layout.addLayout(row)

        self.return_combo.currentIndexChanged.connect(self._on_return_changed)
        self.return_qty_spin.valueChanged.connect(self._refresh_difference)

    def _build_replacement(self, layout: QVBoxLayout) -> None:
        section = QLabel("REPLACEMENT", self)
        section.setStyleSheet(f"font-size: {F.SIZE_MD}; font-weight: {F.WEIGHT_BOLD}; color: {C.FG_SECONDARY}; padding-top: 8px;")
        layout.addWidget(section)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search:", self))
        self.replacement_search = QLineEdit(self)
        self.replacement_search.setPlaceholderText("Search replacement product")
        search_row.addWidget(self.replacement_search, 1)
        self.replacement_add = QPushButton("Use Selected", self)
        self.replacement_add.setObjectName("btnSecondary")
        self.replacement_add.clicked.connect(self._add_replacement)
        search_row.addWidget(self.replacement_add)
        layout.addLayout(search_row)

        self.replacement_results = QListWidget(self)
        self.replacement_results.setMaximumHeight(80)
        layout.addWidget(self.replacement_results)

        qty_row = QHBoxLayout()
        qty_row.addWidget(QLabel("Qty:", self))
        self.replacement_qty_spin = QSpinBox(self)
        self.replacement_qty_spin.setRange(1, 1)
        self.replacement_qty_spin.setValue(1)
        qty_row.addWidget(self.replacement_qty_spin)
        self.replacement_readout = QLabel("", self)
        qty_row.addWidget(self.replacement_readout, 1)
        qty_row.addStretch(1)
        layout.addLayout(qty_row)

        self.replacement_search.textChanged.connect(self._on_replacement_search)
        self.replacement_qty_spin.valueChanged.connect(self._refresh_difference)

    def _build_summary(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.addStretch(1)
        self.difference_label = QLabel("", self)
        self.difference_label.setStyleSheet(f"font-size: 16px; font-weight: {F.WEIGHT_BOLD}; color: {C.ACCENT};")
        row.addWidget(self.difference_label)
        layout.addLayout(row)

    def _build_payment(self, layout: QVBoxLayout) -> None:
        row = QHBoxLayout()
        row.addWidget(QLabel("Payment:", self))
        self.payment_group = QButtonGroup(self)
        self.pos_button = QPushButton("POS", self)
        self.pos_button.setCheckable(True)
        self.pos_button.setChecked(True)
        self.transfer_button = QPushButton("TRANSFER", self)
        self.transfer_button.setCheckable(True)
        self.payment_group.addButton(self.pos_button)
        self.payment_group.addButton(self.transfer_button)
        row.addWidget(self.pos_button)
        row.addWidget(self.transfer_button)
        row.addStretch(1)
        self._payment_enabled = False
        self._set_payment_enabled(False)
        layout.addLayout(row)

    def _build_complete(self, layout: QVBoxLayout) -> None:
        self.error_label = QLabel("", self)
        self.error_label.setStyleSheet(f"color: {C.DESTRUCTIVE}; background-color: {C.DESTRUCTIVE_LIGHT}; border-radius: {S.RADIUS_SM}; padding: 8px;")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        self.complete_button = QPushButton("ADMIN APPROVE & COMPLETE EXCHANGE", self)
        self.complete_button.setObjectName("btnSuccess")
        self.complete_button.setMinimumHeight(48)
        self.complete_button.setStyleSheet(f"font-size: {F.SIZE_MD}; font-weight: {F.WEIGHT_BOLD};")
        self.complete_button.clicked.connect(self._complete_exchange)
        layout.addWidget(self.complete_button)

    # --- find sale --------------------------------------------------------- #

    def _find_sale(self) -> None:
        self._clear_error()
        receipt_no = self.receipt_input.text().strip()
        if not receipt_no:
            self._show_error("Enter a receipt number.")
            return
        try:
            with session_scope(self.session_factory) as session:
                service = ExchangeService(session)
                sale = service.find_sale(self.current_user, receipt_no)
                items = []
                for si in sale.items:
                    items.append({
                        "product_id": si.product_id,
                        "product_name": si.product.name,
                        "quantity": int(si.quantity),
                        "price": Decimal(si.unit_price),
                    })
                customer_name = sale.customer.name
                sale_date = sale.sale_date
                sale_id = sale.id
        except (NotFoundError, ValidationError, AuthorizationError) as exc:
            self._show_error(str(exc))
            return
        except Exception:
            self._show_error("Could not load the sale. Please try again.")
            return

        self._sale = {"id": sale_id, "receipt_no": receipt_no, "customer_name": customer_name, "sale_date": sale_date}
        self.sale_info_label.setText(
            f"Receipt: {receipt_no}   |   Customer: {customer_name}   |   Date: {sale_date:%d/%m/%Y %H:%M}"
        )
        self.sale_info_label.setVisible(True)

        self._return_options = {}
        self._return_product_id = None
        self._clear_replacement()
        self.return_combo.blockSignals(True)
        self.return_combo.clear()
        for item_data in items:
            pid = item_data["product_id"]
            self._return_options[pid] = item_data
            self.return_combo.addItem(
                f"{item_data['product_name']} (qty {item_data['quantity']} @ {format_money(item_data['price'])})",
                pid,
            )
        self.return_combo.blockSignals(False)
        if items:
            self.return_combo.setCurrentIndex(0)
            self._on_return_changed()

    # --- return item change ------------------------------------------------ #

    def _on_return_changed(self) -> None:
        pid = self.return_combo.currentData()
        if pid is None or pid not in self._return_options:
            return
        data = self._return_options[pid]
        self._return_product_id = pid
        self._return_price = data["price"]
        self.return_qty_spin.blockSignals(True)
        self.return_qty_spin.setRange(1, max(data["quantity"], 1))
        self.return_qty_spin.setValue(1)
        self.return_qty_spin.blockSignals(False)
        self.return_price_label.setText(format_money(self._return_price))
        self._refresh_difference()

    # --- replacement search ------------------------------------------------ #

    def _on_replacement_search(self, text: str) -> None:
        query = text.strip()
        self.replacement_results.clear()
        self._search_results = []
        if not query:
            return
        try:
            with session_scope(self.session_factory) as session:
                results = ProductService(session).search_products(
                    self.current_user, query, limit=10
                )
        except Exception:
            return
        for product in results:
            self.replacement_results.addItem(
                f"{product.name} — {format_money(product.selling_price)} (stock {product.quantity})"
            )
            self._search_results.append(product)

    def _add_replacement(self) -> None:
        row = self.replacement_results.currentRow()
        if row < 0 or row >= len(self._search_results):
            self._show_error("Select a replacement product from the search results.")
            return
        product = self._search_results[row]
        self._replacement_product_id = product.id
        self._replacement_price = Decimal(product.selling_price)
        self._replacement_stock = product.quantity
        self.replacement_readout.setText(
            f"{product.name} — {format_money(self._replacement_price)}"
        )
        self.replacement_qty_spin.blockSignals(True)
        self.replacement_qty_spin.setRange(1, max(product.quantity, 1))
        self.replacement_qty_spin.setValue(1)
        self.replacement_qty_spin.blockSignals(False)
        self._refresh_difference()

    def _clear_replacement(self) -> None:
        self._replacement_product_id = None
        self._replacement_price = Decimal("0")
        self._replacement_stock = 0
        self.replacement_readout.setText("")
        self.replacement_qty_spin.blockSignals(True)
        self.replacement_qty_spin.setRange(1, 1)
        self.replacement_qty_spin.setValue(1)
        self.replacement_qty_spin.blockSignals(False)
        self.replacement_results.clear()
        self._search_results = []
        self.replacement_search.clear()

    # --- live difference --------------------------------------------------- #

    def _refresh_difference(self) -> None:
        if self._return_product_id is None:
            self.difference_label.setText("")
            return
        returned = self._return_price * self.return_qty_spin.value()
        replacement = self._replacement_price * self.replacement_qty_spin.value() if self._replacement_product_id else Decimal("0")
        diff = replacement - returned
        if self._replacement_product_id is None:
            self.difference_label.setText("Select a replacement product.")
            self._set_payment_enabled(False)
        elif diff > 0:
            self.difference_label.setText(f"Difference: Customer pays {format_money(diff)}")
            self._set_payment_enabled(True)
        elif diff == 0:
            self.difference_label.setText("No difference")
            self._set_payment_enabled(False)
        else:
            self.difference_label.setText(
                "Exchange requires a refund to the customer — settlement not confirmed"
            )
            self._set_payment_enabled(False)

    def _set_payment_enabled(self, enabled: bool) -> None:
        self._payment_enabled = enabled
        self.pos_button.setEnabled(enabled)
        self.transfer_button.setEnabled(enabled)

    # --- complete ---------------------------------------------------------- #

    def _complete_exchange(self) -> None:
        self._clear_error()
        if self._sale is None:
            self._show_error("Find the original receipt first.")
            return
        if self._return_product_id is None:
            self._show_error("Select a product to return.")
            return
        if self._replacement_product_id is None:
            self._show_error("Select a replacement product.")
            return

        returned = self._return_price * self.return_qty_spin.value()
        replacement = self._replacement_price * self.replacement_qty_spin.value()
        diff = replacement - returned
        if diff < 0:
            self._show_error(
                "This exchange would give money back to the customer. "
                "The settlement is not confirmed (see OPEN_DECISIONS.md)."
            )
            return

        payment_method = PAYMENT_TRANSFER if self.transfer_button.isChecked() else PAYMENT_POS
        receipt_no = self._sale["receipt_no"]

        items = [
            {
                "original_product_id": self._return_product_id,
                "original_quantity": self.return_qty_spin.value(),
                "replacement_product_id": self._replacement_product_id,
                "replacement_quantity": self.replacement_qty_spin.value(),
            }
        ]

        summary = (
            f"Return: {self._return_options[self._return_product_id]['product_name']} x "
            f"{self.return_qty_spin.value()}\n"
            f"Replace with: {self.replacement_readout.text()} x "
            f"{self.replacement_qty_spin.value()}\n"
            f"Difference: {format_money(diff) if diff > 0 else 'No difference'}"
        )
        if not self.confirm_popup(self, receipt_no, summary):
            return

        try:
            with session_scope(self.session_factory) as session:
                ExchangeService(session).complete_exchange(
                    self.current_user,
                    receipt_no=receipt_no,
                    items=items,
                    payment_method=payment_method if diff > 0 else None,
                )
        except (NotFoundError, ValidationError, AuthorizationError) as exc:
            self._show_error(str(exc))
            return
        except Exception:
            self._show_error("Could not complete the exchange. Please try again.")
            return

        self.complete_popup(self, receipt_no)
        self.exchange_completed.emit()

    # --- feedback ---------------------------------------------------------- #

    def _clear_error(self) -> None:
        self.error_label.setVisible(False)

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)
