"""Reporting repository — read-only aggregation queries for Phase 08.

All queries use database-level aggregation where possible to avoid loading
unnecessary rows into memory. Money values are ``Decimal``; profit and
inventory calculations must never use floating-point.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from app.data.models import (
    Customer,
    Expense,
    LOW_STOCK_THRESHOLD,
    Payment,
    Product,
    Purchase,
    PurchaseItem,
    Sale,
    SaleItem,
    User,
)
from app.data.repositories.base import BaseRepository


# --- Result dataclasses --------------------------------------------------- #


@dataclass(frozen=True)
class DashboardSummary:
    """Today's KPI widgets for the Admin dashboard."""

    total_sales: Decimal = Decimal("0")
    cogs: Decimal = Decimal("0")
    gross_profit: Decimal = Decimal("0")
    total_expenses: Decimal = Decimal("0")
    net_profit: Decimal = Decimal("0")
    transaction_count: int = 0
    pos_total: Decimal = Decimal("0")
    transfer_total: Decimal = Decimal("0")


@dataclass(frozen=True)
class SalesReportRow:
    """One sale in the sales report."""

    receipt_no: str
    sale_date: datetime
    customer_name: str
    cashier_name: str
    subtotal: Decimal
    discount_amount: Decimal
    total: Decimal
    payment_method: str


@dataclass(frozen=True)
class SalesReportSummary:
    """Period totals for the sales report."""

    total_sales: Decimal = Decimal("0")
    total_discounts: Decimal = Decimal("0")
    transaction_count: int = 0
    rows: tuple[SalesReportRow, ...] = ()


@dataclass(frozen=True)
class ProfitReportSummary:
    """Period profit breakdown."""

    total_sales: Decimal = Decimal("0")
    cogs: Decimal = Decimal("0")
    gross_profit: Decimal = Decimal("0")
    total_expenses: Decimal = Decimal("0")
    net_profit: Decimal = Decimal("0")


@dataclass(frozen=True)
class InventoryReportRow:
    """One product in the inventory report."""

    product_name: str
    category_name: str
    quantity: int
    cost_price: Decimal
    selling_price: Decimal
    inventory_value: Decimal
    minimum_stock: int
    status: str


@dataclass(frozen=True)
class InventoryReportSummary:
    """Inventory report totals."""

    total_value: Decimal = Decimal("0")
    total_products: int = 0
    low_stock_count: int = 0
    rows: tuple[InventoryReportRow, ...] = ()


@dataclass(frozen=True)
class LowStockReportRow:
    """One low-stock product."""

    product_name: str
    quantity: int
    minimum_stock: int
    status: str


@dataclass(frozen=True)
class PaymentReportRow:
    """One payment in the payments report."""

    payment_method: str
    amount: Decimal
    reference: str
    payment_date: datetime
    recorded_by_name: str
    receipt_no: str


@dataclass(frozen=True)
class PaymentReportSummary:
    """Payment report totals."""

    pos_total: Decimal = Decimal("0")
    transfer_total: Decimal = Decimal("0")
    grand_total: Decimal = Decimal("0")
    rows: tuple[PaymentReportRow, ...] = ()


@dataclass(frozen=True)
class PurchaseReportRow:
    """One purchase in the purchases report."""

    supplier_name: str
    purchase_date: datetime
    total_cost: Decimal
    amount_paid: Decimal
    balance: Decimal
    created_by_name: str


@dataclass(frozen=True)
class PurchaseReportSummary:
    """Purchase report totals."""

    total_cost: Decimal = Decimal("0")
    total_paid: Decimal = Decimal("0")
    total_balance: Decimal = Decimal("0")
    rows: tuple[PurchaseReportRow, ...] = ()


@dataclass(frozen=True)
class ExpenseReportRow:
    """One expense in the expenses report."""

    category: str
    description: str
    amount: Decimal
    expense_date: datetime
    created_by_name: str


@dataclass(frozen=True)
class ExpenseReportSummary:
    """Expense report totals."""

    total_expenses: Decimal = Decimal("0")
    rows: tuple[ExpenseReportRow, ...] = ()


@dataclass(frozen=True)
class ProductSalesReportRow:
    """One product's sales performance."""

    product_name: str
    quantity_sold: int
    revenue: Decimal
    cost: Decimal
    profit: Decimal


@dataclass(frozen=True)
class CashierSalesReportRow:
    """One cashier's sales performance."""

    cashier_name: str
    total_sales: Decimal
    transaction_count: int


@dataclass(frozen=True)
class EndOfDayReport:
    """Complete daily summary."""

    total_sales: Decimal = Decimal("0")
    cogs: Decimal = Decimal("0")
    gross_profit: Decimal = Decimal("0")
    total_expenses: Decimal = Decimal("0")
    net_profit: Decimal = Decimal("0")
    transaction_count: int = 0
    pos_total: Decimal = Decimal("0")
    transfer_total: Decimal = Decimal("0")
    sales_rows: tuple[SalesReportRow, ...] = ()
    expense_rows: tuple[ExpenseReportRow, ...] = ()


