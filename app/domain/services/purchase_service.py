"""Purchase service (Phase 07).

The approved purchase workflow (UC-11, Engineering Artifact 02):

    select supplier -> add purchase items -> set amount paid
    -> complete purchase -> atomic transaction:
       create purchase header -> create purchase_items
       -> increase stock per item -> update product cost prices
       -> write inventory logs -> commit

One ``complete_purchase`` call is a single atomic transaction: the caller owns
the ``session_scope``. Any failure (unknown supplier, unknown product, invalid
quantity, ...) rolls the whole purchase back.

Confirmed rules enforced here (source-of-truth artifacts):

- Admin is the only user allowed to manage purchases (``CAP_MANAGE_PURCHASES_SUPPLIERS``).
- Every purchase must have a supplier.
- Every purchase must have at least one item.
- Purchase items must reference existing, active products.
- Quantities must be positive whole numbers.
- Unit costs must be non-negative.
- The stock increase goes through the shared ``InventoryService.change_stock``
  writer with a ``PURCHASE`` reference, so every movement is auditable.
- Product ``cost_price`` is updated to the latest purchase unit cost so that
  future profit calculations reflect the latest cost. Historical sale-item costs
  are preserved in ``sale_items.cost_price`` and are never overwritten.
- ``purchases.balance`` = ``total_cost - amount_paid``. The balance semantics
  (whether it represents a true payable or just a record) are an open decision
  (see ``OPEN_DECISIONS.md``); until confirmed, no payment tracking or aging
  is implemented.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.data.models import (
    Purchase,
    PurchaseItem,
)
from app.data.repositories.product_repository import ProductRepository
from app.data.repositories.purchase_repository import PurchaseRepository
from app.data.repositories.supplier_repository import SupplierRepository
from app.domain.errors import NotFoundError, ValidationError
from app.domain.permissions import CAP_MANAGE_PURCHASES_SUPPLIERS, require_permission
from app.domain.rules.validation import parse_decimal, parse_quantity
from app.domain.services.inventory_service import REFERENCE_STOCK_IN, InventoryService
from app.domain.services.sync_service import SyncService
from app.domain.session import user_record_id


@dataclass
class PurchaseLine:
    """One line in a purchase order."""

    product_id: int
    quantity: int
    unit_cost: Decimal


class PurchaseService:
    """Use-case service for recording supplier purchases."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.purchases = PurchaseRepository(session)
        self.suppliers = SupplierRepository(session)
        self.products = ProductRepository(session)

    def _sync(self) -> SyncService:
        return SyncService(self.session)

    def list_purchases(
        self,
        user,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        supplier_id: int | None = None,
    ) -> list[Purchase]:
        """List purchases, newest first. Admin-only."""
        require_permission(user, CAP_MANAGE_PURCHASES_SUPPLIERS)
        return self.purchases.list_purchases(
            start=start, end=end, supplier_id=supplier_id,
        )

    def get_purchase(self, user, purchase_id: int) -> Purchase:
        """Get a purchase with items and supplier. Admin-only."""
        require_permission(user, CAP_MANAGE_PURCHASES_SUPPLIERS)
        purchase = self.purchases.get_with_details(purchase_id)
        if purchase is None:
            raise NotFoundError("Purchase not found.")
        return purchase

    def complete_purchase(
        self,
        user,
        *,
        supplier_id: int,
        items: list[PurchaseLine],
        amount_paid: Decimal | str | int,
        purchase_date: datetime | None = None,
    ) -> Purchase:
        """Record a supplier purchase and increase stock atomically.

        In one ``session_scope`` transaction:
        1. Validate supplier exists.
        2. Validate each item (product exists and is active, quantity > 0, unit_cost >= 0).
        3. Create the purchase header (total_cost, amount_paid, balance).
        4. Create purchase_items rows (historical unit_cost).
        5. For each item: increase stock via ``InventoryService.change_stock``
           (``CAP_MANAGE_PURCHASES_SUPPLIERS``, ``reference_type=STOCK_IN``,
           ``reference_id=purchase.id``).
        6. Update each product's ``cost_price`` to the purchased unit_cost.
        7. Commit.
        Any failure rolls the whole transaction back.
        """
        require_permission(user, CAP_MANAGE_PURCHASES_SUPPLIERS)

        if not items:
            raise ValidationError("A purchase must have at least one item.")

        supplier = self.suppliers.get(supplier_id)
        if supplier is None:
            raise NotFoundError("Supplier not found.")

        paid = parse_decimal(amount_paid, "amount paid", minimum=Decimal("0"))
        purchase_date = purchase_date or datetime.now()
        inv = InventoryService(self.session)

        total_cost = Decimal("0")
        validated_lines: list[tuple[ProductRepository, PurchaseLine]] = []

        seen_products: set[int] = set()
        for line in items:
            pid = line.product_id
            if pid in seen_products:
                raise ValidationError(
                    f"Duplicate product on purchase line (product id {pid})."
                )
            seen_products.add(pid)

            product = self.products.get(pid)
            if product is None:
                raise NotFoundError(f"Product not found (id {pid}).")
            if not product.is_active:
                raise ValidationError(
                    f"Product '{product.name}' is not active and cannot be purchased."
                )

            qty = parse_quantity(line.quantity, "quantity", minimum=1)
            unit_cost = parse_decimal(line.unit_cost, "unit cost", minimum=Decimal("0"))

            line_total = unit_cost * qty
            total_cost += line_total
            validated_lines.append((product, qty, unit_cost, line_total))

        if paid > total_cost:
            raise ValidationError(
                "Amount paid cannot exceed the total cost."
            )

        balance = total_cost - paid

        purchase = Purchase(
            supplier_id=supplier.id,
            purchase_date=purchase_date,
            total_cost=total_cost,
            amount_paid=paid,
            balance=balance,
            created_by=user_record_id(user),
        )
        self.session.add(purchase)
        self.session.flush()

        for product, qty, unit_cost, line_total in validated_lines:
            self.session.add(
                PurchaseItem(
                    purchase_id=purchase.id,
                    product_id=product.id,
                    quantity=qty,
                    unit_cost=unit_cost,
                    line_total=line_total,
                )
            )

            inv.change_stock(
                user,
                product.id,
                qty,
                "Purchase stock received",
                reference_type=REFERENCE_STOCK_IN,
                reference_id=purchase.id,
                capability=CAP_MANAGE_PURCHASES_SUPPLIERS,
            )

            product.cost_price = unit_cost

        self.session.flush()

        sync = self._sync()
        sync.enqueue_create("purchase", purchase.id, {
            "sync_uuid": purchase.sync_uuid,
            "supplier_id": purchase.supplier_id,
            "purchase_date": str(purchase.purchase_date),
            "total_cost": str(purchase.total_cost),
            "amount_paid": str(purchase.amount_paid),
            "balance": str(purchase.balance),
            "created_by": purchase.created_by,
        })
        for pi in purchase.items:
            sync.enqueue_create("purchase_item", pi.id, {
                "sync_uuid": pi.sync_uuid,
                "purchase_id": pi.purchase_id,
                "product_id": pi.product_id,
                "quantity": pi.quantity,
                "unit_cost": str(pi.unit_cost),
                "line_total": str(pi.line_total),
            })

        return purchase
