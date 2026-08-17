"""Customer service (Phase 03).

Customer-record management defaults to Admin-only (``CAP_MANAGE_CUSTOMERS``)
because the use-case permission matrix does not grant it to the Cashier; the
Cashier still selects an existing customer during a sale. This default is
recorded in ``OPEN_DECISIONS.md`` pending client confirmation.

A customer may be created without a phone number (the approved schema makes
``phone`` nullable and requires no uniqueness on it).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.data.models import Customer
from app.data.repositories.customer_repository import CustomerRepository
from app.domain.errors import NotFoundError, ValidationError
from app.domain.permissions import CAP_MAKE_SALE, CAP_MANAGE_CUSTOMERS, require_permission
from app.domain.services.sync_service import SyncService

CUSTOMER_CODE_PREFIX = "CUS"


class CustomerService:
    """Use-case service for shop customer records."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = CustomerRepository(session)

    def _sync(self) -> SyncService:
        return SyncService(self.session)

    def create(
        self,
        user,
        *,
        name: str,
        phone: str | None = None,
        address: str | None = None,
        customer_code: str | None = None,
    ) -> Customer:
        """Register a customer, generating a unique code when none is supplied."""
        require_permission(user, CAP_MANAGE_CUSTOMERS)
        return self._create(
            name=name,
            phone=phone,
            address=address,
            customer_code=customer_code,
        )

    def create_for_sale(
        self,
        user,
        *,
        name: str,
        phone: str | None = None,
    ) -> Customer:
        """Register a minimal customer while completing a sale.

        A customer record is required for every sale, and the Cashier may need
        to record a new walk-in at the till. Full customer-record management
        stays Admin-only (``CAP_MANAGE_CUSTOMERS``); this narrow path is gated
        by the shared ``CAP_MAKE_SALE`` permission and only registers a name
        (phone optional). See ``OPEN_DECISIONS.md``.
        """
        require_permission(user, CAP_MAKE_SALE)
        return self._create(name=name, phone=phone, address=None, customer_code=None)

    def _create(
        self,
        *,
        name: str,
        phone: str | None = None,
        address: str | None = None,
        customer_code: str | None = None,
    ) -> Customer:
        name = (name or "").strip()
        if not name:
            raise ValidationError("Customer name is required.")

        code = (customer_code or "").strip() or self._next_customer_code()
        if self.repo.get_by_customer_code(code) is not None:
            raise ValidationError(f"Customer code '{code}' already exists.")

        customer = Customer(
            customer_code=code,
            name=name,
            phone=phone.strip() if phone else None,
            address=address.strip() if address else None,
        )
        self.repo.add(customer)
        self.session.flush()
        self._sync().enqueue_create("customer", customer.id, {
            "sync_uuid": customer.sync_uuid,
            "customer_code": customer.customer_code,
            "name": customer.name,
            "phone": customer.phone,
            "address": customer.address,
            "version": customer.version,
        })
        return customer

    def update(
        self,
        user,
        customer_id: int,
        *,
        name: str | None = None,
        phone: str | None = None,
        address: str | None = None,
        customer_code: str | None = None,
    ) -> Customer:
        """Update a customer record (Admin only)."""
        require_permission(user, CAP_MANAGE_CUSTOMERS)
        customer = self.get(customer_id)

        if name is not None:
            cleaned = (name or "").strip()
            if not cleaned:
                raise ValidationError("Customer name is required.")
            customer.name = cleaned
        if phone is not None:
            customer.phone = phone.strip() if phone else None
        if address is not None:
            customer.address = address.strip() if address else None
        if customer_code is not None:
            cleaned = customer_code.strip()
            if not cleaned:
                raise ValidationError("Customer code cannot be empty.")
            clash = self.repo.get_by_customer_code(cleaned)
            if clash is not None and clash.id != customer.id:
                raise ValidationError(f"Customer code '{cleaned}' already exists.")
            customer.customer_code = cleaned
        self.session.flush()
        self._sync().enqueue_update("customer", customer.id, {
            "sync_uuid": customer.sync_uuid,
            "customer_code": customer.customer_code,
            "name": customer.name,
            "phone": customer.phone,
            "address": customer.address,
            "version": customer.version,
        })
        return customer

    def get(self, customer_id: int) -> Customer:
        customer = self.repo.get(customer_id)
        if customer is None:
            raise NotFoundError("Customer not found.")
        return customer

    def get_by_code(self, customer_code: str) -> Customer | None:
        return self.repo.get_by_customer_code(customer_code)

    def search(self, query: str, *, limit: int = 50) -> list[Customer]:
        return self.repo.search(query, limit=limit)

    def list(self) -> list[Customer]:
        return self.repo.list_all()

    def _next_customer_code(self) -> str:
        current = self.repo.max_code_number(CUSTOMER_CODE_PREFIX)
        return f"{CUSTOMER_CODE_PREFIX}-{current + 1:05d}"
