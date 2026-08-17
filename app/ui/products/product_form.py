"""Add/edit product dialog.

Mirrors the login dialog pattern: the dialog collects input and calls an
injected ``save_handler`` callable; on a validation error it shows the message
inside the dialog and stays open so nothing the Admin typed is lost.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.data.models import DEFAULT_MINIMUM_STOCK, Product
from app.domain.errors import ValidationError
from app.ui.theme import C, F, S

GENERIC_SAVE_ERROR = "Could not save the product. Please try again."


class ProductFormDialog(QDialog):
    """Modal form for creating or editing a product."""

    def __init__(
        self,
        save_handler: Callable[[dict], Product],
        categories: list[str] | None = None,
        existing: Product | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._save_handler = save_handler
        self.existing = existing
        self.saved: Product | None = None

        self.setWindowTitle("Edit Product" if existing else "Add Product")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {C.BG};
            }}
            QFormLayout QLabel, form QLabel {{
                font-weight: {F.WEIGHT_MEDIUM};
                color: {C.FG_SECONDARY};
                font-size: {F.SIZE_BASE};
            }}
            QLineEdit, QComboBox {{
                padding: 8px 10px;
                font-size: {F.SIZE_BASE};
                border: 1px solid {C.BORDER};
                border-radius: {S.RADIUS_SM};
                background-color: {C.CARD};
                min-height: 20px;
            }}
            QLineEdit:focus, QComboBox:focus {{
                border: 1px solid {C.ACCENT};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)
        form.setContentsMargins(16, 16, 16, 8)

        label_style = f"font-weight: {F.WEIGHT_MEDIUM}; color: {C.FG_SECONDARY};"

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Ladies Gown")
        _lbl = QLabel("Name:"); _lbl.setStyleSheet(label_style)
        form.addRow(_lbl, self.name_input)

        self.category_input = QComboBox()
        self.category_input.setEditable(True)
        self.category_input.addItems(categories or [])
        self.category_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.category_input.lineEdit().setPlaceholderText("Type or pick a category")
        _lbl = QLabel("Category:"); _lbl.setStyleSheet(label_style)
        form.addRow(_lbl, self.category_input)

        self.brand_input = QLineEdit()
        self.brand_input.setPlaceholderText("e.g. Gucci")
        _lbl = QLabel("Brand:"); _lbl.setStyleSheet(label_style)
        form.addRow(_lbl, self.brand_input)

        self.size_input = QLineEdit()
        self.size_input.setPlaceholderText("e.g. M")
        _lbl = QLabel("Size:"); _lbl.setStyleSheet(label_style)
        form.addRow(_lbl, self.size_input)

        self.color_input = QLineEdit()
        self.color_input.setPlaceholderText("e.g. Black")
        _lbl = QLabel("Colour:"); _lbl.setStyleSheet(label_style)
        form.addRow(_lbl, self.color_input)

        self.cost_input = QLineEdit()
        self.cost_input.setPlaceholderText("e.g. 15000")
        _lbl = QLabel("Cost Price:"); _lbl.setStyleSheet(label_style)
        form.addRow(_lbl, self.cost_input)

        self.selling_input = QLineEdit()
        self.selling_input.setPlaceholderText("e.g. 25000")
        _lbl = QLabel("Selling Price:"); _lbl.setStyleSheet(label_style)
        form.addRow(_lbl, self.selling_input)

        self.quantity_input = QLineEdit("0")
        _lbl = QLabel("Quantity:"); _lbl.setStyleSheet(label_style)
        form.addRow(_lbl, self.quantity_input)

        self.minimum_input = QLineEdit(str(DEFAULT_MINIMUM_STOCK))
        _lbl = QLabel("Minimum Stock:"); _lbl.setStyleSheet(label_style)
        form.addRow(_lbl, self.minimum_input)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Leave blank to auto-generate")
        _lbl = QLabel("Product Code:"); _lbl.setStyleSheet(label_style)
        form.addRow(_lbl, self.code_input)

        self.barcode_input = QLineEdit()
        self.barcode_input.setPlaceholderText("Auto-generated on save")
        self.barcode_input.setReadOnly(True)
        _lbl = QLabel("Barcode:"); _lbl.setStyleSheet(label_style)
        form.addRow(_lbl, self.barcode_input)

        layout.addLayout(form)

        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("btnPrimary")
        self.save_button.setDefault(True)
        self.save_button.setMinimumHeight(40)
        layout.addWidget(self.save_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("btnSecondary")
        layout.addWidget(cancel_button)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet(f"""
            color: {C.DESTRUCTIVE};
            background-color: {C.DESTRUCTIVE_LIGHT};
            padding: 8px 12px;
            border-radius: {S.RADIUS_SM};
            font-size: {F.SIZE_SM};
        """)
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        self.save_button.clicked.connect(self._save)
        cancel_button.clicked.connect(self.reject)

        if existing is not None:
            self._populate(existing)

    def _populate(self, product: Product) -> None:
        self.name_input.setText(product.name)
        self.category_input.setEditText(product.category.name if product.category else "")
        self.brand_input.setText(product.brand or "")
        self.size_input.setText(product.size or "")
        self.color_input.setText(product.color or "")
        self.cost_input.setText(str(product.cost_price))
        self.selling_input.setText(str(product.selling_price))
        self.quantity_input.setText(str(product.quantity))
        self.minimum_input.setText(str(product.minimum_stock))
        self.code_input.setText(product.product_code)
        self.barcode_input.setText(product.barcode)

    def values(self) -> dict:
        return {
            "name": self.name_input.text().strip(),
            "category": self.category_input.currentText().strip(),
            "brand": self.brand_input.text().strip(),
            "size": self.size_input.text().strip(),
            "color": self.color_input.text().strip(),
            "cost_price": self.cost_input.text().strip(),
            "selling_price": self.selling_input.text().strip(),
            "quantity": self.quantity_input.text().strip(),
            "minimum_stock": self.minimum_input.text().strip(),
            "product_code": self.code_input.text().strip(),
        }

    def _save(self) -> None:
        data = self.values()
        if not data["name"]:
            self._show_error("Product name is required.")
            return
        if not data["category"]:
            self._show_error("Category is required.")
            return
        for field, label in (
            ("cost_price", "Cost price"),
            ("selling_price", "Selling price"),
        ):
            if not data[field]:
                self._show_error(f"{label} is required.")
                return
            try:
                Decimal(data[field])
            except Exception:
                self._show_error(f"{label} must be a valid number.")
                return

        try:
            product = self._save_handler(data)
        except ValidationError as exc:
            self._show_error(str(exc))
            return
        except Exception:
            self._show_error(GENERIC_SAVE_ERROR)
            return

        self.saved = product
        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)
