"""Dashboard screen (Phase 04 enhanced in Phase 08).

Phase 08 adds the TODAY KPI widgets (sales, gross profit, net profit,
transactions, payment-method breakdown) above the low-stock indicator.
The page talks to the reporting service through a short-lived session.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpacerItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.data.db import session_scope
from app.data.models import LOW_STOCK_THRESHOLD, Product
from app.domain.permissions import CAP_VIEW_REPORTS
from app.domain.services.inventory_service import InventoryService
from app.domain.services.reporting_service import ReportingService
from app.domain.session import CurrentUser
from app.ui.theme import C, F, S
from app.utils.formatting import format_money


_KPI_CARD_QSS = f"""
QFrame#kpiCard {{
    background-color: {C.CARD};
    border: 1px solid {C.BORDER};
    border-radius: {S.RADIUS_MD};
    border-top: 3px solid {C.ACCENT};
}}
QFrame#kpiCardNeg {{
    background-color: {C.CARD};
    border: 1px solid {C.BORDER};
    border-radius: {S.RADIUS_MD};
    border-top: 3px solid {C.DESTRUCTIVE};
}}
"""


class _KPICard(QFrame):
    """A single KPI tile showing a label and a value."""

    def __init__(self, label: str, accent: str = C.ACCENT, parent=None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("kpiCard")
        self.setStyleSheet(f"""
            QFrame#kpiCard {{
                background-color: {C.CARD};
                border: 1px solid {C.BORDER};
                border-radius: {S.RADIUS_MD};
                border-top: 3px solid {accent};
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(4)

        self._label = QLabel(label, self)
        self._label.setStyleSheet(f"""
            font-size: {F.SIZE_XS};
            font-weight: {F.WEIGHT_SEMIBOLD};
            color: {C.MUTED_FG};
            background: transparent;
            letter-spacing: 0.5px;
        """)
        layout.addWidget(self._label)

        self._value = QLabel("\u20A60", self)
        self._value.setStyleSheet(f"""
            font-size: {F.SIZE_XL};
            font-weight: {F.WEIGHT_BOLD};
            color: {C.FG};
            background: transparent;
        """)
        layout.addWidget(self._value)
        layout.addStretch()

    def set_value(self, text: str) -> None:
        self._value.setText(text)


class DashboardPage(QWidget):
    """Admin dashboard with today's KPIs and the low-stock indicator."""

    view_stock_requested = Signal()

    def __init__(self, session_factory, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.session_factory = session_factory
        self.current_user = current_user
        self._low_stock: list[Product] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(20)

        # --- Title row ---
        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title = QLabel("Dashboard", self)
        title.setStyleSheet(f"""
            font-size: {F.SIZE_2XL};
            font-weight: {F.WEIGHT_BOLD};
            color: {C.FG};
        """)
        title_row.addWidget(title)
        title_row.addStretch(1)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("btnSecondary")
        self.refresh_button.clicked.connect(self.refresh)
        title_row.addWidget(self.refresh_button)
        layout.addLayout(title_row)

        # --- Today KPI section ---
        self._today_group = QGroupBox("TODAY")
        today_layout = QVBoxLayout(self._today_group)
        today_layout.setSpacing(16)
        today_layout.setContentsMargins(16, 20, 16, 16)

        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(12)

        self.kpi_sales = _KPICard("SALES", C.ACCENT)
        self.kpi_gross_profit = _KPICard("GROSS PROFIT", C.ACCENT)
        self.kpi_net_profit = _KPICard("NET PROFIT", C.ACCENT)
        self.kpi_transactions = _KPICard("TRANSACTIONS", C.PRIMARY)

        kpi_grid.addWidget(self.kpi_sales, 0, 0)
        kpi_grid.addWidget(self.kpi_gross_profit, 0, 1)
        kpi_grid.addWidget(self.kpi_net_profit, 0, 2)
        kpi_grid.addWidget(self.kpi_transactions, 0, 3)
        today_layout.addLayout(kpi_grid)

        # Payment breakdown row
        payment_row = QHBoxLayout()
        payment_row.setSpacing(12)

        self.kpi_pos = _KPICard("BANK POS", "#0369A1")
        self.kpi_transfer = _KPICard("BANK TRANSFER", "#7C3AED")

        payment_row.addWidget(self.kpi_pos)
        payment_row.addWidget(self.kpi_transfer)
        payment_row.addStretch(1)
        today_layout.addLayout(payment_row)

        layout.addWidget(self._today_group)

        # --- Low Stock section ---
        self.low_stock_group = QGroupBox(f"Low Stock (\u2264 {LOW_STOCK_THRESHOLD})")
        group_layout = QVBoxLayout(self.low_stock_group)
        group_layout.setSpacing(12)
        group_layout.setContentsMargins(16, 20, 16, 16)

        self.summary_label = QLabel("", self.low_stock_group)
        self.summary_label.setStyleSheet(f"""
            font-size: {F.SIZE_SM};
            color: {C.MUTED_FG};
            padding: 4px 0;
            background: transparent;
        """)
        group_layout.addWidget(self.summary_label)

        self.table = QTableWidget(0, 4, self.low_stock_group)
        self.table.setHorizontalHeaderLabels(["Product", "Current", "Min", "Status"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        group_layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.view_stock_button = QPushButton("View Stock", self.low_stock_group)
        self.view_stock_button.setObjectName("btnPrimary")
        self.view_stock_button.clicked.connect(self.view_stock_requested.emit)
        btn_row.addWidget(self.view_stock_button)
        group_layout.addLayout(btn_row)

        layout.addWidget(self.low_stock_group, 1)

        self.refresh()

    def refresh(self) -> None:
        """Reload KPIs and the low-stock list from the database."""
        # --- KPIs ---
        if self.current_user.can(CAP_VIEW_REPORTS):
            with session_scope(self.session_factory) as session:
                summary = ReportingService(session).dashboard_summary(
                    self.current_user, date.today()
                )
            self.kpi_sales.set_value(format_money(summary.total_sales))
            self.kpi_gross_profit.set_value(format_money(summary.gross_profit))
            self.kpi_net_profit.set_value(format_money(summary.net_profit))
            self.kpi_transactions.set_value(str(summary.transaction_count))
            self.kpi_pos.set_value(format_money(summary.pos_total))
            self.kpi_transfer.set_value(format_money(summary.transfer_total))

        # --- Low stock ---
        with session_scope(self.session_factory) as session:
            products = InventoryService(session).list_low_stock(self.current_user)
        self._low_stock = products
        self.table.setRowCount(0)
        for product in products:
            self._append_row(product)
        if products:
            count = len(products)
            self.summary_label.setText(f"{count} product(s) are low on stock.")
            self.summary_label.setStyleSheet(f"""
                font-size: {F.SIZE_SM};
                color: {C.DESTRUCTIVE};
                padding: 4px 0;
                background: transparent;
                font-weight: {F.WEIGHT_MEDIUM};
            """)
        else:
            self.summary_label.setText("No products are low on stock.")
            self.summary_label.setStyleSheet(f"""
                font-size: {F.SIZE_SM};
                color: {C.MUTED_FG};
                padding: 4px 0;
                background: transparent;
            """)
        self.view_stock_button.setEnabled(bool(products))

    def _append_row(self, product: Product) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [
            product.name,
            str(product.quantity),
            str(product.minimum_stock),
            "LOW",
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column in (1, 2):
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
            if column == 3:
                item.setForeground(QColor(C.DESTRUCTIVE))
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self.table.setItem(row, column, item)
        self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, product.id)
