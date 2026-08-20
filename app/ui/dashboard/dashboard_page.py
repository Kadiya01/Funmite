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
                border: 1px solid {C.BORDER_LIGHT};
                border-radius: {S.RADIUS_MD};
                border-top: 3px solid {accent};
            }}
        """)
        
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        from PySide6.QtGui import QColor
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 10))
        self.setGraphicsEffect(shadow)
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
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(24)

        # --- Title row ---
        title_row = QHBoxLayout()
        title_row.setSpacing(12)
        title = QLabel("Dashboard overview", self)
        title.setStyleSheet(f"""
            font-size: {F.SIZE_3XL};
            font-weight: {F.WEIGHT_BOLD};
            color: {C.FG};
            letter-spacing: -0.5px;
        """)
        title_row.addWidget(title)
        title_row.addStretch(1)

        self.refresh_button = QPushButton("Refresh Data")
        self.refresh_button.setObjectName("btnSecondary")
        self.refresh_button.clicked.connect(self.refresh)
        title_row.addWidget(self.refresh_button)
        layout.addLayout(title_row)

        # --- Today KPI Grid ---
        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(16)

        self.kpi_sales = _KPICard("TOTAL SALES (TODAY)", C.ACCENT)
        self.kpi_gross_profit = _KPICard("GROSS PROFIT", C.ACCENT)
        self.kpi_net_profit = _KPICard("NET PROFIT", C.SUCCESS)
        self.kpi_transactions = _KPICard("TRANSACTIONS", C.PRIMARY)
        self.kpi_pos = _KPICard("BANK POS", "#0369A1")
        self.kpi_transfer = _KPICard("BANK TRANSFER", "#7C3AED")

        kpi_grid.addWidget(self.kpi_sales, 0, 0)
        kpi_grid.addWidget(self.kpi_gross_profit, 0, 1)
        kpi_grid.addWidget(self.kpi_net_profit, 0, 2)
        kpi_grid.addWidget(self.kpi_transactions, 0, 3)
        kpi_grid.addWidget(self.kpi_pos, 1, 0, 1, 2)
        kpi_grid.addWidget(self.kpi_transfer, 1, 2, 1, 2)
        
        for col in range(4):
            kpi_grid.setColumnStretch(col, 1)
            
        layout.addLayout(kpi_grid)

        # --- Low Stock Card ---
        self.low_stock_card = QFrame()
        self.low_stock_card.setStyleSheet(f"""
            QFrame {{
                background-color: {C.CARD};
                border: 1px solid {C.BORDER_LIGHT};
                border-radius: {S.RADIUS_LG};
            }}
        """)
        
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        from PySide6.QtGui import QColor
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 10))
        self.low_stock_card.setGraphicsEffect(shadow)
        
        card_layout = QVBoxLayout(self.low_stock_card)
        card_layout.setSpacing(16)
        card_layout.setContentsMargins(24, 24, 24, 24)

        header_row = QHBoxLayout()
        header_title = QLabel("Inventory Alerts")
        header_title.setStyleSheet(f"""
            font-size: {F.SIZE_LG};
            font-weight: {F.WEIGHT_BOLD};
            color: {C.PRIMARY_DARK};
            background: transparent;
        """)
        header_row.addWidget(header_title)
        
        self.summary_label = QLabel("", self.low_stock_card)
        self.summary_label.setStyleSheet(f"""
            font-size: {F.SIZE_SM};
            color: {C.MUTED_FG};
            background: transparent;
        """)
        header_row.addWidget(self.summary_label)
        header_row.addStretch(1)
        
        self.view_stock_button = QPushButton("Manage Inventory")
        self.view_stock_button.setObjectName("btnSecondary")
        self.view_stock_button.clicked.connect(self.view_stock_requested.emit)
        header_row.addWidget(self.view_stock_button)
        
        card_layout.addLayout(header_row)

        self.table = QTableWidget(0, 4, self.low_stock_card)
        self.table.setHorizontalHeaderLabels(["Product", "Current Stock", "Min Required", "Status"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        card_layout.addWidget(self.table, 1)

        layout.addWidget(self.low_stock_card, 1)

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
