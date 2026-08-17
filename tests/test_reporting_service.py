"""Reporting service tests (Phase 08).

Covers dashboard KPIs, sales/profit/inventory/payment/purchase/expense reports,
product-sales, cashier-sales, end-of-day, date filtering, authorization,
empty periods, multiple transactions, and offline operation.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest

from app.data.db import session_scope
from app.data.models import (
    PAYMENT_POS,
    PAYMENT_TRANSFER,
    ROLE_ADMIN,
    ROLE_CASHIER,
    Expense,
    Purchase,
    PurchaseItem,
)
from app.domain.errors import AuthorizationError
from app.domain.services.reporting_service import ReportingService
from app.domain.session import CurrentUser
from tests.factories import (
    make_category,
    make_customer,
    make_product,
    make_sale,
    make_user,
)


# -- helpers --------------------------------------------------------------- #

def _admin(session):
    return make_user(session, role=ROLE_ADMIN, full_name="Admin User")


def _cashier(session):
    return make_user(session, role=ROLE_CASHIER, full_name="Cashier User")


def _product(session, *, name="Test Product", cost="1500", selling="2500", qty=10):
    return make_product(
        session,
        make_category(session),
        name=name,
        cost_price=Decimal(cost),
        selling_price=Decimal(selling),
        quantity=qty,
    )


def _customer(session, name="Walk-in"):
    return make_customer(session, name=name)


def _today_range():
    today = date.today()
    start = datetime.combine(today, time.min)
    end = datetime.combine(today, time.max)
    return start, end


def _make_expense(session, user, amount="500", category="Rent", days_ago=0):
    expense = Expense(
        category=category,
        description=f"Test {category}",
        amount=Decimal(amount),
        expense_date=datetime.now() - timedelta(days=days_ago),
        created_by=user.id,
    )
    session.add(expense)
    session.flush()
    return expense


# -- Authorization tests --------------------------------------------------- #

class TestAuthorization:
    def test_cashier_dashboard_summary_blocked(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            cashier = _cashier(session)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            with pytest.raises(AuthorizationError):
                svc.dashboard_summary(cashier, date.today())

    def test_admin_dashboard_summary_allowed(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            result = svc.dashboard_summary(admin, date.today())
            assert result.transaction_count == 0

    def test_unauthenticated_blocked(self, session_factory):
        fake_user = CurrentUser(
            user_id=999, username="ghost", full_name="Ghost", role="UNKNOWN"
        )
        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            with pytest.raises(AuthorizationError):
                svc.dashboard_summary(fake_user, date.today())

    def test_cashier_profit_report_blocked(self, session_factory):
        with session_scope(session_factory) as session:
            cashier = _cashier(session)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            with pytest.raises(AuthorizationError):
                svc.profit_report(cashier, start, end)

    def test_cashier_sales_report_restricted_to_own(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            cashier = _cashier(session)
            cat = make_category(session)
            prod = _product(session)
            cust = _customer(session)

        with session_scope(session_factory) as session:
            make_sale(session, cust, cashier, items=[(prod, 1)])
            make_sale(session, cust, admin, items=[(prod, 1)])

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            result = svc.sales_report(cashier, start, end)
            assert result.transaction_count == 1
            assert result.rows[0].cashier_name == "Cashier User"


# -- Dashboard Summary tests ----------------------------------------------- #

class TestDashboardSummary:
    def test_empty_dashboard(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            result = svc.dashboard_summary(admin, date.today())
            assert result.total_sales == Decimal("0")
            assert result.cogs == Decimal("0")
            assert result.gross_profit == Decimal("0")
            assert result.total_expenses == Decimal("0")
            assert result.net_profit == Decimal("0")
            assert result.transaction_count == 0
            assert result.pos_total == Decimal("0")
            assert result.transfer_total == Decimal("0")

    def test_dashboard_with_sales(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            cust = _customer(session)
            prod = _product(session, cost="1500", selling="2500", qty=10)

        with session_scope(session_factory) as session:
            make_sale(session, cust, admin, items=[(prod, 2)], payment_method=PAYMENT_POS)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            result = svc.dashboard_summary(admin, date.today())
            assert result.total_sales == Decimal("5000")
            assert result.cogs == Decimal("3000")
            assert result.gross_profit == Decimal("2000")
            assert result.transaction_count == 1
            assert result.pos_total == Decimal("5000")
            assert result.transfer_total == Decimal("0")

    def test_dashboard_with_transfer_payment(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            cust = _customer(session)
            prod = _product(session, cost="1000", selling="2000", qty=10)

        with session_scope(session_factory) as session:
            make_sale(session, cust, admin, items=[(prod, 1)], payment_method=PAYMENT_TRANSFER)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            result = svc.dashboard_summary(admin, date.today())
            assert result.pos_total == Decimal("0")
            assert result.transfer_total == Decimal("2000")

    def test_dashboard_with_expenses(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)

        with session_scope(session_factory) as session:
            _make_expense(session, admin, amount="1000", category="Rent")

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            result = svc.dashboard_summary(admin, date.today())
            assert result.total_expenses == Decimal("1000")
            assert result.net_profit == Decimal("-1000")

    def test_dashboard_multiple_sales(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            cust = _customer(session)
            prod = _product(session, cost="1000", selling="2000", qty=20)

        with session_scope(session_factory) as session:
            make_sale(session, cust, admin, items=[(prod, 1)], payment_method=PAYMENT_POS)
            make_sale(session, cust, admin, items=[(prod, 3)], payment_method=PAYMENT_TRANSFER)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            result = svc.dashboard_summary(admin, date.today())
            assert result.total_sales == Decimal("8000")
            assert result.transaction_count == 2
            assert result.pos_total == Decimal("2000")
            assert result.transfer_total == Decimal("6000")

    def test_dashboard_filters_by_date(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            cust = _customer(session)
            prod = _product(session, cost="1000", selling="2000", qty=20)

        yesterday = datetime.now() - timedelta(days=1)
        with session_scope(session_factory) as session:
            make_sale(
                session, cust, admin,
                sale_date=yesterday,
                items=[(prod, 1)],
                payment_method=PAYMENT_POS,
            )

        with session_scope(session_factory) as session:
            make_sale(session, cust, admin, items=[(prod, 2)], payment_method=PAYMENT_POS)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            result = svc.dashboard_summary(admin, date.today())
            assert result.total_sales == Decimal("4000")
            assert result.transaction_count == 1


# -- Sales Report tests ---------------------------------------------------- #

class TestSalesReport:
    def test_empty_sales_report(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            result = svc.sales_report(admin, start, end)
            assert result.transaction_count == 0
            assert result.total_sales == Decimal("0")
            assert len(result.rows) == 0

    def test_sales_report_with_data(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            cust = _customer(session)
            prod = _product(session, cost="1500", selling="2500", qty=10)

        with session_scope(session_factory) as session:
            make_sale(session, cust, admin, items=[(prod, 2)], payment_method=PAYMENT_POS)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            result = svc.sales_report(admin, start, end)
            assert result.transaction_count == 1
            assert result.total_sales == Decimal("5000")
            assert result.rows[0].payment_method == "POS"

    def test_sales_report_filters_by_date(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            cust = _customer(session)
            prod = _product(session, cost="1000", selling="2000", qty=20)

        yesterday = datetime.now() - timedelta(days=1)
        with session_scope(session_factory) as session:
            make_sale(session, cust, admin, sale_date=yesterday, items=[(prod, 1)])
            make_sale(session, cust, admin, items=[(prod, 2)])

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            result = svc.sales_report(admin, start, end)
            assert result.transaction_count == 1
            assert result.total_sales == Decimal("4000")


# -- Profit Report tests --------------------------------------------------- #

class TestProfitReport:
    def test_empty_profit_report(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            result = svc.profit_report(admin, start, end)
            assert result.total_sales == Decimal("0")
            assert result.cogs == Decimal("0")
            assert result.gross_profit == Decimal("0")
            assert result.total_expenses == Decimal("0")
            assert result.net_profit == Decimal("0")

    def test_profit_report_with_sales_and_expenses(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            cust = _customer(session)
            prod = _product(session, cost="1000", selling="2000", qty=10)

        with session_scope(session_factory) as session:
            make_sale(session, cust, admin, items=[(prod, 3)])
            _make_expense(session, admin, amount="500", category="Rent")

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            result = svc.profit_report(admin, start, end)
            assert result.total_sales == Decimal("6000")
            assert result.cogs == Decimal("3000")
            assert result.gross_profit == Decimal("3000")
            assert result.total_expenses == Decimal("500")
            assert result.net_profit == Decimal("2500")

    def test_profit_uses_historical_cost(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            cust = _customer(session)
            prod = _product(session, cost="1000", selling="2000", qty=10)

        with session_scope(session_factory) as session:
            make_sale(session, cust, admin, items=[(prod, 1)])

        with session_scope(session_factory) as session:
            from app.data.models import Product
            from sqlalchemy import select
            p = session.scalars(select(Product).where(Product.id == prod.id)).one()
            p.cost_price = Decimal("1500")
            session.flush()

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            result = svc.profit_report(admin, start, end)
            assert result.cogs == Decimal("1000")
            assert result.gross_profit == Decimal("1000")


# -- Inventory Report tests ------------------------------------------------ #

class TestInventoryReport:
    def test_empty_inventory(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            result = svc.inventory_report(admin)
            assert result.total_value == Decimal("0")
            assert result.total_products == 0

    def test_inventory_with_products(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            _product(session, name="Widget", cost="1000", selling="2000", qty=5)
            _product(session, name="Gadget", cost="500", selling="1000", qty=10)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            result = svc.inventory_report(admin)
            assert result.total_products == 2
            assert result.total_value == Decimal("10000")

    def test_inventory_value_uses_current_cost(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            _product(session, cost="1000", selling="2000", qty=5)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            result = svc.inventory_report(admin)
            assert result.total_value == Decimal("5000")


# -- Low Stock Report tests ------------------------------------------------ #

class TestLowStockReport:
    def test_no_low_stock(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            _product(session, qty=10)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            result = svc.low_stock_report(admin)
            assert len(result) == 0

    def test_low_stock_products(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            _product(session, name="Low Item", qty=2)
            _product(session, name="Ok Item", qty=10)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            result = svc.low_stock_report(admin)
            assert len(result) == 1
            assert result[0].product_name == "Low Item"
            assert result[0].quantity == 2

    def test_low_stock_custom_threshold(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            _product(session, name="Mid Item", qty=5)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            result = svc.low_stock_report(admin, threshold=5)
            assert len(result) == 1


# -- Payment Report tests -------------------------------------------------- #

class TestPaymentReport:
    def test_empty_payments(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            result = svc.payment_report(admin, start, end)
            assert result.pos_total == Decimal("0")
            assert result.transfer_total == Decimal("0")
            assert len(result.rows) == 0

    def test_payments_pos_and_transfer(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            cust = _customer(session)
            prod = _product(session, cost="1000", selling="2000", qty=10)

        with session_scope(session_factory) as session:
            make_sale(session, cust, admin, items=[(prod, 1)], payment_method=PAYMENT_POS)
            make_sale(session, cust, admin, items=[(prod, 2)], payment_method=PAYMENT_TRANSFER)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            result = svc.payment_report(admin, start, end)
            assert result.pos_total == Decimal("2000")
            assert result.transfer_total == Decimal("4000")
            assert result.grand_total == Decimal("6000")
            assert len(result.rows) == 2


# -- Purchase Report tests ------------------------------------------------- #

class TestPurchaseReport:
    def test_empty_purchases(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            result = svc.purchase_report(admin, start, end)
            assert result.total_cost == Decimal("0")
            assert len(result.rows) == 0


# -- Expense Report tests -------------------------------------------------- #

class TestExpenseReport:
    def test_empty_expenses(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            result = svc.expense_report(admin, start, end)
            assert result.total_expenses == Decimal("0")
            assert len(result.rows) == 0

    def test_expenses_with_data(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            _make_expense(session, admin, amount="500", category="Rent")
            _make_expense(session, admin, amount="200", category="Transport")

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            result = svc.expense_report(admin, start, end)
            assert result.total_expenses == Decimal("700")
            assert len(result.rows) == 2


# -- Product Sales Report tests -------------------------------------------- #

class TestProductSalesReport:
    def test_empty_product_sales(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            result = svc.product_sales_report(admin, start, end)
            assert len(result) == 0

    def test_product_sales_with_data(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            cust = _customer(session)
            prod = _product(session, name="Widget", cost="1000", selling="2000", qty=10)

        with session_scope(session_factory) as session:
            make_sale(session, cust, admin, items=[(prod, 3)])

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            result = svc.product_sales_report(admin, start, end)
            assert len(result) == 1
            assert result[0].product_name == "Widget"
            assert result[0].quantity_sold == 3
            assert result[0].revenue == Decimal("6000")
            assert result[0].cost == Decimal("3000")
            assert result[0].profit == Decimal("3000")


# -- Cashier Sales Report tests -------------------------------------------- #

class TestCashierSalesReport:
    def test_empty_cashier_sales(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            result = svc.cashier_sales_report(admin, start, end)
            assert len(result) == 0

    def test_cashier_sales_by_multiple_users(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            cashier = _cashier(session)
            cust = _customer(session)
            prod = _product(session, cost="1000", selling="2000", qty=20)

        with session_scope(session_factory) as session:
            make_sale(session, cust, admin, items=[(prod, 2)])
            make_sale(session, cust, cashier, items=[(prod, 1)])

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            result = svc.cashier_sales_report(admin, start, end)
            assert len(result) == 2
            assert result[0].cashier_name == "Admin User"
            assert result[0].total_sales == Decimal("4000")
            assert result[1].cashier_name == "Cashier User"
            assert result[1].total_sales == Decimal("2000")


# -- End of Day Report tests ----------------------------------------------- #

class TestEndOfDayReport:
    def test_empty_end_of_day(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            result = svc.end_of_day_report(admin, date.today())
            assert result.total_sales == Decimal("0")
            assert result.transaction_count == 0

    def test_end_of_day_with_data(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            cust = _customer(session)
            prod = _product(session, cost="1000", selling="2000", qty=10)

        with session_scope(session_factory) as session:
            make_sale(session, cust, admin, items=[(prod, 2)])
            _make_expense(session, admin, amount="300", category="Transport")

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            result = svc.end_of_day_report(admin, date.today())
            assert result.total_sales == Decimal("4000")
            assert result.transaction_count == 1


# -- Date boundary tests --------------------------------------------------- #

class TestDateBoundaries:
    def test_report_excludes_out_of_range(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            cust = _customer(session)
            prod = _product(session, cost="1000", selling="2000", qty=20)

        old_date = datetime.now() - timedelta(days=5)
        with session_scope(session_factory) as session:
            make_sale(session, cust, admin, sale_date=old_date, items=[(prod, 1)])

        with session_scope(session_factory) as session:
            make_sale(session, cust, admin, items=[(prod, 2)])

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            result = svc.sales_report(admin, start, end)
            assert result.transaction_count == 1
            assert result.total_sales == Decimal("4000")

    def test_report_with_specific_date_range(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            cust = _customer(session)
            prod = _product(session, cost="1000", selling="2000", qty=20)

        d3 = datetime.now() - timedelta(days=3)
        d1 = datetime.now() - timedelta(days=1)

        with session_scope(session_factory) as session:
            make_sale(session, cust, admin, sale_date=d3, items=[(prod, 1)])
            make_sale(session, cust, admin, sale_date=d1, items=[(prod, 2)])

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start = datetime.combine(date.today() - timedelta(days=2), time.min)
            end = datetime.combine(date.today(), time.max)
            result = svc.sales_report(admin, start, end)
            assert result.transaction_count == 1
            assert result.total_sales == Decimal("4000")


# -- Decimal / money precision tests --------------------------------------- #

class TestMoneyPrecision:
    def test_decimal_totals_not_float(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            cust = _customer(session)
            prod = _product(session, cost="1333.33", selling="2666.67", qty=10)

        with session_scope(session_factory) as session:
            make_sale(session, cust, admin, items=[(prod, 3)])

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            result = svc.sales_report(admin, start, end)
            assert isinstance(result.total_sales, Decimal)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            result = svc.profit_report(admin, start, end)
            assert isinstance(result.cogs, Decimal)
            assert isinstance(result.gross_profit, Decimal)

    def test_dashboard_returns_decimal(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            result = svc.dashboard_summary(admin, date.today())
            assert isinstance(result.total_sales, Decimal)
            assert isinstance(result.gross_profit, Decimal)
            assert isinstance(result.net_profit, Decimal)


# -- Offline operation test ------------------------------------------------ #

class TestOfflineOperation:
    def test_all_reports_use_local_database(self, session_factory):
        with session_scope(session_factory) as session:
            admin = _admin(session)
            cust = _customer(session)
            prod = _product(session, cost="1000", selling="2000", qty=10)

        with session_scope(session_factory) as session:
            make_sale(session, cust, admin, items=[(prod, 1)])
            _make_expense(session, admin, amount="100")

        with session_scope(session_factory) as session:
            svc = ReportingService(session)
            start, end = _today_range()
            svc.dashboard_summary(admin, date.today())
            svc.sales_report(admin, start, end)
            svc.profit_report(admin, start, end)
            svc.inventory_report(admin)
            svc.low_stock_report(admin)
            svc.payment_report(admin, start, end)
            svc.purchase_report(admin, start, end)
            svc.expense_report(admin, start, end)
            svc.product_sales_report(admin, start, end)
            svc.cashier_sales_report(admin, start, end)
            svc.end_of_day_report(admin, date.today())
