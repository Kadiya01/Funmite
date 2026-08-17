"""Receipt service (Phase 05).

A dedicated printer/receipt service keeps POS business logic free of printer
code (technical architecture, section 8): ``SaleService`` only returns the
completed sale; printing happens through this service after the transaction
commits. A sale is never deleted because printing failed.

Reprinting a past receipt is UC-06 and is Admin-only; it is gated by
``CAP_VIEW_REPORTS`` because the permission matrix has no dedicated "reprint"
capability and reprint reads a historical sale record.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.data.models import Sale
from app.data.repositories.sale_repository import SaleRepository
from app.domain.errors import NotFoundError
from app.domain.permissions import CAP_VIEW_REPORTS, require_permission
from app.printing.printer import ReceiptPrinter
from app.printing.receipt import ReceiptBuilder, ReceiptData


class ReceiptService:
    """Builds, prints and reprints receipts for completed sales."""

    def __init__(self, session: Session, *, builder: ReceiptBuilder | None = None) -> None:
        self.session = session
        self.sales = SaleRepository(session)
        self.builder = builder or ReceiptBuilder()

    def get_by_receipt_no(self, receipt_no: str) -> Sale | None:
        return self.sales.get_by_receipt_no(receipt_no)

    def build_receipt(self, sale: Sale) -> ReceiptData:
        """Detached receipt data for a sale (safe to use after the session closes)."""
        return self.builder.from_sale(sale)

    def print_receipt(self, receipt: ReceiptData, printer: ReceiptPrinter) -> None:
        printer.print_receipt(receipt)

    def reprint(self, user, receipt_no: str, printer: ReceiptPrinter) -> ReceiptData:
        """Admin-only reprint of a completed sale (UC-06)."""
        require_permission(user, CAP_VIEW_REPORTS)
        sale = self.get_by_receipt_no(receipt_no)
        if sale is None:
            raise NotFoundError(f"No sale found with receipt '{receipt_no}'.")
        receipt = self.build_receipt(sale)
        self.print_receipt(receipt, printer)
        return receipt
