"""Exchange service (Phase 06).

The approved exchange workflow (UC-10, Engineering Artifact 02):

    find original receipt -> verify within 2 days -> select returned item
    -> select replacement -> calculate difference -> Admin confirms
    -> return old item to stock -> deduct replacement
    -> record difference + non-cash payment method if needed -> record exchange

One ``complete_exchange`` call is a single atomic transaction: the caller owns
the ``session_scope``. Any failure (late exchange, unknown product, insufficient
replacement stock, ...) rolls the whole exchange back. The original sale is never
modified or deleted — the exchange references ``original_sale_id`` and item lines
snapshot the historical unit prices and the replacement's current selling price.

Confirmed rules enforced here (source-of-truth artifacts):

- Admin is the only user allowed to process exchanges (``CAP_EXCHANGE``).
- The exchange window is 2 days from the original sale.
- The returned item must have been sold on the original receipt, and the
  returned quantity cannot exceed what was sold (already-exchanged quantities
  count against the sale, so the same item cannot be returned twice).
- Returned items go back into stock; replacements are deducted. Both go through
  the shared ``InventoryService.change_stock`` writer with a ``EXCHANGE``
  reference, so no negative stock and a full movement audit trail.
- Only Bank POS and Bank Transfer payments exist (the wireframe shows the
  customer paying the difference with POS/Transfer). A zero difference needs no
  payment. When the customer would be owed money the settlement is NOT
  confirmed (no-cash rule) — the exchange is refused and the branch is recorded
  in ``OPEN_DECISIONS.md`` rather than invented here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.data.models import (
    DIFFERENCE_CUSTOMER_PAYS,
    DIFFERENCE_NONE,
    EXCHANGE_COMPLETED,
    VALID_PAYMENT_METHODS,
    Exchange,
    ExchangeItem,
    Product,
    Sale,
)
from app.data.repositories.exchange_repository import ExchangeRepository
from app.data.repositories.product_repository import ProductRepository
from app.data.repositories.sale_repository import SaleRepository
from app.domain.errors import NotFoundError, ValidationError
from app.domain.permissions import CAP_EXCHANGE, require_permission
from app.domain.rules.validation import parse_quantity
from app.domain.services.inventory_service import REFERENCE_EXCHANGE, InventoryService
from app.domain.services.sale_service import money2
from app.domain.services.sync_service import SyncService
from app.domain.session import user_record_id

EXCHANGE_WINDOW_DAYS = 2
EXCHANGE_RETURN_REASON = "Exchange return"
EXCHANGE_REPLACEMENT_REASON = "Exchange replacement"


@dataclass(frozen=True)
class ExchangeLine:
    """One validated exchange line: a returned product and its replacement."""

    original: Product
    original_quantity: int
    original_price: Decimal
    replacement: Product
    replacement_quantity: int
    replacement_price: Decimal


class ExchangeService:
    """Use-case service for the two-day Admin exchange workflow."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.sales = SaleRepository(session)
        self.products = ProductRepository(session)
        self.exchanges = ExchangeRepository(session)
        self.inventory = InventoryService(session)

    def _sync(self) -> SyncService:
        return SyncService(self.session)

    # --- queries ---------------------------------------------------------- #

    def find_sale(self, user, receipt_no: str) -> Sale:
        """Fetch the original sale for the exchange screen (Admin only)."""
        require_permission(user, CAP_EXCHANGE)
        sale = self.sales.get_by_receipt_no((receipt_no or "").strip())
        if sale is None:
            raise NotFoundError(f"No sale found for receipt '{receipt_no}'.")
        return sale

    # --- exchange completion ---------------------------------------------- #

    def complete_exchange(
        self,
        user,
        *,
        receipt_no: str,
        items: list[dict],
        payment_method: str | None = None,
        exchange_date: datetime | None = None,
    ) -> Exchange:
        """Complete one atomic exchange and return its header.

        ``items`` is a list of lines:
        ``{"original_product_id": int, "original_quantity": int,
        "replacement_product_id": int, "replacement_quantity": int}``.
        """
        require_permission(user, CAP_EXCHANGE)
        sale = self.find_sale(user, receipt_no)

        exchange_date = exchange_date or datetime.now()
        self._validate_window(sale, exchange_date)

        if not items:
            raise ValidationError("An exchange must contain at least one item.")

        lines = self._validate_lines(sale, items)
        difference = self._difference(lines)
        difference_type = self._difference_type(difference)
        payment_method = self._payment(difference_type, payment_method)

        exchange = Exchange(
            original_sale_id=sale.id,
            customer_id=sale.customer_id,
            approved_by=user_record_id(user),
            exchange_date=exchange_date,
            difference_amount=difference,
            difference_type=difference_type,
            payment_method=payment_method,
            status=EXCHANGE_COMPLETED,
        )
        self.exchanges.add(exchange)
        self.session.flush()

        for entry in lines:
            self.session.add(
                ExchangeItem(
                    exchange_id=exchange.id,
                    original_product_id=entry.original.id,
                    replacement_product_id=entry.replacement.id,
                    original_quantity=entry.original_quantity,
                    replacement_quantity=entry.replacement_quantity,
                    original_price=entry.original_price,
                    replacement_price=entry.replacement_price,
                )
            )

        self.session.flush()

        sync = self._sync()
        sync.enqueue_create("exchange", exchange.id, {
            "sync_uuid": exchange.sync_uuid,
            "original_sale_id": exchange.original_sale_id,
            "customer_id": exchange.customer_id,
            "approved_by": exchange.approved_by,
            "exchange_date": str(exchange.exchange_date),
            "difference_amount": str(exchange.difference_amount),
            "difference_type": exchange.difference_type,
            "payment_method": exchange.payment_method,
            "status": exchange.status,
        })
        for ei in exchange.items:
            sync.enqueue_create("exchange_item", ei.id, {
                "sync_uuid": ei.sync_uuid,
                "exchange_id": ei.exchange_id,
                "original_product_id": ei.original_product_id,
                "replacement_product_id": ei.replacement_product_id,
                "original_quantity": ei.original_quantity,
                "replacement_quantity": ei.replacement_quantity,
                "original_price": str(ei.original_price),
                "replacement_price": str(ei.replacement_price),
            })

        for entry in lines:
            self.inventory.change_stock(
                user,
                entry.original.id,
                entry.original_quantity,
                EXCHANGE_RETURN_REASON,
                reference_type=REFERENCE_EXCHANGE,
                reference_id=exchange.id,
                capability=CAP_EXCHANGE,
            )
            try:
                self.inventory.change_stock(
                    user,
                    entry.replacement.id,
                    -entry.replacement_quantity,
                    EXCHANGE_REPLACEMENT_REASON,
                    reference_type=REFERENCE_EXCHANGE,
                    reference_id=exchange.id,
                    capability=CAP_EXCHANGE,
                )
            except ValidationError:
                raise ValidationError(
                    f"Insufficient stock for replacement '{entry.replacement.name}': "
                    f"requested {entry.replacement_quantity}, "
                    f"available {entry.replacement.quantity}."
                ) from None

        return exchange

    # --- validation ------------------------------------------------------- #

    @staticmethod
    def _validate_window(sale: Sale, exchange_date: datetime) -> None:
        if exchange_date < sale.sale_date:
            raise ValidationError("The exchange cannot be dated before the original sale.")
        if (exchange_date - sale.sale_date) > timedelta(days=EXCHANGE_WINDOW_DAYS):
            raise ValidationError(
                "The exchange window has expired. Exchanges are allowed within "
                f"{EXCHANGE_WINDOW_DAYS} days of the original sale."
            )

    def _validate_lines(self, sale: Sale, items: list[dict]) -> list[ExchangeLine]:
        sold: dict[int, int] = {}
        sold_price: dict[int, Decimal] = {}
        for sale_item in sale.items:
            sold[sale_item.product_id] = sold.get(sale_item.product_id, 0) + sale_item.quantity
            sold_price[sale_item.product_id] = sale_item.unit_price

        already = self.exchanges.exchanged_quantities_for_sale(sale.id)

        lines: list[ExchangeLine] = []
        seen_original: set[int] = set()
        seen_replacement: set[int] = set()
        for entry in items:
            try:
                original_product_id = int(entry["original_product_id"])
                replacement_product_id = int(entry["replacement_product_id"])
            except (KeyError, TypeError, ValueError):
                raise ValidationError(
                    "Every exchange line needs an original and a replacement product."
                ) from None

            original_quantity = parse_quantity(
                entry.get("original_quantity"), "original quantity", minimum=1
            )
            replacement_quantity = parse_quantity(
                entry.get("replacement_quantity"), "replacement quantity", minimum=1
            )

            original = self.products.get(original_product_id)
            if original is None:
                raise NotFoundError("Original product not found.")
            replacement = self.products.get(replacement_product_id)
            if replacement is None:
                raise NotFoundError("Replacement product not found.")
            if not replacement.is_active:
                raise ValidationError(
                    f"'{replacement.name}' is not active and cannot be issued as a replacement."
                )

            if original_product_id in seen_original:
                raise ValidationError(
                    f"'{original.name}' appears more than once as a returned item."
                )
            if replacement_product_id in seen_replacement:
                raise ValidationError(
                    f"'{replacement.name}' appears more than once as a replacement."
                )
            seen_original.add(original_product_id)
            seen_replacement.add(replacement_product_id)

            sold_quantity = sold.get(original_product_id, 0)
            available = sold_quantity - already.get(original_product_id, 0)
            if available <= 0:
                raise ValidationError(
                    f"'{original.name}' was not sold on this receipt or has already "
                    "been exchanged."
                )
            if original_quantity > available:
                raise ValidationError(
                    f"Only {available} of '{original.name}' can be exchanged "
                    "from this receipt."
                )

            lines.append(
                ExchangeLine(
                    original=original,
                    original_quantity=original_quantity,
                    original_price=money2(sold_price.get(original_product_id, original.selling_price)),
                    replacement=replacement,
                    replacement_quantity=replacement_quantity,
                    replacement_price=money2(replacement.selling_price),
                )
            )
        return lines

    # --- price difference -------------------------------------------------- #

    @staticmethod
    def _difference(lines: list[ExchangeLine]) -> Decimal:
        returned = sum(
            (entry.original_price * entry.original_quantity for entry in lines), Decimal("0")
        )
        replacement = sum(
            (entry.replacement_price * entry.replacement_quantity for entry in lines),
            Decimal("0"),
        )
        return money2(replacement - returned)

    @staticmethod
    def _difference_type(difference: Decimal) -> str:
        if difference == 0:
            return DIFFERENCE_NONE
        if difference > 0:
            return DIFFERENCE_CUSTOMER_PAYS
        raise ValidationError(
            "This exchange would give money back to the customer. The settlement "
            "for that case is not yet confirmed, so the exchange cannot be "
            "completed (see OPEN_DECISIONS.md)."
        )

    @staticmethod
    def _payment(difference_type: str, payment_method: str | None) -> str | None:
        if difference_type == DIFFERENCE_NONE:
            return None
        value = (payment_method or "").strip().upper()
        if value not in VALID_PAYMENT_METHODS:
            raise ValidationError(
                f"Payment method '{payment_method}' is not supported. "
                "Only Bank POS and Bank Transfer are accepted."
            )
        return value
