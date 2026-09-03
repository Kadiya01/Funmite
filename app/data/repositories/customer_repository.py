"""Customer repository."""

from __future__ import annotations

from sqlalchemy import select

from app.data.models import Customer
from app.data.repositories.base import BaseRepository


class CustomerRepository(BaseRepository[Customer]):
    """Data access for shop customers."""

    model = Customer

    def get_by_customer_code(self, customer_code: str) -> Customer | None:
        return self.get_by(customer_code=customer_code)

    def list_all(self, *, include_inactive: bool = False) -> list[Customer]:
        statement = select(Customer)
        if not include_inactive:
            statement = statement.where(Customer.is_active.is_(True))
        statement = statement.order_by(Customer.name)
        return list(self.session.scalars(statement))

    def search(self, query: str, *, limit: int = 50, include_inactive: bool = False) -> list[Customer]:
        term = f"%{query.strip()}%"
        statement = (
            select(Customer)
            .where(Customer.name.ilike(term) | Customer.phone.ilike(term))
        )
        if not include_inactive:
            statement = statement.where(Customer.is_active.is_(True))
        statement = statement.order_by(Customer.name).limit(limit)
        return list(self.session.scalars(statement))

    def max_code_number(self, prefix: str) -> int:
        """Largest numeric suffix among codes like ``<prefix>-<digits>``."""
        like = f"{prefix}-%"
        offset = len(prefix) + 1
        rows = self.session.scalars(
            select(Customer.customer_code).where(Customer.customer_code.like(like))
        )
        maximum = 0
        for code in rows:
            suffix = code[offset:]
            if suffix.isdigit():
                maximum = max(maximum, int(suffix))
        return maximum
