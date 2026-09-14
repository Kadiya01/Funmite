"""Store credit service.

Confirmed rules (decision batch):

- The shop owes the customer when an exchange replacement is cheaper (the
  no-cash rule forbids a cash refund) and when a credit-paid sale is cancelled.
  Both are recorded as ledger rows with source ``EXCHANGE``.
- The customer spends the balance on a future sale: ``consume`` writes a
  ``SALE_PAYMENT`` ledger row (subtracts from the balance) and refuses to let
  a sale be settled with credit the customer does not have.
- A credit-paid sale cannot be partially settled: a sale is settled by one
  payment method, so ``consume`` covers the full sale total or fails.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.data.models import CREDIT_SOURCE_SALE_PAYMENT, CustomerCredit
from app.data.repositories.customer_credit_repository import CustomerCreditRepository
from app.domain.errors import ValidationError
from app.domain.services.sync_service import SyncService
from app.domain.session import user_record_id


class StoreCreditService:
    """Use-case service for reading and spending customer store credit."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.credits = CustomerCreditRepository(session)

    def _sync(self) -> SyncService:
        return SyncService(self.session)

    def balance(self, customer_id: int) -> Decimal:
        """Current store-credit balance for ``customer_id``."""
        return self.credits.balance_for(customer_id)

    def consume(
        self, user, *, customer_id: int, amount, sale_id: int
    ) -> CustomerCredit:
        """Spend ``amount`` of store credit on a completed sale.

        Refuses when the customer's balance is less than the requested amount
        (a sale can only be settled by credit the customer actually has), then
        records a positive ``SALE_PAYMENT`` ledger row and syncs it.
        """
        value = Decimal(str(amount))
        available = self.balance(customer_id)
        if available < value:
            raise ValidationError(
                f"Insufficient store credit: balance is ₦{available:,.2f}, "
                f"sale total is ₦{value:,.2f}."
            )
        credit = CustomerCredit(
            customer_id=customer_id,
            amount=value,
            source=CREDIT_SOURCE_SALE_PAYMENT,
            sale_id=sale_id,
            created_by=user_record_id(user),
        )
        self.session.add(credit)
        self.session.flush()
        self._sync().enqueue_create("customer_credit", credit.id, {
            "sync_uuid": credit.sync_uuid,
            "customer_id": credit.customer_id,
            "amount": str(credit.amount),
            "source": credit.source,
            "sale_id": credit.sale_id,
            "created_by": credit.created_by,
        })
        return credit