"""Sale service (Phase 05).

A complete sale is a single atomic transaction:

    validate permissions and inputs
    -> create the sale header (receipt number, totals, payment method)
    -> create the sale item lines (with historical cost for later profit)
    -> record the payment (POS, Transfer or store credit)
    -> deduct stock through ``InventoryService.change_stock`` (the one stock
       writer, shared with Phase 04 and reused by Phase 06 exchanges)

The caller owns the transaction (``session_scope``): if any step fails — e.g.
an item runs out of stock mid-sale — the whole sale is rolled back. Stock
sufficiency is enforced by ``change_stock`` itself so there is exactly one
place where "no negative stock" is decided.

Confirmed business rules enforced here (source-of-truth artifacts):

- Bank POS, Bank Transfer and store credit are accepted. Cash, online gateways
  and split payments are not representable.
- A customer record is required for every sale.
- Admin is the only role that may apply a discount (``CAP_DISCOUNT``).
- Discount types are PERCENT or FIXED; a discount can never make the sale
  total negative (the confirmed "discount cannot make a sale total negative"
  rule). No ceiling/limit is invented.
- Store credit can pay for a sale in full: the customer's credit ledger
  (``customer_credits``) is consumed with source ``SALE_PAYMENT`` and the
  sale is recorded with ``payment_method = CREDIT``.
- Receipt numbers follow ``{DEVICE}-YYYYMMDD-NNN`` (daily sequence per device),
  where ``DEVICE`` is a short code derived from the installation's persistent
  device id (``data/device.id``). This makes receipt numbers unique across
  multiple PCs (Phase 10C topology). When no device identity is provided the
  service falls back to the legacy ``FUN`` prefix so existing receipts and
  tests keep working; the database UNIQUE constraint remains the final guard.
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from app.data.models import (
    CREDIT_SOURCE_EXCHANGE,
    DISCOUNT_FIXED,
    DISCOUNT_PERCENT,
    EXCHANGE_COMPLETED,
    PAYMENT_CREDIT,
    SALE_CANCELLED,
    VALID_PAYMENT_METHODS,
    CustomerCredit,
    Payment,
    Product,
    Sale,
    SaleItem,
)
from app.data.repositories.customer_repository import CustomerRepository
from app.data.repositories.exchange_repository import ExchangeRepository
from app.data.repositories.product_repository import ProductRepository
from app.data.repositories.sale_repository import SaleRepository
from app.domain.errors import NotFoundError, ValidationError
from app.domain.permissions import (
    CAP_CANCEL_SALE,
    CAP_DISCOUNT,
    CAP_MAKE_SALE,
    CAP_PROCESS_PAYMENT,
    require_permission,
)
from app.domain.rules.validation import parse_decimal, parse_quantity
from app.domain.services.audit_service import ACTION_SALE_CANCELLED, AuditService
from app.domain.services.device_service import DeviceIdentity
from app.domain.services.inventory_service import (
    REFERENCE_SALE,
    REFERENCE_SALE_CANCELLED,
    InventoryService,
)
from app.domain.services.store_credit_service import StoreCreditService
from app.domain.services.sync_service import SyncService
from app.domain.session import user_record_id

RECEIPT_PREFIX = "FUN"
RECEIPT_SEQUENCE_DIGITS = 3
RECEIPT_DEVICE_CODE_LENGTH = 6
SALE_ITEM_REASON = "Sale"
SALE_CANCEL_REASON = "Sale cancellation (reversal)"

CENT = Decimal("0.01")


def money2(value) -> Decimal:
    """Round ``value`` to two decimal places (banker's-rounding-free half-up)."""
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


class SaleService:
    """Use-case service for completing offline POS sales."""

    def __init__(self, session: Session, device: DeviceIdentity | None = None) -> None:
        self.session = session
        self.sales = SaleRepository(session)
        self.products = ProductRepository(session)
        self.customers = CustomerRepository(session)
        self.exchanges = ExchangeRepository(session)
        self.inventory = InventoryService(session)
        self._device = device

    def _sync(self) -> SyncService:
        return SyncService(self.session)

    # --- queries ---------------------------------------------------------- #

    def get_by_receipt_no(self, receipt_no: str) -> Sale | None:
        return self.sales.get_by_receipt_no(receipt_no)

    # --- receipt numbers -------------------------------------------------- #

    def _device_code(self) -> str:
        """Short uppercase device code used as the receipt prefix.

        Excludes a provided ``DeviceIdentity`` so each PC mints its own
        collision-free daily sequence. Falls back to the legacy ``FUN``
        prefix when no device identity is available.
        """
        if self._device is None:
            return RECEIPT_PREFIX
        raw = self._device.device_id.replace("-", "").upper()
        code = "".join(ch for ch in raw if ch.isalnum())[:RECEIPT_DEVICE_CODE_LENGTH]
        return code or RECEIPT_PREFIX

    def next_receipt_no(self, *, at: datetime | None = None) -> str:
        """Receipt number ``{DEVICE}-YYYYMMDD-NNN`` (daily sequence per device)."""
        day = at or datetime.now()
        prefix = f"{self._device_code()}-{day.strftime('%Y%m%d')}-"
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
            if payment_method == PAYMENT_CREDIT:
                StoreCreditService(self.session).consume(
                    user,
                    customer_id=customer.id,
                    amount=total,
                    sale_id=sale.id,
                )

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

    # --- sale cancellation ------------------------------------------------ #

    def cancel_sale(
        self,
        user,
        *,
        receipt_no: str,
        reason: str,
        cancel_date: datetime | None = None,
    ) -> Sale:
        """Admin reverses + voids a completed sale (``CAP_CANCEL_SALE``).

        The sale is never deleted: its ``status`` becomes ``CANCELLED`` with
        ``cancelled_at``, ``cancelled_by_user_id`` and ``cancel_reason``, while
        the original header, item lines and payments stay in the history for
        audit. The sold stock is restored through the shared inventory writer
        (recorded as ``SALE_CANCELLED`` reversal movements), and any store
        credit the sale consumed is re-granted on the customer's ledger.

        A sale that already has a completed exchange cannot be cancelled: the
        exchange references the original sale, so the two-day window trade is
        what the customer walked away with.
        """
        require_permission(user, CAP_CANCEL_SALE)

        reason = (reason or "").strip()
        if not reason:
            raise ValidationError("A reason is required to cancel a sale.")

        sale = self.sales.get_by_receipt_no((receipt_no or "").strip())
        if sale is None:
            raise NotFoundError(f"No sale found for receipt '{receipt_no}'.")
        if sale.status == SALE_CANCELLED:
            raise ValidationError(f"Sale '{sale.receipt_no}' is already cancelled.")

        if any(
            ex.status == EXCHANGE_COMPLETED for ex in self.exchanges.list_for_sale(sale.id)
        ):
            raise ValidationError(
                f"Sale '{sale.receipt_no}' has a completed exchange and cannot be "
                "cancelled; the exchange keeps the original sale intact."
            )

        cancelled_at = cancel_date or datetime.now()
        sale.status = SALE_CANCELLED
        sale.cancelled_at = cancelled_at
        sale.cancelled_by_user_id = user_record_id(user)
        sale.cancel_reason = reason
        self.session.flush()

        sync = self._sync()
        sync.enqueue_update("sale", sale.id, {
            "sync_uuid": sale.sync_uuid,
            "status": sale.status,
            "cancelled_at": str(sale.cancelled_at),
            "cancelled_by_user_id": sale.cancelled_by_user_id,
            "cancel_reason": sale.cancel_reason,
        })

        for item in sale.items:
            self.inventory.change_stock(
                user,
                item.product_id,
                item.quantity,
                SALE_CANCEL_REASON,
                reference_type=REFERENCE_SALE_CANCELLED,
                reference_id=sale.id,
                capability=CAP_CANCEL_SALE,
            )

        for payment in sale.payments:
            if payment.payment_method != PAYMENT_CREDIT:
                continue
            credit = CustomerCredit(
                customer_id=sale.customer_id,
                amount=payment.amount,
                source=CREDIT_SOURCE_EXCHANGE,
                sale_id=sale.id,
                created_by=user_record_id(user),
            )
            self.session.add(credit)
            self.session.flush()
            sync.enqueue_create("customer_credit", credit.id, {
                "sync_uuid": credit.sync_uuid,
                "customer_id": credit.customer_id,
                "amount": str(credit.amount),
                "source": credit.source,
                "sale_id": credit.sale_id,
                "created_by": credit.created_by,
            })

        AuditService(self.session).record(
            user_id=user_record_id(user),
            username=getattr(user, "username", None),
            action=ACTION_SALE_CANCELLED,
            details={
                "receipt_no": sale.receipt_no,
                "sale_id": sale.id,
                "reason": reason,
                "total": str(sale.total),
            },
        )
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
                "Only Bank POS, Bank Transfer and store credit are accepted."
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
