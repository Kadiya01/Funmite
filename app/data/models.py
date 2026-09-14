"""SQLAlchemy models for the Funmite POS database.

The schema mirrors ``funmite_production_candidate.sql`` together with
Engineering Artifacts 01 and 05. Money values use ``NUMERIC(12, 2)`` (read back
as ``Decimal``) to avoid floating-point errors. Timestamps are naive
shop-local datetimes set by the application so that daily reports and the
two-day exchange window follow the shop calendar.

Historical financial records are never deleted silently: there are no cascade
deletes on financial tables and users/products are deactivated via
``is_active`` instead of being removed.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# --------------------------------------------------------------------------- #
# Approved business value sets. The CHECK constraints below are generated from
# these constants so the Python layer and the database can never drift apart.
# --------------------------------------------------------------------------- #
ROLE_ADMIN = "ADMIN"
ROLE_CASHIER = "CASHIER"
VALID_ROLES = (ROLE_ADMIN, ROLE_CASHIER)

PAYMENT_POS = "POS"
PAYMENT_TRANSFER = "TRANSFER"
PAYMENT_CREDIT = "CREDIT"
VALID_PAYMENT_METHODS = (PAYMENT_POS, PAYMENT_TRANSFER, PAYMENT_CREDIT)

SALE_COMPLETED = "COMPLETED"
SALE_CANCELLED = "CANCELLED"
VALID_SALE_STATUSES = (SALE_COMPLETED, SALE_CANCELLED)

CREDIT_SOURCE_EXCHANGE = "EXCHANGE"
CREDIT_SOURCE_SALE_PAYMENT = "SALE_PAYMENT"
VALID_CREDIT_SOURCES = (CREDIT_SOURCE_EXCHANGE, CREDIT_SOURCE_SALE_PAYMENT)

DISCOUNT_PERCENT = "PERCENT"
DISCOUNT_FIXED = "FIXED"
VALID_DISCOUNT_TYPES = (DISCOUNT_PERCENT, DISCOUNT_FIXED)

DIFFERENCE_NONE = "NONE"
DIFFERENCE_CUSTOMER_PAYS = "CUSTOMER_PAYS"
DIFFERENCE_CUSTOMER_RECEIVES = "CUSTOMER_RECEIVES"
VALID_DIFFERENCE_TYPES = (
    DIFFERENCE_NONE,
    DIFFERENCE_CUSTOMER_PAYS,
    DIFFERENCE_CUSTOMER_RECEIVES,
)

EXCHANGE_COMPLETED = "COMPLETED"
EXCHANGE_CANCELLED = "CANCELLED"
VALID_EXCHANGE_STATUSES = (EXCHANGE_COMPLETED, EXCHANGE_CANCELLED)

SYNC_OP_CREATE = "CREATE"
SYNC_OP_UPDATE = "UPDATE"
SYNC_OP_DELETE = "DELETE"
VALID_SYNC_OPERATIONS = (SYNC_OP_CREATE, SYNC_OP_UPDATE, SYNC_OP_DELETE)

SYNC_STATUS_PENDING = "PENDING"
SYNC_STATUS_SYNCING = "SYNCING"
SYNC_STATUS_SYNCED = "SYNCED"
SYNC_STATUS_FAILED = "FAILED"
VALID_SYNC_STATUSES = (
    SYNC_STATUS_PENDING,
    SYNC_STATUS_SYNCING,
    SYNC_STATUS_SYNCED,
    SYNC_STATUS_FAILED,
)

# Confirmed business rule: a product is low on stock when quantity <= 3.
LOW_STOCK_THRESHOLD = 3
DEFAULT_MINIMUM_STOCK = 3


def _in_clause(values: tuple[str, ...]) -> str:
    """Render ``('A', 'B')`` for use inside a SQL CHECK constraint."""
    return ", ".join(f"'{value}'" for value in values)


def _now() -> datetime:
    return datetime.now()


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


class User(Base):
    """Authentication account. Role is restricted to ADMIN or CASHIER."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"role IN ({_in_clause(VALID_ROLES)})", name="ck_users_role"),
        CheckConstraint("is_active IN (0, 1)", name="ck_users_is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    full_name: Mapped[str] = mapped_column(String(150))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    sales: Mapped[list[Sale]] = relationship(
        back_populates="cashier", foreign_keys="Sale.cashier_id"
    )
    cancelled_sales: Mapped[list[Sale]] = relationship(
        back_populates="cancelled_by_user", foreign_keys="Sale.cancelled_by_user_id"
    )
    inventory_logs: Mapped[list[InventoryLog]] = relationship(back_populates="user")
    payments: Mapped[list[Payment]] = relationship(back_populates="recorded_by_user")
    purchases: Mapped[list[Purchase]] = relationship(back_populates="created_by_user")
    expenses: Mapped[list[Expense]] = relationship(back_populates="created_by_user")
    approved_exchanges: Mapped[list[Exchange]] = relationship(back_populates="approved_by_user")


