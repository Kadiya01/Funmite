"""Products page: list, search, add/edit, import and barcode labels.

The page talks only to application services through short-lived sessions; it
never touches the database directly. Permission enforcement lives in the
service layer; this page is only reachable by Admin from the sidebar.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
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

from app.barcode.labels import SvgLabelRenderer
from app.data.db import session_scope
from app.data.models import Product
from app.data.repositories.product_repository import ProductRepository
from app.domain.services.product_service import ProductService
from app.domain.session import CurrentUser
from app.ui.products.import_dialog import ProductImportDialog
from app.ui.products.product_form import ProductFormDialog
from app.ui.theme import C, F, S, empty_state_message
from app.ui.widgets import BarcodeScanInput

_MONEY = "₦"


class ProductsPage(QWidget):
    """Admin catalogue management screen."""

    def __init__(self, session_factory, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.session_factory = session_factory
        self.current_user = current_user
        self._products: list[Product] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Products", self)
        title.setStyleSheet(f"font-size: {F.SIZE_2XL}; font-weight: {F.WEIGHT_BOLD}; color: {C.FG};")
        layout.addWidget(title)

        subtitle = QLabel("Manage your product catalogue", self)
        subtitle.setStyleSheet(f"font-size: {F.SIZE_SM}; color: {C.MUTED_FG}; margin-bottom: 8px;")
        layout.addWidget(subtitle)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.add_button = QPushButton("+ Add Product")
        self.add_button.setObjectName("btnPrimary")
        self.import_button = QPushButton("Import")
        self.import_button.setObjectName("btnSecondary")
        self.labels_button = QPushButton("Barcode Labels")
        self.labels_button.setObjectName("btnSecondary")
        self.labels_button.setEnabled(False)

        self.search_input = BarcodeScanInput(placeholder="Search name, code or barcode...")
        self.search_input.setClearButtonEnabled(True)

        self.category_filter = QComboBoxWithAll()

        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.import_button)
        toolbar.addWidget(self.labels_button)
        search_label = QLabel("Search:")
        search_label.setStyleSheet(f"font-weight: {F.WEIGHT_MEDIUM}; color: {C.FG_SECONDARY};")
        toolbar.addWidget(search_label)
        toolbar.addWidget(self.search_input, 1)
        cat_label = QLabel("Category:")
        cat_label.setStyleSheet(f"font-weight: {F.WEIGHT_MEDIUM}; color: {C.FG_SECONDARY};")
        toolbar.addWidget(cat_label)
        toolbar.addWidget(self.category_filter)
        layout.addLayout(toolbar)

        self.scan_input = BarcodeScanInput(placeholder="Scan barcode to find product")
        scan_row = QHBoxLayout()
        scan_row.setSpacing(8)
        scan_label = QLabel("Scan barcode:")
        scan_label.setStyleSheet(f"font-weight: {F.WEIGHT_MEDIUM}; color: {C.FG_SECONDARY};")
        scan_row.addWidget(scan_label)
        scan_row.addWidget(self.scan_input, 1)
        layout.addLayout(scan_row)

        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(
            ["Name", "Category", "Size", "Colour", f"Cost ({_MONEY})", f"Selling ({_MONEY})",
             "Qty", "Min", "Barcode", "Code", "Status"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        self.empty_label = QLabel("No products found. Add your first product.", self)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(empty_state_message(""))
        self.empty_label.setVisible(False)
        layout.addWidget(self.empty_label)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"color: {C.MUTED_FG}; font-size: {F.SIZE_SM}; padding: 4px 0;")
        layout.addWidget(self.count_label)

        self.search_input.textChanged.connect(self._on_search_changed)
        self.category_filter.currentIndexChanged.connect(lambda _: self.refresh())
        self.scan_input.barcode_scanned.connect(self._on_scan)
        self.table.doubleClicked.connect(self._on_row_double_clicked)
        self.table.itemSelectionChanged.connect(self._update_label_button)
        self.add_button.clicked.connect(self.add_product)
        self.import_button.clicked.connect(self.open_import)
        self.labels_button.clicked.connect(self.export_labels)

        self._load_categories()
        self.refresh()

    # --- data ------------------------------------------------------------- #

    def _categories(self) -> list[str]:
        with self.session_factory() as session:
            from app.data.repositories.category_repository import CategoryRepository

            return [category.name for category in CategoryRepository(session).list_all()]

    def _load_categories(self) -> None:
        current = self.category_filter.currentData()
        self.category_filter.reload(self._categories())
        if current is not None:
            index = self.category_filter.findData(current)
            if index >= 0:
                self.category_filter.setCurrentIndex(index)

    def refresh(self) -> None:
        query = self.search_input.text().strip()
        category_id = self.category_filter.currentData()
        if category_id == QComboBoxWithAll.ALL:
            category_id = None
        with session_scope(self.session_factory) as session:
            products = ProductRepository(session).search(
                query,
                category_id=category_id,
                include_inactive=True,
                limit=200,
            )
        self._products = products
        self.table.setRowCount(0)
        for product in products:
            self._append_row(product)
        self.count_label.setText(f"{len(products)} product(s)")
        self.empty_label.setVisible(len(products) == 0)
        self._update_label_button()

    def _append_row(self, product: Product) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        category = product.category.name if product.category else ""
        values = [
            product.name,
            category,
            product.size or "",
            product.color or "",
            str(product.cost_price),
            str(product.selling_price),
            str(product.quantity),
            str(product.minimum_stock),
            product.barcode,
            product.product_code,
            "Active" if product.is_active else "Inactive",
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column in (4, 5):
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, column, item)
        self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, product.id)

    # --- events ----------------------------------------------------------- #

    def _on_search_changed(self, _text: str) -> None:
        self.refresh()

    def _on_scan(self, barcode: str) -> None:
        for row in range(self.table.rowCount()):
            if self.table.item(row, 8).text() == barcode:
                self.table.selectRow(row)
                self.table.scrollToItem(self.table.item(row, 0))
                return
        QMessageBox.information(self, "Barcode not found", f"No product has barcode '{barcode}'.")

    def _on_row_double_clicked(self, _index=None) -> None:
        self.edit_selected()

    def _update_label_button(self) -> None:
        self.labels_button.setEnabled(bool(self.table.selectionModel().selectedRows()))

    def _selected_products(self) -> list[Product]:
        by_id = {product.id: product for product in self._products}
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        selected = []
        for row in sorted(rows):
            product_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            product = by_id.get(product_id)
            if product is not None:
                selected.append(product)
        return selected

    # --- actions ---------------------------------------------------------- #

    def add_product(self) -> None:
        dialog = ProductFormDialog(
            save_handler=self._create_handler(),
            categories=self._categories(),
        )
        if dialog.exec():
            self.refresh()
            self._load_categories()

    def edit_selected(self) -> None:
        products = self._selected_products()
        if not products:
            QMessageBox.information(self, "No selection", "Double-click a product row to edit it.")
            return
        self._edit_product(products[0])

    def _edit_product(self, product: Product) -> None:
        with self.session_factory() as session:
            fresh = ProductRepository(session).get(product.id)
        if fresh is None:
            QMessageBox.warning(self, "Not found", "That product no longer exists.")
            self.refresh()
            return
        dialog = ProductFormDialog(
            save_handler=self._update_handler(fresh.id),
            categories=self._categories(),
            existing=fresh,
        )
        if dialog.exec():
            self.refresh()
            self._load_categories()

    def open_import(self) -> None:
        dialog = ProductImportDialog(self.session_factory, self.current_user, parent=self)
        dialog.exec()
        self.refresh()
        self._load_categories()

    def export_labels(self) -> None:
        products = self._selected_products()
        if not products:
            return
        directory = QFileDialog.getExistingDirectory(self, "Choose a folder for barcode labels")
        if not directory:
            return
        renderer = SvgLabelRenderer()
        saved = []
        for product in products:
            path = Path(directory) / f"{product.product_code}_{product.barcode}.svg"
            path.write_bytes(renderer.render_product(product))
            saved.append(str(path))
        if saved:
            QMessageBox.information(
                self,
                "Labels saved",
                f"Saved {len(saved)} barcode label(s).\n\n" + "\n".join(saved[:5]),
            )

    # --- save handlers ---------------------------------------------------- #

    def _create_handler(self):
        def handler(data: dict):
            with session_scope(self.session_factory) as session:
                service = ProductService(session)
                return service.create(
                    self.current_user,
                    name=data["name"],
                    category=data["category"],
                    brand=data["brand"] or None,
                    size=data["size"] or None,
                    color=data["color"] or None,
                    cost_price=data["cost_price"],
                    selling_price=data["selling_price"],
                    quantity=data["quantity"],
                    minimum_stock=data["minimum_stock"],
                    product_code=data["product_code"] or None,
                )
        return handler

    def _update_handler(self, product_id: int):
        def handler(data: dict):
            with session_scope(self.session_factory) as session:
                service = ProductService(session)
                return service.update(
                    self.current_user,
                    product_id,
                    name=data["name"],
                    category=data["category"],
                    brand=data["brand"] or None,
                    size=data["size"] or None,
                    color=data["color"] or None,
                    cost_price=data["cost_price"],
                    selling_price=data["selling_price"],
                    quantity=data["quantity"],
                    minimum_stock=data["minimum_stock"],
                    product_code=data["product_code"] or None,
                )
        return handler


class QComboBoxWithAll(QComboBox):
    """Category filter: an 'All categories' option plus every category."""

    ALL = -1

    def reload(self, categories: list[str]) -> None:
        current = self.currentData()
        self.blockSignals(True)
        try:
            self.clear()
            self.addItem("All categories", QComboBoxWithAll.ALL)
            for name in sorted(categories):
                self.addItem(name, name)
        finally:
            self.blockSignals(False)
        if current is not None:
            index = self.findData(current)
            if index >= 0:
                self.setCurrentIndex(index)

    def currentData(self, role=Qt.ItemDataRole.UserRole):
        return super().currentData(role)