# --- Repository ----------------------------------------------------------- #


class ReportingRepository(BaseRepository[Any]):
    """Read-only aggregation queries for reports and dashboard.

    This repository does not write data. It wraps a SQLAlchemy session and
    executes aggregation queries that feed the reporting service.
    """

    model = None  # type: ignore[assignment]

    def __init__(self, session: Session) -> None:
        self.session = session

    # -- Dashboard --------------------------------------------------------- #

    def dashboard_summary(self, target_date: date) -> DashboardSummary:
        """Today's KPIs: sales, COGS, gross profit, expenses, net profit,
        transaction count, POS/Transfer totals."""
        start = datetime.combine(target_date, datetime.min.time())
        end = datetime.combine(target_date, datetime.max.time())

        # Today's sales totals
        sales_result = self.session.execute(
            select(
                func.coalesce(func.sum(Sale.total), 0),
                func.coalesce(func.sum(Sale.discount_amount), 0),
                func.count(Sale.id),
            ).where(Sale.sale_date >= start, Sale.sale_date <= end)
        ).one()
        total_sales = Decimal(str(sales_result[0]))
        transaction_count = int(sales_result[2])

        # Today's COGS (from sale_items with historical cost)
        cogs_result = self.session.execute(
            select(
                func.coalesce(
                    func.sum(SaleItem.quantity * SaleItem.cost_price), 0
                )
            )
            .join(Sale, SaleItem.sale_id == Sale.id)
            .where(Sale.sale_date >= start, Sale.sale_date <= end)
        ).scalar()
        cogs = Decimal(str(cogs_result))

        # Today's expenses
        expenses_result = self.session.execute(
            select(func.coalesce(func.sum(Expense.amount), 0)).where(
                Expense.expense_date >= start, Expense.expense_date <= end
            )
        ).scalar()
        total_expenses = Decimal(str(expenses_result))

        # Today's POS/Transfer totals
        payment_result = self.session.execute(
            select(
                Payment.payment_method,
                func.coalesce(func.sum(Payment.amount), 0),
            )
            .where(Payment.payment_date >= start, Payment.payment_date <= end)
            .group_by(Payment.payment_method)
        ).all()
        pos_total = Decimal("0")
        transfer_total = Decimal("0")
        for method, amount in payment_result:
            if method == "POS":
                pos_total = Decimal(str(amount))
            elif method == "TRANSFER":
                transfer_total = Decimal(str(amount))

        gross_profit = total_sales - cogs
        net_profit = gross_profit - total_expenses

        return DashboardSummary(
            total_sales=total_sales,
            cogs=cogs,
            gross_profit=gross_profit,
            total_expenses=total_expenses,
            net_profit=net_profit,
            transaction_count=transaction_count,
            pos_total=pos_total,
            transfer_total=transfer_total,
        )

    # -- Sales Report ------------------------------------------------------ #

    def sales_report(
        self, start: datetime, end: datetime, cashier_id: int | None = None
    ) -> SalesReportSummary:
        """List of sales in a date range with totals."""
        stmt = (
            select(Sale)
            .options(
                joinedload(Sale.customer),
                joinedload(Sale.cashier),
            )
            .where(Sale.sale_date >= start, Sale.sale_date <= end)
        )
        if cashier_id is not None:
            stmt = stmt.where(Sale.cashier_id == cashier_id)
        stmt = stmt.order_by(Sale.sale_date)

        sales = list(self.session.scalars(stmt).unique())

        rows = tuple(
            SalesReportRow(
                receipt_no=s.receipt_no,
                sale_date=s.sale_date,
                customer_name=s.customer.name if s.customer else "",
                cashier_name=s.cashier.full_name if s.cashier else "",
                subtotal=s.subtotal,
                discount_amount=s.discount_amount,
                total=s.total,
                payment_method=s.payment_method,
            )
            for s in sales
        )

        total_sales = sum((r.total for r in rows), Decimal("0"))
        total_discounts = sum((r.discount_amount for r in rows), Decimal("0"))

        return SalesReportSummary(
            total_sales=total_sales,
            total_discounts=total_discounts,
            transaction_count=len(rows),
            rows=rows,
        )

    # -- Profit Report ----------------------------------------------------- #

    def profit_report(self, start: datetime, end: datetime) -> ProfitReportSummary:
        """Period profit breakdown: sales, COGS, gross profit, expenses, net profit."""
        # Total sales
        sales_total = self.session.execute(
            select(func.coalesce(func.sum(Sale.total), 0)).where(
                Sale.sale_date >= start, Sale.sale_date <= end
            )
        ).scalar()

        # COGS (historical cost from sale_items)
        cogs_total = self.session.execute(
            select(
                func.coalesce(
                    func.sum(SaleItem.quantity * SaleItem.cost_price), 0
                )
            )
            .join(Sale, SaleItem.sale_id == Sale.id)
            .where(Sale.sale_date >= start, Sale.sale_date <= end)
        ).scalar()

        # Expenses
        expenses_total = self.session.execute(
            select(func.coalesce(func.sum(Expense.amount), 0)).where(
                Expense.expense_date >= start, Expense.expense_date <= end
            )
        ).scalar()

        total_sales = Decimal(str(sales_total))
        cogs = Decimal(str(cogs_total))
        gross_profit = total_sales - cogs
        total_expenses = Decimal(str(expenses_total))
        net_profit = gross_profit - total_expenses

        return ProfitReportSummary(
            total_sales=total_sales,
            cogs=cogs,
            gross_profit=gross_profit,
            total_expenses=total_expenses,
            net_profit=net_profit,
        )

    # -- Inventory Report -------------------------------------------------- #

    def inventory_report(self) -> InventoryReportSummary:
        """All active products with inventory value."""
        stmt = (
            select(Product)
            .options(joinedload(Product.category))
            .where(Product.is_active.is_(True))
            .order_by(Product.name)
        )
        products = list(self.session.scalars(stmt).unique())

        rows = tuple(
            InventoryReportRow(
                product_name=p.name,
                category_name=p.category.name if p.category else "",
                quantity=p.quantity,
                cost_price=p.cost_price,
                selling_price=p.selling_price,
                inventory_value=p.cost_price * p.quantity,
                minimum_stock=p.minimum_stock,
                status="LOW" if p.quantity <= LOW_STOCK_THRESHOLD else "OK",
            )
            for p in products
        )

        total_value = sum((r.inventory_value for r in rows), Decimal("0"))
        low_stock_count = sum(1 for r in rows if r.status == "LOW")

        return InventoryReportSummary(
            total_value=total_value,
            total_products=len(rows),
            low_stock_count=low_stock_count,
            rows=rows,
        )

    # -- Low Stock Report -------------------------------------------------- #

    def low_stock_report(
        self, threshold: int = LOW_STOCK_THRESHOLD
    ) -> tuple[LowStockReportRow, ...]:
        """Products at or below the low-stock threshold."""
        stmt = (
            select(Product)
            .where(Product.is_active.is_(True), Product.quantity <= threshold)
            .order_by(Product.quantity, Product.name)
        )
        products = list(self.session.scalars(stmt))

        return tuple(
            LowStockReportRow(
                product_name=p.name,
                quantity=p.quantity,
                minimum_stock=p.minimum_stock,
                status="LOW",
            )
            for p in products
        )

    # -- Payment Report ---------------------------------------------------- #

    def payment_report(
        self, start: datetime, end: datetime
    ) -> PaymentReportSummary:
        """Payments in a date range with POS/Transfer totals."""
        stmt = (
            select(Payment)
            .options(
                joinedload(Payment.recorded_by_user),
                joinedload(Payment.sale),
            )
            .where(Payment.payment_date >= start, Payment.payment_date <= end)
            .order_by(Payment.payment_date)
        )
        payments = list(self.session.scalars(stmt).unique())

        rows = tuple(
            PaymentReportRow(
                payment_method=p.payment_method,
                amount=p.amount,
                reference=p.reference or "",
                payment_date=p.payment_date,
                recorded_by_name=(
                    p.recorded_by_user.full_name
                    if p.recorded_by_user
                    else ""
                ),
                receipt_no=p.sale.receipt_no if p.sale else "",
            )
            for p in payments
        )

        pos_total = sum(
            (r.amount for r in rows if r.payment_method == "POS"), Decimal("0")
        )
        transfer_total = sum(
            (r.amount for r in rows if r.payment_method == "TRANSFER"),
            Decimal("0"),
        )

        return PaymentReportSummary(
            pos_total=pos_total,
            transfer_total=transfer_total,
            grand_total=pos_total + transfer_total,
            rows=rows,
        )

    # -- Purchase Report --------------------------------------------------- #

    def purchase_report(
        self, start: datetime, end: datetime
    ) -> PurchaseReportSummary:
        """Purchases in a date range with totals."""
        stmt = (
            select(Purchase)
            .options(
                joinedload(Purchase.supplier),
                joinedload(Purchase.created_by_user),
            )
            .where(Purchase.purchase_date >= start, Purchase.purchase_date <= end)
            .order_by(Purchase.purchase_date)
        )
        purchases = list(self.session.scalars(stmt).unique())

        rows = tuple(
            PurchaseReportRow(
                supplier_name=p.supplier.name if p.supplier else "",
                purchase_date=p.purchase_date,
                total_cost=p.total_cost,
                amount_paid=p.amount_paid,
                balance=p.balance,
                created_by_name=(
                    p.created_by_user.full_name
                    if p.created_by_user
                    else ""
                ),
            )
            for p in purchases
        )

        total_cost = sum((r.total_cost for r in rows), Decimal("0"))
        total_paid = sum((r.amount_paid for r in rows), Decimal("0"))
        total_balance = sum((r.balance for r in rows), Decimal("0"))

        return PurchaseReportSummary(
            total_cost=total_cost,
            total_paid=total_paid,
            total_balance=total_balance,
            rows=rows,
        )

    # -- Expense Report ---------------------------------------------------- #

    def expense_report(
        self, start: datetime, end: datetime
    ) -> ExpenseReportSummary:
        """Expenses in a date range with totals."""
        stmt = (
            select(Expense)
            .options(joinedload(Expense.created_by_user))
            .where(
                Expense.expense_date >= start, Expense.expense_date <= end
            )
            .order_by(Expense.expense_date)
        )
        expenses = list(self.session.scalars(stmt).unique())

        rows = tuple(
            ExpenseReportRow(
                category=e.category,
                description=e.description or "",
                amount=e.amount,
                expense_date=e.expense_date,
                created_by_name=(
                    e.created_by_user.full_name
                    if e.created_by_user
                    else ""
                ),
            )
            for e in expenses
        )

        total_expenses = sum((r.amount for r in rows), Decimal("0"))

        return ExpenseReportSummary(
            total_expenses=total_expenses,
            rows=rows,
        )

    # -- Product Sales Report ---------------------------------------------- #

    def product_sales_report(
        self, start: datetime, end: datetime
    ) -> tuple[ProductSalesReportRow, ...]:
        """Per-product sales performance in a date range."""
        stmt = (
            select(
                Product.name,
                func.coalesce(func.sum(SaleItem.quantity), 0).label(
                    "qty_sold"
                ),
                func.coalesce(func.sum(SaleItem.line_total), 0).label(
                    "revenue"
                ),
                func.coalesce(
                    func.sum(SaleItem.quantity * SaleItem.cost_price), 0
                ).label("cost"),
            )
            .join(SaleItem, SaleItem.product_id == Product.id)
            .join(Sale, SaleItem.sale_id == Sale.id)
            .where(Sale.sale_date >= start, Sale.sale_date <= end)
            .group_by(Product.id, Product.name)
            .order_by(Product.name)
        )
        results = self.session.execute(stmt).all()

        return tuple(
            ProductSalesReportRow(
                product_name=row[0],
                quantity_sold=int(row[1]),
                revenue=Decimal(str(row[2])),
                cost=Decimal(str(row[3])),
                profit=Decimal(str(row[2])) - Decimal(str(row[3])),
            )
            for row in results
        )

    # -- Sales by Cashier Report ------------------------------------------- #

    def cashier_sales_report(
        self, start: datetime, end: datetime
    ) -> tuple[CashierSalesReportRow, ...]:
        """Per-cashier sales performance in a date range."""
        stmt = (
            select(
                User.full_name,
                func.coalesce(func.sum(Sale.total), 0).label("total_sales"),
                func.count(Sale.id).label("txn_count"),
            )
            .join(Sale, Sale.cashier_id == User.id)
            .where(Sale.sale_date >= start, Sale.sale_date <= end)
            .group_by(User.id, User.full_name)
            .order_by(User.full_name)
        )
        results = self.session.execute(stmt).all()

        return tuple(
            CashierSalesReportRow(
                cashier_name=row[0],
                total_sales=Decimal(str(row[1])),
                transaction_count=int(row[2]),
            )
            for row in results
        )

    # -- End of Day Report ------------------------------------------------- #

    def end_of_day_report(self, target_date: date) -> EndOfDayReport:
        """Complete daily summary combining sales, expenses, payments."""
        start = datetime.combine(target_date, datetime.min.time())
        end = datetime.combine(target_date, datetime.max.time())

        # Sales
        sales_summary = self.sales_report(start, end)

        # Profit
        profit_summary = self.profit_report(start, end)

        # Payments
        payment_summary = self.payment_report(start, end)

        # Expenses
        expense_summary = self.expense_report(start, end)

        return EndOfDayReport(
            total_sales=profit_summary.total_sales,
            cogs=profit_summary.cogs,
            gross_profit=profit_summary.gross_profit,
            total_expenses=expense_summary.total_expenses,
            net_profit=profit_summary.net_profit,
            transaction_count=sales_summary.transaction_count,
            pos_total=payment_summary.pos_total,
            transfer_total=payment_summary.transfer_total,
            sales_rows=sales_summary.rows,
            expense_rows=expense_summary.rows,
        )
