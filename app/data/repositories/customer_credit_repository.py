"""Customer credit ledger repository.

Store credit is a ledger (deliberately no absolute-balance column, matching the
inventory delta model so the two-PC convergence stays idempotent). Every row
records a positive movement: source ``EXCHANGE`` adds to the balance, source
``SALE_PAYMENT`` (credit spent on a sale) subtracts it.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from app.data.models import CREDIT_SOURCE_EXCHANGE, CREDIT_SOURCE_SALE_PAYMENT, CustomerCredit
from app.data.repositories.base import BaseRepository


class CustomerCreditRepository(BaseRepository[CustomerCredit]):
    """Data access for customer credit ledger rows."""

    model = CustomerCredit

    def balance_for(self, customer_id: int) -> Decimal:
        """Current store-credit balance: EXCHANGE grants minus SALE_PAYMENT spent."""
        granted = self.session.scalar(
            select(func.coalesce(func.sum(CustomerCredit.amount), 0)).where(
                CustomerCredit.customer_id == customer_id,
                CustomerCredit.source == CREDIT_SOURCE_EXCHANGE,
            )
        )
        spent = self.session.scalar(
            select(func.coalesce(func.sum(CustomerCredit.amount), 0)).where(
                CustomerCredit.customer_id == customer_id,
                CustomerCredit.source == CREDIT_SOURCE_SALE_PAYMENT,
            )
        )
        return Decimal(str(granted)) - Decimal(str(spent))

    def list_for_customer(self, customer_id: int) -> list[CustomerCredit]:
        statement = (
            select(CustomerCredit)
            .where(CustomerCredit.customer_id == customer_id)
            .order_by(CustomerCredit.created_at)
        )
        return list(self.session.scalars(statement))