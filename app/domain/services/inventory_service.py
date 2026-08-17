"""Inventory service (Phase 04).

Stock is only ever changed through this service, so every movement is
auditable and the confirmed low-stock rule (quantity <= 3) is applied in one
place. Sales (Phase 05) and exchanges (Phase 06) consume the same
``change_stock`` movement writer instead of touching ``Product.quantity``
directly.

Confirmed rules enforced here:

- Stock-in adds a positive quantity and is Admin-only (``CAP_STOCK_IN``).
- Stock adjustment corrects the quantity to an absolute value, requires a
  reason and is Admin-only (``CAP_STOCK_ADJUSTMENT``).
- A movement must never take a product below zero (negative stock is not
  approved); the database CHECK constraint is the final guard.
- Every movement writes an ``InventoryLog`` with product, previous quantity,
  change, new quantity, reason, user and timestamp, plus a reference type/id
  where a related record exists.

Reference types tag the movement kind; ``reference_id`` links to a related
transaction (e.g. the sale for a Phase 05 stock-out) when one exists.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.data.models import InventoryLog, Product
from app.data.repositories.inventory_repository import InventoryLogRepository
from app.data.repositories.product_repository import ProductRepository
from app.domain.errors import NotFoundError, ValidationError
from app.domain.permissions import (
    CAP_STOCK_ADJUSTMENT,
    CAP_STOCK_IN,
    require_permission,
)
from app.domain.rules.validation import parse_quantity, parse_signed_quantity
from app.domain.services.sync_service import SyncService
from app.domain.session import user_record_id

REFERENCE_STOCK_IN = "STOCK_IN"
REFERENCE_STOCK_ADJUSTMENT = "STOCK_ADJUSTMENT"
REFERENCE_SALE = "SALE"
REFERENCE_EXCHANGE = "EXCHANGE"

DEFAULT_STOCK_IN_REASON = "Stock received"


class InventoryService:
    """Use-case service for stock movements and inventory visibility."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.products = ProductRepository(session)
        self.logs = InventoryLogRepository(session)

    def _sync(self) -> SyncService:
        return SyncService(self.session)

    # --- queries ---------------------------------------------------------- #

    def get(self, product_id: int) -> Product:
        product = self.products.get(product_id)
        if product is None:
            raise NotFoundError("Product not found.")
        return product

    def list_low_stock(self, user, *, threshold: int = 3) -> list[Product]:
        """Confirmed rule: quantity <= 3. Admin-only (inventory management)."""
        require_permission(user, CAP_STOCK_ADJUSTMENT)
        return self.products.list_low_stock(threshold=threshold)

    def list_movements(
        self,
        user,
        *,
        product_id: int | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[InventoryLog]:
        """Movement history, newest first. Admin-only (inventory management)."""
        require_permission(user, CAP_STOCK_ADJUSTMENT)
        return self.logs.list_recent(
            product_id=product_id,
            start=start,
            end=end,
            limit=limit,
        )

    # --- stock movements (Admin) ----------------------------------------- #

    def stock_in(
        self,
        user,
        product_id: int,
        quantity,
        reason: str | None = None,
    ) -> InventoryLog:
        """Receive stock: increase ``product_id`` by ``quantity``.

        The quantity must be a positive whole number. The movement is logged
        with a ``STOCK_IN`` reference (no related transaction record yet —
        purchases arrive in Phase 07).
        """
        require_permission(user, CAP_STOCK_IN)
        added = parse_quantity(quantity, "stock-in quantity", minimum=1)
        return self.change_stock(
            user,
            product_id,
            added,
            reason or DEFAULT_STOCK_IN_REASON,
            reference_type=REFERENCE_STOCK_IN,
            capability=CAP_STOCK_IN,
        )

    def adjust(
        self,
        user,
        product_id: int,
        new_quantity,
        reason: str,
    ) -> InventoryLog:
        """Correct the physical/system mismatch: set quantity to an absolute value.

        ``reason`` is mandatory (confirmed business rule). The resulting
        quantity must be zero or positive.
        """
        require_permission(user, CAP_STOCK_ADJUSTMENT)
        new = parse_quantity(new_quantity, "new quantity", minimum=0)
        product = self.get(product_id)
        change = new - product.quantity
        return self.change_stock(
            user,
            product_id,
            change,
            reason,
            reference_type=REFERENCE_STOCK_ADJUSTMENT,
            capability=CAP_STOCK_ADJUSTMENT,
        )

    # --- shared movement writer (also used by sales/exchanges) ------------ #

    def change_stock(
        self,
        user,
        product_id: int,
        change_quantity,
        reason: str,
        *,
        reference_type: str | None = None,
        reference_id: int | None = None,
        capability=CAP_STOCK_ADJUSTMENT,
    ) -> InventoryLog:
        """Apply a signed quantity change and record the movement.

        Authorization is checked against ``capability`` so future sale and
        exchange services can reuse the same writer with their own permission
        (``CAP_MAKE_SALE`` / ``CAP_EXCHANGE``) instead of duplicating stock
        logic. The change is refused if it would push stock below zero.
        """
        require_permission(user, capability)
        change = parse_signed_quantity(change_quantity, "stock change")
        product = self.get(product_id)
        reason = (reason or "").strip()
        if not reason:
            raise ValidationError("A reason is required for every stock change.")

        previous = product.quantity
        new = previous + change
        if new < 0:
            raise ValidationError(
                f"Stock for '{product.name}' cannot go below zero "
                f"(current {previous}, change {change})."
            )

        product.quantity = new
        log = InventoryLog(
            product_id=product.id,
            change_quantity=change,
            previous_quantity=previous,
            new_quantity=new,
            reason=reason,
            reference_type=reference_type,
            reference_id=reference_id,
            user_id=user_record_id(user),
        )
        self.session.add(log)
        self.session.flush()
        self._sync().enqueue_create("inventory_log", log.id, {
            "sync_uuid": log.sync_uuid,
            "product_id": log.product_id,
            "change_quantity": log.change_quantity,
            "previous_quantity": log.previous_quantity,
            "new_quantity": log.new_quantity,
            "reason": log.reason,
            "reference_type": log.reference_type,
            "reference_id": log.reference_id,
            "user_id": log.user_id,
        })
        return log
