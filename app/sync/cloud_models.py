"""Cloud-side SQLAlchemy models.

These models mirror the local SQLite schema but are designed for PostgreSQL.
The cloud uses ``sync_uuid`` as the unique identifier (never exposes local
integer ``id``).  Foreign keys use ``sync_uuid`` references so that data
from multiple independent devices can coexist in one cloud database.

Users are intentionally excluded — credentials never leave the local PC.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now()


class CloudBase(DeclarativeBase):
    """Declarative base for cloud models."""


class DeviceRegistry(CloudBase):
    """Registered device (PC installation) allowed to sync."""

    __tablename__ = "device_registry"

    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    device_name: Mapped[str] = mapped_column(String(150))
    api_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)


class CloudCategory(CloudBase):
    __tablename__ = "categories"

    sync_uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer, default=1)
    device_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CloudProduct(CloudBase):
    __tablename__ = "products"

    sync_uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    product_code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(200))
    category_sync_uuid: Mapped[str | None] = mapped_column(String(36))
    brand: Mapped[str | None] = mapped_column(String(120))
    size: Mapped[str | None] = mapped_column(String(30))
    color: Mapped[str | None] = mapped_column(String(50))
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    selling_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    minimum_stock: Mapped[int] = mapped_column(Integer, default=3)
    barcode: Mapped[str] = mapped_column(String(80))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    device_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CloudCustomer(CloudBase):
    __tablename__ = "customers"

    sync_uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    device_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CloudSupplier(CloudBase):
    __tablename__ = "suppliers"

    sync_uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    phone: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    device_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CloudSale(CloudBase):
    __tablename__ = "sales"

    sync_uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    receipt_no: Mapped[str] = mapped_column(String(50))
    customer_sync_uuid: Mapped[str] = mapped_column(String(36))
    cashier_name: Mapped[str] = mapped_column(String(150))
    sale_date: Mapped[datetime] = mapped_column(DateTime)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount_type: Mapped[str | None] = mapped_column(String(20))
    discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    payment_method: Mapped[str] = mapped_column(String(20))
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    device_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CloudSaleItem(CloudBase):
    __tablename__ = "sale_items"

    sync_uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    sale_sync_uuid: Mapped[str] = mapped_column(String(36))
    product_sync_uuid: Mapped[str] = mapped_column(String(36))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    device_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CloudPayment(CloudBase):
    __tablename__ = "payments"

    sync_uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    sale_sync_uuid: Mapped[str] = mapped_column(String(36))
    payment_method: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    reference: Mapped[str | None] = mapped_column(String(100))
    payment_date: Mapped[datetime] = mapped_column(DateTime)
    recorded_by_name: Mapped[str] = mapped_column(String(150))
    device_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CloudInventoryLog(CloudBase):
    __tablename__ = "inventory_logs"

    sync_uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    product_sync_uuid: Mapped[str] = mapped_column(String(36))
    change_quantity: Mapped[int] = mapped_column(Integer)
    previous_quantity: Mapped[int] = mapped_column(Integer)
    new_quantity: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(255))
    reference_type: Mapped[str | None] = mapped_column(String(50))
    reference_id: Mapped[int | None] = mapped_column(Integer)
    user_name: Mapped[str] = mapped_column(String(150))
    device_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CloudPurchase(CloudBase):
    __tablename__ = "purchases"

    sync_uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    supplier_sync_uuid: Mapped[str] = mapped_column(String(36))
    purchase_date: Mapped[datetime] = mapped_column(DateTime)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    created_by_name: Mapped[str] = mapped_column(String(150))
    device_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CloudPurchaseItem(CloudBase):
    __tablename__ = "purchase_items"

    sync_uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    purchase_sync_uuid: Mapped[str] = mapped_column(String(36))
    product_sync_uuid: Mapped[str] = mapped_column(String(36))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    device_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CloudExpense(CloudBase):
    __tablename__ = "expenses"

    sync_uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    category: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    expense_date: Mapped[datetime] = mapped_column(DateTime)
    created_by_name: Mapped[str] = mapped_column(String(150))
    device_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CloudExchange(CloudBase):
    __tablename__ = "exchanges"

    sync_uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_sale_sync_uuid: Mapped[str] = mapped_column(String(36))
    customer_sync_uuid: Mapped[str] = mapped_column(String(36))
    approved_by_name: Mapped[str] = mapped_column(String(150))
    exchange_date: Mapped[datetime] = mapped_column(DateTime)
    difference_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    difference_type: Mapped[str] = mapped_column(String(20))
    payment_method: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="COMPLETED")
    device_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CloudExchangeItem(CloudBase):
    __tablename__ = "exchange_items"

    sync_uuid: Mapped[str] = mapped_column(String(36), primary_key=True)
    exchange_sync_uuid: Mapped[str] = mapped_column(String(36))
    original_product_sync_uuid: Mapped[str] = mapped_column(String(36))
    replacement_product_sync_uuid: Mapped[str] = mapped_column(String(36))
    original_quantity: Mapped[int] = mapped_column(Integer)
    replacement_quantity: Mapped[int] = mapped_column(Integer)
    original_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    replacement_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    device_id: Mapped[str] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class CloudSyncLog(CloudBase):
    """Immutable audit log of every sync mutation applied to the cloud."""

    __tablename__ = "sync_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    operation: Mapped[str] = mapped_column(String(20))
    sync_uuid: Mapped[str] = mapped_column(String(36), index=True)
    device_id: Mapped[str] = mapped_column(String(36))
    version: Mapped[int] = mapped_column(Integer, default=1)
    accepted: Mapped[bool] = mapped_column(Boolean, default=True)
    conflict_reason: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
