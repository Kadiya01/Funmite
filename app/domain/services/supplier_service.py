"""Supplier service (Phase 07).

Admin-only supplier CRUD. Suppliers are referenced by purchases; they do not
have their own payment terms or credit semantics until that is confirmed
(see ``OPEN_DECISIONS.md``).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.data.models import Supplier
from app.data.repositories.supplier_repository import SupplierRepository
from app.domain.errors import NotFoundError, ValidationError
from app.domain.permissions import CAP_MANAGE_PURCHASES_SUPPLIERS, require_permission
from app.domain.services.sync_service import SyncService


class SupplierService:
    """Use-case service for supplier management."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = SupplierRepository(session)

    def _sync(self) -> SyncService:
        return SyncService(self.session)

    def list_suppliers(self, user, *, search: str | None = None) -> list[Supplier]:
        """List suppliers, optionally filtered by name/phone. Admin-only."""
        require_permission(user, CAP_MANAGE_PURCHASES_SUPPLIERS)
        return self.repo.list_suppliers(search=search)

    def get_supplier(self, user, supplier_id: int) -> Supplier:
        """Get a supplier by id. Admin-only."""
        require_permission(user, CAP_MANAGE_PURCHASES_SUPPLIERS)
        supplier = self.repo.get(supplier_id)
        if supplier is None:
            raise NotFoundError("Supplier not found.")
        return supplier

    def create_supplier(
        self,
        user,
        *,
        name: str,
        phone: str | None = None,
        address: str | None = None,
    ) -> Supplier:
        """Create a new supplier. Admin-only."""
        require_permission(user, CAP_MANAGE_PURCHASES_SUPPLIERS)
        name = (name or "").strip()
        if not name:
            raise ValidationError("Supplier name is required.")
        supplier = Supplier(
            name=name,
            phone=phone.strip() if phone else None,
            address=address.strip() if address else None,
        )
        self.session.add(supplier)
        self.session.flush()
        self._sync().enqueue_create("supplier", supplier.id, {
            "sync_uuid": supplier.sync_uuid,
            "name": supplier.name,
            "phone": supplier.phone,
            "address": supplier.address,
            "version": supplier.version,
        })
        return supplier

    def update_supplier(
        self,
        user,
        supplier_id: int,
        *,
        name: str | None = None,
        phone: str | None = None,
        address: str | None = None,
    ) -> Supplier:
        """Update an existing supplier. Admin-only."""
        require_permission(user, CAP_MANAGE_PURCHASES_SUPPLIERS)
        supplier = self.repo.get(supplier_id)
        if supplier is None:
            raise NotFoundError("Supplier not found.")
        if name is not None:
            name = name.strip()
            if not name:
                raise ValidationError("Supplier name is required.")
            supplier.name = name
        if phone is not None:
            supplier.phone = phone.strip() if phone else None
        if address is not None:
            supplier.address = address.strip() if address else None
        self.session.flush()
        self._sync().enqueue_update("supplier", supplier.id, {
            "sync_uuid": supplier.sync_uuid,
            "name": supplier.name,
            "phone": supplier.phone,
            "address": supplier.address,
            "version": supplier.version,
        })
        return supplier
