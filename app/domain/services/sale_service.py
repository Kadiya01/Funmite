"""Sale service (Phase 05).

A complete sale is a single atomic transaction:

    validate permissions and inputs
    -> create the sale header (receipt number, totals, payment method)
    -> create the sale item lines (with historical cost for later profit)
    -> record the payment (POS or Transfer only)
    -> deduct stock through ``InventoryService.change_stock`` (the one stock
       writer, shared with Phase 04 and reused by Phase 06 exchanges)

The caller owns the transaction (``session_scope``): if any step fails — e.g.
an item runs out of stock mid-sale — the whole sale is rolled back. Stock
sufficiency is enforced by ``change_stock`` itself so there is exactly one
place where "no negative stock" is decided.

Confirmed business rules enforced here (source-of-truth artifacts):

- Only Bank POS and Bank Transfer payments exist. Cash, credit, split payments
  and online gateways are not representable.
- A customer record is required for every sale.
- Admin is the only role that may apply a discount (``CAP_DISCOUNT``).
- Discount types are PERCENT or FIXED; a discount can never make the sale
  total negative (the confirmed "discount cannot make a sale total negative"
  rule). No ceiling/limit is invented.
- Receipt numbers follow the wireframe candidate ``FUN-YYYYMMDD-NNN`` (daily
  sequence); the exact prefix/format is still an open client decision and the
  database UNIQUE constraint is the final guard.
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.data.models import (
    DISCOUNT_FIXED,
    DISCOUNT_PERCENT,
    VALID_PAYMENT_METHODS,
    Payment,
    Product,
    Sale,
    SaleItem,
)
from app.data.repositories.customer_repository import CustomerRepository
from app.data.repositories.product_repository import ProductRepository
from app.data.repositories.sale_repository import SaleRepository
from app.domain.errors import NotFoundError, ValidationError
from app.domain.permissions import (
    CAP_DISCOUNT,
    CAP_MAKE_SALE,
    CAP_PROCESS_PAYMENT,
    require_permission,
)
from app.domain.rules.validation import parse_decimal, parse_quantity
from app.domain.services.inventory_service import REFERENCE_SALE, InventoryService
from app.domain.services.sync_service import SyncService
from app.domain.session import user_record_id

RECEIPT_PREFIX = "FUN"
RECEIPT_SEQUENCE_DIGITS = 3
SALE_ITEM_REASON = "Sale"

CENT = Decimal("0.01")


def money2(value) -> Decimal:
    """Round ``value`` to two decimal places (banker's-rounding-free half-up)."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


class SaleService:
    """Use-case service for completing offline POS sales."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.sales = SaleRepository(session)
        self.products = ProductRepository(session)
        self.customers = CustomerRepository(session)
        self.inventory = InventoryService(session)

    def _sync(self) -> SyncService:
        return SyncService(self.session)

    # --- queries ---------------------------------------------------------- #

    def get_by_receipt_no(self, receipt_no: str) -> Sale | None:
        return self.sales.get_by_receipt_no(receipt_no)

    # --- receipt numbers -------------------------------------------------- #

    def next_receipt_no(self, *, at: datetime | None = None) -> str:
        """Candidate receipt number ``FUN-YYYYMMDD-NNN`` (daily sequence)."""
        day = at or datetime.now()
        prefix = f"{RECEIPT_PREFIX}-{day.strftime('%Y%m%d')}-"
        sequence = self.sales.max_receipt_sequence(prefix) + 1
        return f"{prefix}{sequence:0{RECEIPT_SEQUENCE_DIGITS}d}"

    # --- sale completion -------------------------------------------------- #

    def complete_sale(
        self,
        user,
        *,
        customer_id: int,
        items: list[dict],
        payment_method: str,
        discount: dict | None = None,
        reference: str | None = None,
        sale_date: datetime | None = None,
    ) -> Sale:
        """Complete one atomic sale and return its header.

        ``items`` is a list of ``{"product_id": int, "quantity": int}`` cart
        lines. Stock is deducted per line through the shared inventory writer;
        any failure rolls the entire transaction back.
        """
        require_permission(user, CAP_MAKE_SALE)
        require_permission(user, CAP_PROCESS_PAYMENT)

        customer = self.customers.get(customer_id)
        if customer is None:
            raise NotFoundError("Customer not found.")

        if not items:
            raise ValidationError("A sale must contain at least one item.")

        payment_method = self._validate_payment_method(payment_method)

        lines = self._validate_lines(items)

        discount_type, discount_value, discount_amount = self._discount(user, lines, discount)

        subtotal = self._subtotal(lines)
        total = money2(subtotal - discount_amount)
        if total < 0:
            raise ValidationError("Discount cannot be more than the sale total.")

        sale_date = sale_date or datetime.now()
        sale = Sale(
            receipt_no=self.next_receipt_no(at=sale_date),
            customer_id=customer.id,
            cashier_id=user_record_id(user),
            sale_date=sale_date,
            subtotal=subtotal,
            discount_type=discount_type,
            discount_value=discount_value,
            discount_amount=discount_amount,
            total=total,
            payment_method=payment_method,
            amount_paid=total,
        )
        self.sales.add(sale)
        self.session.flush()

        for product, quantity in lines:
            self.session.add(
                SaleItem(
                    sale_id=sale.id,
                    product_id=product.id,
                    quantity=quantity,
                    unit_price=money2(product.selling_price),
                    cost_price=money2(product.cost_price),
                    line_total=money2(Decimal(product.selling_price) * quantity),
                )
            )

        payment_obj = None
        if total > 0:
            payment_obj = Payment(
                sale_id=sale.id,
                payment_method=payment_method,
                amount=money2(total),
                reference=(reference or "").strip() or None,
                payment_date=sale_date,
                recorded_by=user_record_id(user),
            )
            self.session.add(payment_obj)

        self.session.flush()

        sync = self._sync()
        sync.enqueue_create("sale", sale.id, {
            "sync_uuid": sale.sync_uuid,
            "receipt_no": sale.receipt_no,
            "customer_id": sale.customer_id,
            "cashier_id": sale.cashier_id,
            "sale_date": str(sale.sale_date),
            "subtotal": str(sale.subtotal),
            "discount_type": sale.discount_type,
            "discount_value": str(sale.discount_value),
            "discount_amount": str(sale.discount_amount),
            "total": str(sale.total),
            "payment_method": sale.payment_method,
            "amount_paid": str(sale.amount_paid),
        })
        for si in sale.items:
            sync.enqueue_create("sale_item", si.id, {
                "sync_uuid": si.sync_uuid,
                "sale_id": si.sale_id,
                "product_id": si.product_id,
                "quantity": si.quantity,
                "unit_price": str(si.unit_price),
                "cost_price": str(si.cost_price),
                "line_total": str(si.line_total),
            })
        if payment_obj is not None:
            sync.enqueue_create("payment", payment_obj.id, {
                "sync_uuid": payment_obj.sync_uuid,
                "sale_id": payment_obj.sale_id,
                "payment_method": payment_obj.payment_method,
                "amount": str(payment_obj.amount),
                "reference": payment_obj.reference,
                "payment_date": str(payment_obj.payment_date),
                "recorded_by": payment_obj.recorded_by,
            })

        for product, quantity in lines:
            try:
                self.inventory.change_stock(
                    user,
                    product.id,
                    -quantity,
                    SALE_ITEM_REASON,
                    reference_type=REFERENCE_SALE,
                    reference_id=sale.id,
                    capability=CAP_MAKE_SALE,
                )
            except ValidationError:
                raise ValidationError(
                    f"Insufficient stock for '{product.name}': "
                    f"requested {quantity}, available {product.quantity}."
                ) from None

        return sale

    # --- helpers ---------------------------------------------------------- #

    def _validate_lines(self, items: list[dict]) -> list[tuple[Product, int]]:
        lines: list[tuple[Product, int]] = []
        seen: set[int] = set()
        for entry in items:
            try:
                product_id = int(entry["product_id"])
            except (KeyError, TypeError, ValueError):
                raise ValidationError("Every cart line needs a product.") from None
            quantity = parse_quantity(entry.get("quantity"), "quantity", minimum=1)

            product = self.products.get(product_id)
            if product is None:
                raise NotFoundError("Product not found.")
            if not product.is_active:
                raise ValidationError(f"'{product.name}' is not active and cannot be sold.")
            if product_id in seen:
                raise ValidationError(f"'{product.name}' appears more than once in the cart.")
            seen.add(product_id)
            lines.append((product, quantity))
        return lines

    @staticmethod
    def _validate_payment_method(payment_method: str) -> str:
        value = (payment_method or "").strip().upper()
        if value not in VALID_PAYMENT_METHODS:
            raise ValidationError(
                f"Payment method '{payment_method}' is not supported. "
                "Only Bank POS and Bank Transfer are accepted."
            )
        return value

    def _discount(
        self,
        user,
        lines: list[tuple[Product, int]],
        discount: dict | None,
    ) -> tuple[str | None, Decimal, Decimal]:
        if not discount:
            return None, Decimal("0"), Decimal("0")
        require_permission(user, CAP_DISCOUNT)

        discount_type = str(discount.get("type") or "").strip().upper()
        value = discount.get("value")
        subtotal = self._subtotal(lines)

        if discount_type == DISCOUNT_PERCENT:
            percent = parse_decimal(value, "discount percentage")
            amount = money2(subtotal * percent / Decimal("100"))
            return discount_type, money2(percent), amount
        if discount_type == DISCOUNT_FIXED:
            amount = money2(parse_decimal(value, "discount amount"))
            return discount_type, amount, amount
        raise ValidationError(
            f"Discount type '{discount_type}' is not supported. Use PERCENT or FIXED."
        )

    @staticmethod
    def _subtotal(lines: list[tuple[Product, int]]) -> Decimal:
        return money2(
            sum((Decimal(product.selling_price) * quantity for product, quantity in lines), Decimal("0"))
        )
