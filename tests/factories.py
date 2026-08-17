"""Helpers for building small, valid samples of the schema in tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.data.models import (
    PAYMENT_POS,
    ROLE_ADMIN,
    ROLE_CASHIER,
    Category,
    Customer,
    InventoryLog,
    Payment,
    Product,
    Sale,
    SaleItem,
    User,
)
from app.security.passwords import hash_password

_counter = 0


def next_code(prefix: str) -> str:
    global _counter
    _counter += 1
    return f"{prefix}-{_counter:05d}"


def make_user(
    session: Session,
    username: str | None = None,
    role: str = ROLE_ADMIN,
    password: str = "pass1234",
    full_name: str = "Test User",
) -> User:
    user = User(
        username=username or next_code("U"),
        password_hash=hash_password(password, iterations=10_000),
        role=role,
        full_name=full_name,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def make_category(session: Session, name: str | None = None) -> Category:
    category = Category(name=name or next_code("CAT"))
    session.add(category)
    session.flush()
    return category


def make_product(
    session: Session,
    category: Category,
    *,
    name: str = "Test Product",
    cost_price: Decimal | str | int = Decimal("1500"),
    selling_price: Decimal | str | int = Decimal("2500"),
    quantity: int = 10,
) -> Product:
    code = next_code("P")
    product = Product(
        product_code=code,
        name=name,
        category_id=category.id,
        cost_price=Decimal(cost_price),
        selling_price=Decimal(selling_price),
        quantity=quantity,
        barcode=f"BC{next_code('X')}",
        is_active=True,
    )
    session.add(product)
    session.flush()
    return product


def make_customer(session: Session, name: str = "Walk-in Customer") -> Customer:
    customer = Customer(customer_code=next_code("C"), name=name)
    session.add(customer)
    session.flush()
    return customer


def make_sale(
    session: Session,
    customer: Customer,
    cashier: User,
    *,
    sale_date: datetime | None = None,
    items: list[tuple[Product, int]] | None = None,
    payment_method: str = PAYMENT_POS,
) -> Sale:
    """Build a complete sale (header + items + payment + stock + logs)."""
    sale_date = sale_date or datetime.now()
    entries = items or []
    subtotal = Decimal("0")
    for product, quantity in entries:
        subtotal += Decimal(product.selling_price) * quantity
    total = subtotal

    sale = Sale(
        receipt_no=next_code("R"),
        customer_id=customer.id,
        cashier_id=cashier.id,
        sale_date=sale_date,
        subtotal=subtotal,
        discount_type=None,
        discount_value=Decimal("0"),
        discount_amount=Decimal("0"),
        total=total,
        payment_method=payment_method,
        amount_paid=total,
    )
    session.add(sale)
    session.flush()

    for product, quantity in entries:
        line_total = Decimal(product.selling_price) * quantity
        session.add(
            SaleItem(
                sale_id=sale.id,
                product_id=product.id,
                quantity=quantity,
                unit_price=Decimal(product.selling_price),
                cost_price=Decimal(product.cost_price),
                line_total=line_total,
            )
        )
        previous = product.quantity
        product.quantity -= quantity
        session.add(
            InventoryLog(
                product_id=product.id,
                change_quantity=-quantity,
                previous_quantity=previous,
                new_quantity=product.quantity,
                reason="SALE",
                reference_type="SALE",
                reference_id=sale.id,
                user_id=cashier.id,
            )
        )

    if total > 0:
        session.add(
            Payment(
                sale_id=sale.id,
                payment_method=payment_method,
                amount=total,
                payment_date=sale_date,
                recorded_by=cashier.id,
            )
        )
    session.flush()
    return sale


def make_recent_sale(
    session: Session,
    customer: Customer,
    cashier: User,
    days_old: int = 1,
    **kwargs,
) -> Sale:
    """A sale dated ``days_old`` days before now (for the exchange window)."""
    sale_date = datetime.now() - timedelta(days=days_old)
    return make_sale(session, customer, cashier, sale_date=sale_date, **kwargs)
