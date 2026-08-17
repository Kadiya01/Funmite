"""Reporting service — authorization wrapper for Phase 08 reports.

Every public method checks the required permission before delegating to the
reporting repository.  ``CAP_VIEW_REPORTS`` gates most reports; profit-
sensitive views additionally require ``CAP_VIEW_PROFIT``.

The cashier's own daily sales view (UC-14) is handled by filtering
``sales_report`` on the current user's ``user_id``.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.data.repositories.reporting_repository import (
    CashierSalesReportRow,
    DashboardSummary,
    EndOfDayReport,
    ExpenseReportRow,
    ExpenseReportSummary,
    InventoryReportRow,
    InventoryReportSummary,
    LowStockReportRow,
    PaymentReportRow,
    PaymentReportSummary,
    ProductSalesReportRow,
    ProfitReportSummary,
    PurchaseReportRow,
    PurchaseReportSummary,
    ReportingRepository,
    SalesReportRow,
    SalesReportSummary,
)
from app.domain.errors import AuthorizationError
from app.domain.permissions import CAP_VIEW_OWN_SALES, CAP_VIEW_PROFIT, CAP_VIEW_REPORTS
from app.domain.permissions.catalog import require_permission
from app.domain.session import CurrentUser, user_record_id


class ReportingService:
    """Thin authorization layer over ``ReportingRepository``."""

    def __init__(self, session: Session) -> None:
        self.repo = ReportingRepository(session)

    # -- Dashboard --------------------------------------------------------- #

    def dashboard_summary(
        self, user: CurrentUser, target_date: date
    ) -> DashboardSummary:
        """Today's KPIs.  Admin-only (Dashboard is Admin-only in sidebar)."""
        require_permission(user, CAP_VIEW_REPORTS)
        return self.repo.dashboard_summary(target_date)

    # -- Sales Report ------------------------------------------------------ #

    def sales_report(
        self,
        user: CurrentUser,
        start: datetime,
        end: datetime,
        cashier_id: int | None = None,
    ) -> SalesReportSummary:
        """Sales in a date range.

        Admin sees all sales; Cashier sees only their own daily sales.
        """
        if user.role == "CASHIER":
            require_permission(user, CAP_VIEW_OWN_SALES)
        else:
            require_permission(user, CAP_VIEW_REPORTS)
        if user.role == "CASHIER":
            # Cashier is restricted to own sales
            effective_cashier_id = user_record_id(user)
        else:
            effective_cashier_id = cashier_id
        return self.repo.sales_report(start, end, effective_cashier_id)

    # -- Profit Report ----------------------------------------------------- #

    def profit_report(
        self, user: CurrentUser, start: datetime, end: datetime
    ) -> ProfitReportSummary:
        """Period profit breakdown. Admin-only (requires CAP_VIEW_PROFIT)."""
        require_permission(user, CAP_VIEW_PROFIT)
        return self.repo.profit_report(start, end)

    # -- Inventory Report -------------------------------------------------- #

    def inventory_report(self, user: CurrentUser) -> InventoryReportSummary:
        """All active products with inventory value. Admin-only."""
        require_permission(user, CAP_VIEW_REPORTS)
        return self.repo.inventory_report()

    # -- Low Stock Report -------------------------------------------------- #

    def low_stock_report(
        self, user: CurrentUser, threshold: int = 3
    ) -> tuple[LowStockReportRow, ...]:
        """Products at or below the low-stock threshold. Admin-only."""
        require_permission(user, CAP_VIEW_REPORTS)
        return self.repo.low_stock_report(threshold)

    # -- Payment Report ---------------------------------------------------- #

    def payment_report(
        self, user: CurrentUser, start: datetime, end: datetime
    ) -> PaymentReportSummary:
        """Payments in a date range with POS/Transfer totals. Admin-only."""
        require_permission(user, CAP_VIEW_REPORTS)
        return self.repo.payment_report(start, end)

    # -- Purchase Report --------------------------------------------------- #

    def purchase_report(
        self, user: CurrentUser, start: datetime, end: datetime
    ) -> PurchaseReportSummary:
        """Purchases in a date range. Admin-only."""
        require_permission(user, CAP_VIEW_REPORTS)
        return self.repo.purchase_report(start, end)

    # -- Expense Report ---------------------------------------------------- #

    def expense_report(
        self, user: CurrentUser, start: datetime, end: datetime
    ) -> ExpenseReportSummary:
        """Expenses in a date range. Admin-only."""
        require_permission(user, CAP_VIEW_REPORTS)
        return self.repo.expense_report(start, end)

    # -- Product Sales Report ---------------------------------------------- #

    def product_sales_report(
        self, user: CurrentUser, start: datetime, end: datetime
    ) -> tuple[ProductSalesReportRow, ...]:
        """Per-product sales performance. Admin-only."""
        require_permission(user, CAP_VIEW_REPORTS)
        return self.repo.product_sales_report(start, end)

    # -- Cashier Sales Report ---------------------------------------------- #

    def cashier_sales_report(
        self, user: CurrentUser, start: datetime, end: datetime
    ) -> tuple[CashierSalesReportRow, ...]:
        """Per-cashier sales performance. Admin-only."""
        require_permission(user, CAP_VIEW_REPORTS)
        return self.repo.cashier_sales_report(start, end)

    # -- End of Day Report ------------------------------------------------- #

    def end_of_day_report(
        self, user: CurrentUser, target_date: date
    ) -> EndOfDayReport:
        """Complete daily summary. Admin sees all; Cashier sees own sales."""
        require_permission(user, CAP_VIEW_REPORTS)
        return self.repo.end_of_day_report(target_date)
