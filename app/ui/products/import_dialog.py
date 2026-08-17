"""Product bulk-import dialog.

Lets the Admin load a CSV file (or paste CSV text), run a validated import and
see per-row results. Validation happens in the service layer; bad rows are
reported and never written, valid rows are imported in one transaction.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from app.data.db import session_scope
from app.domain.services.product_import import ProductImportService
from app.domain.session import CurrentUser
from app.ui.theme import C, F, S


class ProductImportDialog(QDialog):
    """Modal dialog for importing products from a CSV document."""

    def __init__(self, session_factory, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.session_factory = session_factory
        self.current_user = current_user
        self._csv_text = ""
        self.last_result = None

        self.setWindowTitle("Import Products")
        self.setModal(True)
        self.setMinimumSize(640, 480)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {C.BG};
            }}
            QLabel {{
                font-size: {F.SIZE_BASE};
                color: {C.FG};
            }}
            QPlainTextEdit {{
                font-size: {F.SIZE_BASE};
                border: 1px solid {C.BORDER};
                border-radius: {S.RADIUS_SM};
                padding: 8px;
                background-color: {C.CARD};
                font-family: {F.FAMILY_MONO};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(24, 20, 24, 20)

        hint = QLabel(
            "First row must be a header. Required columns: Name, Category, "
            "Cost Price, Selling Price. Codes and barcodes are generated when "
            "left blank. Invalid rows are reported and skipped."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {C.MUTED_FG}; font-size: {F.SIZE_SM}; padding: 4px 0;")
        layout.addWidget(hint)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.choose_button = QPushButton("Choose CSV file...")
        self.choose_button.setObjectName("btnPrimary")
        self.template_button = QPushButton("Show template")
        self.template_button.setObjectName("btnSecondary")
        self.import_button = QPushButton("Import")
        self.import_button.setObjectName("btnSuccess")
        toolbar.addWidget(self.choose_button)
        toolbar.addWidget(self.template_button)
        toolbar.addStretch(1)
        toolbar.addWidget(self.import_button)
        layout.addLayout(toolbar)

        self.preview = QPlainTextEdit()
        self.preview.setPlaceholderText(
            "Choose a CSV file or paste CSV text here, then press Import."
        )
        layout.addWidget(self.preview, 1)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet(f"""
            color: {C.FG_SECONDARY};
            font-size: {F.SIZE_SM};
            padding: 8px 12px;
            background-color: {C.MUTED};
            border-radius: {S.RADIUS_SM};
        """)
        self.result_label.setTextInteractionFlags(
            self.result_label.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.result_label)

        close_button = QPushButton("Close")
        close_button.setObjectName("btnSecondary")
        layout.addWidget(close_button)

        self.choose_button.clicked.connect(self.choose_file)
        self.template_button.clicked.connect(self.show_template)
        self.import_button.clicked.connect(self.run_import)
        close_button.clicked.connect(self.reject)

    def choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose CSV file", "", "CSV files (*.csv *.txt);;All files (*)"
        )
        if path:
            self.load_csv(path)

    def load_csv(self, path: str | Path) -> str:
        """Read a CSV file into the preview and store its text."""
        text = Path(path).read_bytes().decode("utf-8-sig")
        self._csv_text = text
        self.preview.setPlainText(text)
        return text

    def show_template(self) -> None:
        QMessageBox.information(
            self,
            "Import template",
            ProductImportService.sample_template(),
        )

    def run_import(self) -> None:
        text = self._csv_text or self.preview.toPlainText()
        if not text.strip():
            self.result_label.setText("Nothing to import yet.")
            return
        with session_scope(self.session_factory) as session:
            service = ProductImportService(session)
            self.last_result = service.import_csv(self.current_user, text)
        self.result_label.setText(self.last_result.summary())
        if self.last_result.created and not self.last_result.has_fatal_error:
            QMessageBox.information(
                self,
                "Import complete",
                f"Created {self.last_result.created} product(s).",
            )