class Category(Base):
    """Product category."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    sync_uuid: Mapped[str] = mapped_column(String(36), unique=True, default=_uuid)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    products: Mapped[list[Product]] = relationship(back_populates="category")


class Product(Base):
    """Master catalogue item with its own generated unique barcode."""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("cost_price >= 0", name="ck_products_cost_price"),
        CheckConstraint("selling_price >= 0", name="ck_products_selling_price"),
        CheckConstraint("quantity >= 0", name="ck_products_quantity"),
        CheckConstraint("minimum_stock >= 0", name="ck_products_minimum_stock"),
        Index("idx_products_category", "category_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    brand: Mapped[str | None] = mapped_column(String(120))
    size: Mapped[str | None] = mapped_column(String(30))
    color: Mapped[str | None] = mapped_column(String(50))
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    selling_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    minimum_stock: Mapped[int] = mapped_column(Integer, default=DEFAULT_MINIMUM_STOCK)
    barcode: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    image_path: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_uuid: Mapped[str] = mapped_column(String(36), unique=True, default=_uuid)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    category: Mapped[Category] = relationship(back_populates="products")
    sale_items: Mapped[list[SaleItem]] = relationship(back_populates="product")
    purchase_items: Mapped[list[PurchaseItem]] = relationship(back_populates="product")
    inventory_logs: Mapped[list[InventoryLog]] = relationship(back_populates="product")
    original_exchange_items: Mapped[list[ExchangeItem]] = relationship(
        back_populates="original_product",
        foreign_keys="ExchangeItem.original_product_id",
    )
    replacement_exchange_items: Mapped[list[ExchangeItem]] = relationship(
        back_populates="replacement_product",
        foreign_keys="ExchangeItem.replacement_product_id",
    )


class Customer(Base):
    """Shop customer. A customer record is required for every sale."""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_uuid: Mapped[str] = mapped_column(String(36), unique=True, default=_uuid)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    sales: Mapped[list[Sale]] = relationship(back_populates="customer")
    exchanges: Mapped[list[Exchange]] = relationship(back_populates="customer")
    credits: Mapped[list[CustomerCredit]] = relationship(back_populates="customer")


class CustomerCredit(Base):
    """Store-credit ledger line for one customer.

    The shop owes the customer when an exchange replacement is cheaper than the
    returned items (the no-cash rule forbids a cash refund), and the customer
    can spend the balance on a future sale. Balance is derived by summing the
    ledger rows: ``amount`` is always positive, source ``EXCHANGE`` adds to the
    balance and source ``SALE_PAYMENT`` (credit applied to a sale) subtracts it.
    Using a ledger instead of an absolute balance column keeps the two-PC
    convergence model idempotent, exactly like the inventory delta model.
    """

    __tablename__ = "customer_credits"
    __table_args__ = (
        CheckConstraint(
            f"source IN ({_in_clause(VALID_CREDIT_SOURCES)})",
            name="ck_customer_credits_source",
        ),
        CheckConstraint("amount > 0", name="ck_customer_credits_amount_positive"),
        Index("idx_customer_credits_customer", "customer_id"),
        Index("idx_customer_credits_source", "source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    source: Mapped[str] = mapped_column(String(20))
    exchange_id: Mapped[int | None] = mapped_column(ForeignKey("exchanges.id"))
    sale_id: Mapped[int | None] = mapped_column(ForeignKey("sales.id"))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    sync_uuid: Mapped[str] = mapped_column(String(36), unique=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    customer: Mapped[Customer] = relationship(back_populates="credits")
    exchange: Mapped[Exchange | None] = relationship()
    sale: Mapped[Sale | None] = relationship()


class Sale(Base):
    """Sale header. payment_method is restricted to POS, TRANSFER or CREDIT."""

    __tablename__ = "sales"
    __table_args__ = (
        CheckConstraint(f"payment_method IN ({_in_clause(VALID_PAYMENT_METHODS)})", name="ck_sales_payment_method"),
        CheckConstraint(f"status IN ({_in_clause(VALID_SALE_STATUSES)})", name="ck_sales_status"),
        CheckConstraint("subtotal >= 0", name="ck_sales_subtotal"),
        CheckConstraint(
            "discount_type IS NULL OR discount_type IN "
            f"({_in_clause(VALID_DISCOUNT_TYPES)})",
            name="ck_sales_discount_type",
        ),
        CheckConstraint("discount_value >= 0", name="ck_sales_discount_value"),
        CheckConstraint("discount_amount >= 0", name="ck_sales_discount_amount"),
        CheckConstraint("total >= 0", name="ck_sales_total"),
        CheckConstraint("amount_paid >= 0", name="ck_sales_amount_paid"),
        Index("idx_sales_date", "sale_date"),
        Index("idx_sales_cashier", "cashier_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_no: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    cashier_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    sale_date: Mapped[datetime] = mapped_column(DateTime)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount_type: Mapped[str | None] = mapped_column(String(20))
    discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    payment_method: Mapped[str] = mapped_column(String(20))
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(20), default=SALE_COMPLETED)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime)
    cancelled_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancel_reason: Mapped[str | None] = mapped_column(String(255))
    sync_uuid: Mapped[str] = mapped_column(String(36), unique=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    customer: Mapped[Customer] = relationship(back_populates="sales")
    cashier: Mapped[User] = relationship(back_populates="sales", foreign_keys=[cashier_id])
    cancelled_by_user: Mapped[User | None] = relationship(
        foreign_keys=[cancelled_by_user_id], back_populates="cancelled_sales"
    )
    items: Mapped[list[SaleItem]] = relationship(back_populates="sale")
    payments: Mapped[list[Payment]] = relationship(back_populates="sale")
    exchanges: Mapped[list[Exchange]] = relationship(back_populates="original_sale")


class SaleItem(Base):
    """One product line in a sale. cost_price is the historical unit cost."""

    __tablename__ = "sale_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sale_items_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_sale_items_unit_price"),
        CheckConstraint("cost_price >= 0", name="ck_sale_items_cost_price"),
        CheckConstraint("line_total >= 0", name="ck_sale_items_line_total"),
        Index("idx_sale_items_sale", "sale_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    sync_uuid: Mapped[str] = mapped_column(String(36), unique=True, default=_uuid)

    sale: Mapped[Sale] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(back_populates="sale_items")


class Payment(Base):
    """Payment received for a sale. Cash is not representable; store credit is."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            f"payment_method IN ({_in_clause(VALID_PAYMENT_METHODS)})",
            name="ck_payments_payment_method",
        ),
        CheckConstraint("amount > 0", name="ck_payments_amount"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"))
    payment_method: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reference: Mapped[str | None] = mapped_column(String(100))
    payment_date: Mapped[datetime] = mapped_column(DateTime)
    recorded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    sync_uuid: Mapped[str] = mapped_column(String(36), unique=True, default=_uuid)

    sale: Mapped[Sale] = relationship(back_populates="payments")
    recorded_by_user: Mapped[User] = relationship(back_populates="payments")


class InventoryLog(Base):
    """Every stock movement is recorded here with reason, user and reference."""

    __tablename__ = "inventory_logs"
    __table_args__ = (
        Index("idx_inventory_product_date", "product_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    change_quantity: Mapped[int] = mapped_column(Integer)
    previous_quantity: Mapped[int] = mapped_column(Integer)
    new_quantity: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(255))
    reference_type: Mapped[str | None] = mapped_column(String(50))
    reference_id: Mapped[int | None] = mapped_column(Integer)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    sync_uuid: Mapped[str] = mapped_column(String(36), unique=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    product: Mapped[Product] = relationship(back_populates="inventory_logs")
    user: Mapped[User] = relationship(back_populates="inventory_logs")


class Supplier(Base):
    """Supplier record for purchases."""

    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[str | None] = mapped_column(Text)
    sync_uuid: Mapped[str] = mapped_column(String(36), unique=True, default=_uuid)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    purchases: Mapped[list[Purchase]] = relationship(back_populates="supplier")


class Purchase(Base):
    """Stock-in header. balance semantics stay an open decision (see OPEN_DECISIONS)."""

    __tablename__ = "purchases"
    __table_args__ = (
        CheckConstraint("total_cost >= 0", name="ck_purchases_total_cost"),
        CheckConstraint("amount_paid >= 0", name="ck_purchases_amount_paid"),
        CheckConstraint("balance >= 0", name="ck_purchases_balance"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"))
    purchase_date: Mapped[datetime] = mapped_column(DateTime)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    sync_uuid: Mapped[str] = mapped_column(String(36), unique=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    supplier: Mapped[Supplier] = relationship(back_populates="purchases")
    created_by_user: Mapped[User] = relationship(back_populates="purchases")
    items: Mapped[list[PurchaseItem]] = relationship(back_populates="purchase")


class PurchaseItem(Base):
    """A product line received in a purchase."""

    __tablename__ = "purchase_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_purchase_items_quantity"),
        CheckConstraint("unit_cost >= 0", name="ck_purchase_items_unit_cost"),
        CheckConstraint("line_total >= 0", name="ck_purchase_items_line_total"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchases.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    sync_uuid: Mapped[str] = mapped_column(String(36), unique=True, default=_uuid)

    purchase: Mapped[Purchase] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(back_populates="purchase_items")


class Expense(Base):
    """Business expense, deducted from gross profit for net-profit reporting."""

    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expenses_amount"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    expense_date: Mapped[datetime] = mapped_column(DateTime)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    sync_uuid: Mapped[str] = mapped_column(String(36), unique=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    created_by_user: Mapped[User] = relationship(back_populates="expenses")


class Exchange(Base):
    """Exchange header linked to the original sale. Never deletes the sale."""

    __tablename__ = "exchanges"
    __table_args__ = (
        CheckConstraint(
            f"difference_type IN ({_in_clause(VALID_DIFFERENCE_TYPES)})",
            name="ck_exchanges_difference_type",
        ),
        CheckConstraint(
            "payment_method IS NULL OR payment_method IN "
            f"({_in_clause(VALID_PAYMENT_METHODS)})",
            name="ck_exchanges_payment_method",
        ),
        CheckConstraint(
            f"status IN ({_in_clause(VALID_EXCHANGE_STATUSES)})",
            name="ck_exchanges_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    original_sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    approved_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    exchange_date: Mapped[datetime] = mapped_column(DateTime)
    difference_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    difference_type: Mapped[str] = mapped_column(String(20))
    payment_method: Mapped[str | None] = mapped_column(String(20))
    override_reason: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default=EXCHANGE_COMPLETED)
    sync_uuid: Mapped[str] = mapped_column(String(36), unique=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    original_sale: Mapped[Sale] = relationship(back_populates="exchanges")
    customer: Mapped[Customer] = relationship(back_populates="exchanges")
    approved_by_user: Mapped[User] = relationship(back_populates="approved_exchanges")
    items: Mapped[list[ExchangeItem]] = relationship(back_populates="exchange")


class ExchangeItem(Base):
    """One returned product and its replacement product."""

    __tablename__ = "exchange_items"
    __table_args__ = (
        CheckConstraint("original_quantity > 0", name="ck_exchange_items_original_quantity"),
        CheckConstraint("replacement_quantity > 0", name="ck_exchange_items_replacement_quantity"),
        CheckConstraint("original_price >= 0", name="ck_exchange_items_original_price"),
        CheckConstraint("replacement_price >= 0", name="ck_exchange_items_replacement_price"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    exchange_id: Mapped[int] = mapped_column(ForeignKey("exchanges.id"))
    original_product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    replacement_product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    original_quantity: Mapped[int] = mapped_column(Integer)
    replacement_quantity: Mapped[int] = mapped_column(Integer)
    original_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    replacement_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    sync_uuid: Mapped[str] = mapped_column(String(36), unique=True, default=_uuid)

    exchange: Mapped[Exchange] = relationship(back_populates="items")
    original_product: Mapped[Product] = relationship(
        back_populates="original_exchange_items",
        foreign_keys=[original_product_id],
    )
    replacement_product: Mapped[Product] = relationship(
        back_populates="replacement_exchange_items",
        foreign_keys=[replacement_product_id],
    )


class SyncQueueItem(Base):
    """Pending local change destined for the cloud. Sync is Phase 10."""

    __tablename__ = "sync_queue"
    __table_args__ = (
        CheckConstraint(
            f"operation IN ({_in_clause(VALID_SYNC_OPERATIONS)})",
            name="ck_sync_queue_operation",
        ),
        CheckConstraint(
            f"status IN ({_in_clause(VALID_SYNC_STATUSES)})",
            name="ck_sync_queue_status",
        ),
        Index("idx_sync_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[int] = mapped_column(Integer)
    operation: Mapped[str] = mapped_column(String(20))
    payload: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=SYNC_STATUS_PENDING)
    device_id: Mapped[str | None] = mapped_column(String(100))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt: Mapped[datetime | None] = mapped_column(DateTime)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class SyncState(Base):
    """Per-device synchronization state."""

    __tablename__ = "sync_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(100), unique=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime)
    sync_version: Mapped[int] = mapped_column(Integer, default=0)


class AuditLog(Base):
    """Immutable record of sensitive actions (login, user management, etc.).

    Added in migration 002 to satisfy the audit-log requirement from the master
    specification and technical architecture. ``user_id`` is nullable because a
    failed login may reference a username that does not exist yet.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("idx_audit_created_at", "created_at"),
        Index("idx_audit_action", "action"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    username: Mapped[str | None] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(100))
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
