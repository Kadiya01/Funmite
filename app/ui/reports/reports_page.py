"""Reports screen — Phase 08.

Tab-based reporting with date-range filters. Each tab loads data from the
reporting service when the user clicks "Run". The summary panel at the top
shows the key totals for the active tab.
"""

from __future__ import annotations

from datetime import date, datetime, time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.data.db import session_scope
from app.domain.permissions import CAP_VIEW_REPORTS
from app.domain.services.reporting_service import ReportingService
from app.domain.session import CurrentUser
from app.ui.theme import C, F, S
from app.utils.formatting import format_money


def _today() -> date:
    return date.today()


def _start_of_month() -> date:
    t = date.today()
    return t.replace(day=1)


def _make_table(columns: list[str]) -> QTableWidget:
    """Create a standard read-only table with the given column headers."""
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.setShowGrid(False)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setDefaultSectionSize(40)
    table.verticalHeader().setDefaultSectionSize(40)
    
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    return table


class ReportsPage(QWidget):
    """Admin-only reports screen with date-range filters and tab navigation."""

    def __init__(self, session_factory, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.session_factory = session_factory
        self.current_user = current_user

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # --- Title ---
        title = QLabel("Reports", self)
        title.setStyleSheet(f"font-size: {F.SIZE_2XL}; font-weight: {F.WEIGHT_BOLD}; color: {C.FG};")
        layout.addWidget(title)

        # --- Date range filters ---
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

        self.run_button = QPushButton("Run")
        self.run_button.setObjectName("btnPrimary")
        self.run_button.clicked.connect(self._run_all_tabs)
        filter_row.addWidget(self.run_button)
        filter_row.addStretch(1)
        layout.addLayout(filter_row)

        # --- Summary label ---
        self.summary_label = QLabel("", self)
        self.summary_label.setStyleSheet(
            f"background-color: {C.CARD}; border: 1px solid {C.BORDER}; "
            f"border-radius: {S.RADIUS_MD}; padding: 10px 16px; "
            f"font-size: {F.SIZE_BASE}; font-weight: {F.WEIGHT_MEDIUM}; color: {C.FG_SECONDARY};"
        )
        layout.addWidget(self.summary_label)

        # --- Tabs ---
        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs, 1)

        # Build tabs
        self._build_sales_tab()
        self._build_profit_tab()
        self._build_inventory_tab()
        self._build_payments_tab()
        self._build_purchases_tab()
        self._build_expenses_tab()
        self._build_product_sales_tab()
        self._build_cashier_sales_tab()
        self._build_end_of_day_tab()

        self.tabs.currentChanged.connect(self._update_summary)

    # -- Tab builders ------------------------------------------------------ #

    def _build_sales_tab(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        from app.ui.widgets.charts import ModernBarChart
        self.sales_chart = ModernBarChart(self)
        self.sales_chart.setMinimumHeight(300)
        layout.addWidget(self.sales_chart)
        
        self.sales_table = _make_table(
            ["Receipt", "Date", "Customer", "Cashier", "Subtotal", "Discount", "Total", "Method"]
        )
        layout.addWidget(self.sales_table, 1)
        self.tabs.addTab(widget, "Sales")

    def _build_profit_tab(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.profit_table = _make_table(
            ["Metric", "Amount"]
        )
        layout.addWidget(self.profit_table, 1)
        self.tabs.addTab(widget, "Profit")

    def _build_inventory_tab(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.inventory_table = _make_table(
            ["Product", "Category", "Qty", "Cost", "Price", "Value", "Min", "Status"]
        )
        layout.addWidget(self.inventory_table, 1)
        self.tabs.addTab(widget, "Inventory")

    def _build_payments_tab(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.payments_table = _make_table(
            ["Method", "Amount", "Reference", "Date", "Recorded By", "Receipt"]
        )
        layout.addWidget(self.payments_table, 1)
        self.tabs.addTab(widget, "Payments")

    def _build_purchases_tab(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.purchases_table = _make_table(
            ["Supplier", "Date", "Total Cost", "Paid", "Balance", "Created By"]
        )
        layout.addWidget(self.purchases_table, 1)
        self.tabs.addTab(widget, "Purchases")

    def _build_expenses_tab(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.expenses_table = _make_table(
            ["Category", "Description", "Amount", "Date", "Created By"]
        )
        layout.addWidget(self.expenses_table, 1)
        self.tabs.addTab(widget, "Expenses")

    def _build_product_sales_tab(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        from app.ui.widgets.charts import ModernBarChart
        self.product_sales_chart = ModernBarChart(self)
        self.product_sales_chart.setMinimumHeight(240)
        layout.addWidget(self.product_sales_chart)
        
        self.product_sales_table = _make_table(
            ["Product", "Qty Sold", "Revenue", "Cost", "Profit"]
        )
        layout.addWidget(self.product_sales_table, 1)
        self.tabs.addTab(widget, "Product Sales")

    def _build_cashier_sales_tab(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.cashier_sales_table = _make_table(
            ["Cashier", "Total Sales", "Transactions"]
        )
        layout.addWidget(self.cashier_sales_table, 1)
        self.tabs.addTab(widget, "Cashier Sales")

    def _build_end_of_day_tab(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        self.eod_table = _make_table(
            ["Receipt", "Customer", "Cashier", "Total", "Method"]
        )
        layout.addWidget(self.eod_table, 1)
        self.tabs.addTab(widget, "End of Day")

    # -- Data loading ------------------------------------------------------ #

    def _get_date_range(self) -> tuple[datetime, datetime]:
        d_from = self.date_from.date().toPython()
        d_to = self.date_to.date().toPython()
        start = datetime.combine(d_from, time.min)
        end = datetime.combine(d_to, time.max)
        return start, end

    def _run_all_tabs(self) -> None:
        """Load data for all tabs from the database."""
        start, end = self._get_date_range()

        with session_scope(self.session_factory) as session:
            svc = ReportingService(session)

            # Sales
            sales = svc.sales_report(self.current_user, start, end)
            self._populate_sales(sales)

            # Profit (Admin only)
            if self.current_user.can(CAP_VIEW_REPORTS):
                profit = svc.profit_report(self.current_user, start, end)
                self._populate_profit(profit)

            # Inventory
            inventory = svc.inventory_report(self.current_user)
            self._populate_inventory(inventory)

            # Payments
            payments = svc.payment_report(self.current_user, start, end)
            self._populate_payments(payments)

            # Purchases
            purchases = svc.purchase_report(self.current_user, start, end)
            self._populate_purchases(purchases)

            # Expenses
            expenses = svc.expense_report(self.current_user, start, end)
            self._populate_expenses(expenses)

            # Product Sales
            product_sales = svc.product_sales_report(self.current_user, start, end)
            self._populate_product_sales(product_sales)

            # Cashier Sales
            cashier_sales = svc.cashier_sales_report(self.current_user, start, end)
            self._populate_cashier_sales(cashier_sales)

            # End of Day (today only)
            eod = svc.end_of_day_report(self.current_user, date.today())
            self._populate_end_of_day(eod)

        self._update_summary()

    def _populate_sales(self, report) -> None:
        t = self.sales_table
        t.setRowCount(0)
        
        # Aggregate daily sales for chart
        daily_sales = {}
        
        for row in report.rows:
            # Aggregate for chart
            date_str = row.sale_date.strftime("%b %d")
            daily_sales[date_str] = daily_sales.get(date_str, 0) + float(row.total)
            
            r = t.rowCount()
            t.insertRow(r)
            values = [
                row.receipt_no,
                row.sale_date.strftime("%Y-%m-%d %H:%M"),
                row.customer_name,
                row.cashier_name,
                format_money(row.subtotal),
                format_money(row.discount_amount),
                format_money(row.total),
                row.payment_method,
            ]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if c in (4, 5, 6):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                t.setItem(r, c, item)
                
        # Set chart data
        chart_data = [(date, val) for date, val in daily_sales.items()]
        # Sort by date implicitly by keeping them in chronological order if possible, or just plot
        self.sales_chart.set_data(list(reversed(chart_data))[:10])  # Show up to 10 days


    def _populate_profit(self, report) -> None:
        t = self.profit_table
        t.setRowCount(0)
        rows = [
            ("Total Sales", format_money(report.total_sales)),
            ("COGS", format_money(report.cogs)),
            ("Gross Profit", format_money(report.gross_profit)),
            ("Expenses", format_money(report.total_expenses)),
            ("Net Profit", format_money(report.net_profit)),
        ]
        for label, amount in rows:
            r = t.rowCount()
            t.insertRow(r)
            t.setItem(r, 0, QTableWidgetItem(label))
            item = QTableWidgetItem(amount)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            t.setItem(r, 1, item)

    def _populate_inventory(self, report) -> None:
        t = self.inventory_table
        t.setRowCount(0)
        for row in report.rows:
            r = t.rowCount()
            t.insertRow(r)
            values = [
                row.product_name,
                row.category_name,
                str(row.quantity),
                format_money(row.cost_price),
                format_money(row.selling_price),
                format_money(row.inventory_value),
                str(row.minimum_stock),
                row.status,
            ]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if c in (2, 3, 4, 5, 6):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                t.setItem(r, c, item)

    def _populate_payments(self, report) -> None:
        t = self.payments_table
        t.setRowCount(0)
        for row in report.rows:
            r = t.rowCount()
            t.insertRow(r)
            values = [
                row.payment_method,
                format_money(row.amount),
                row.reference,
                row.payment_date.strftime("%Y-%m-%d %H:%M"),
                row.recorded_by_name,
                row.receipt_no,
            ]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if c == 1:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                t.setItem(r, c, item)

    def _populate_purchases(self, report) -> None:
        t = self.purchases_table
        t.setRowCount(0)
        for row in report.rows:
            r = t.rowCount()
            t.insertRow(r)
            values = [
                row.supplier_name,
                row.purchase_date.strftime("%Y-%m-%d %H:%M"),
                format_money(row.total_cost),
                format_money(row.amount_paid),
                format_money(row.balance),
                row.created_by_name,
            ]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if c in (2, 3, 4):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                t.setItem(r, c, item)

    def _populate_expenses(self, report) -> None:
        t = self.expenses_table
        t.setRowCount(0)
        for row in report.rows:
            r = t.rowCount()
            t.insertRow(r)
            values = [
                row.category,
                row.description,
                format_money(row.amount),
                row.expense_date.strftime("%Y-%m-%d %H:%M"),
                row.created_by_name,
            ]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if c == 2:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                t.setItem(r, c, item)

    def _populate_product_sales(self, rows) -> None:
        t = self.product_sales_table
        t.setRowCount(0)
        
        chart_data = []
        
        for row in rows:
            if len(chart_data) < 7:
                chart_data.append((row.product_name, float(row.revenue)))
                
            r = t.rowCount()
            t.insertRow(r)
            values = [
                row.product_name,
                str(row.quantity_sold),
                format_money(row.revenue),
                format_money(row.cost),
                format_money(row.profit),
            ]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if c in (1, 2, 3, 4):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                t.setItem(r, c, item)
                
        self.product_sales_chart.set_data(chart_data)

    def _populate_cashier_sales(self, rows) -> None:
        t = self.cashier_sales_table
        t.setRowCount(0)
        for row in rows:
            r = t.rowCount()
            t.insertRow(r)
            values = [
                row.cashier_name,
                format_money(row.total_sales),
                str(row.transaction_count),
            ]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if c in (1, 2):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                t.setItem(r, c, item)

    def _populate_end_of_day(self, report) -> None:
        t = self.eod_table
        t.setRowCount(0)
        for row in report.sales_rows:
            r = t.rowCount()
            t.insertRow(r)
            values = [
                row.receipt_no,
                row.customer_name,
                row.cashier_name,
                format_money(row.total),
                row.payment_method,
            ]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                if c == 3:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )
                t.setItem(r, c, item)

    # -- Summary ----------------------------------------------------------- #

    def _update_summary(self) -> None:
        """Update the summary label based on the active tab."""
        idx = self.tabs.currentIndex()
        tab_name = self.tabs.tabText(idx)
        start = self.start_date.date().toString("dd MMM yyyy")
        end = self.end_date.date().toString("dd MMM yyyy")
        self.summary_label.setText(f"{tab_name}  •  {start} to {end}")
