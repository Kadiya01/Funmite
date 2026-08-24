"""Cashier My Sales screen — shows only the logged-in cashier's own sales.

Uses the same ReportingService.sales_report() which automatically filters
to the cashier's own user_id.
"""

from __future__ import annotations

from datetime import date, datetime, time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.data.db import session_scope
from app.domain.services.reporting_service import ReportingService
from app.domain.session import CurrentUser
from app.ui.theme import C, F, S
from app.utils.formatting import format_money


def _today() -> date:
    return date.today()


def _start_of_month() -> date:
    t = date.today()
    return t.replace(day=1)


class MySalesPage(QWidget):
    """Cashier-only sales report page showing own sales."""

    def __init__(self, session_factory, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.session_factory = session_factory
        self.current_user = current_user

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("My Sales", self)
        title.setStyleSheet(f"font-size: {F.SIZE_2XL}; font-weight: {F.WEIGHT_BOLD}; color: {C.FG};")
        layout.addWidget(title)

        # Date range filters
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        from_label = QLabel("From:", self)
        from_label.setStyleSheet(f"font-weight: {F.WEIGHT_MEDIUM}; color: {C.FG_SECONDARY};")
        filter_row.addWidget(from_label)
        self.date_from = QDateEdit(self)
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(_start_of_month())
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        filter_row.addWidget(self.date_from)

        to_label = QLabel("To:", self)
        to_label.setStyleSheet(f"font-weight: {F.WEIGHT_MEDIUM}; color: {C.FG_SECONDARY};")
        filter_row.addWidget(to_label)
        self.date_to = QDateEdit(self)
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(_today())
        self.date_to.setDisplayFormat("yyyy-MM-dd")
        filter_row.addWidget(self.date_to)

        run_btn = QPushButton("Run")
        run_btn.setObjectName("btnPrimary")
        run_btn.clicked.connect(self._run_report)
        filter_row.addWidget(run_btn)
        filter_row.addStretch(1)
        layout.addLayout(filter_row)

        # Summary
        self.summary_label = QLabel("", self)
        self.summary_label.setStyleSheet(
            f"background-color: {C.CARD}; border: 1px solid {C.BORDER}; "
            f"border-radius: {S.RADIUS_MD}; padding: 10px 16px; "
            f"font-size: {F.SIZE_BASE}; font-weight: {F.WEIGHT_MEDIUM}; color: {C.FG_SECONDARY};"
        )
        layout.addWidget(self.summary_label)

        # Sales table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Receipt", "Date", "Customer", "Total", "Method", "Cashier"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(40)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)

        # Auto-run on load
        self._run_report()

    def _run_report(self) -> None:
        d_from = self.date_from.date().toPython()
        d_to = self.date_to.date().toPython()
        start = datetime.combine(d_from, time.min)
        end = datetime.combine(d_to, time.max)

        with session_scope(self.session_factory) as session:
            svc = ReportingService(session)
            summary = svc.sales_report(self.current_user, start, end)

        rows = summary.rows
        self.table.setRowCount(len(rows))
        total_sales = 0
        for i, row in enumerate(rows):
            self.table.setItem(i, 0, QTableWidgetItem(row.receipt_no))
            dt = row.sale_date
            if isinstance(dt, datetime):
                dt = dt.strftime("%Y-%m-%d %H:%M")
            self.table.setItem(i, 1, QTableWidgetItem(str(dt)))
            self.table.setItem(i, 2, QTableWidgetItem(row.customer_name or ""))
            amt = row.total
            self.table.setItem(i, 3, QTableWidgetItem(format_money(amt)))
            self.table.setItem(i, 4, QTableWidgetItem(row.payment_method))
            self.table.setItem(i, 5, QTableWidgetItem(row.cashier_name))
            total_sales += float(amt)

        count = len(rows)
        self.summary_label.setText(
            f"  Transactions: {count}     Total Sales: {format_money(total_sales)}"
        )
