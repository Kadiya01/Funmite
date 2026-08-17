"""Permission catalog and authorization checks.

The capability list mirrors the permission matrix in Engineering Artifact 02
(``02_Use_Cases_Workflows``). A capability is a string; every role maps to the
set of capabilities it may exercise. Authorization is enforced here, in the
service layer — never merely by hiding a UI button.

Mapping notes:
- ``Cashier`` may log in, make sales, process POS/Transfer payments, scan
  barcodes and see their own daily sales history.
- Everything else is Admin-only, including the full reports capability
  (the matrix grants Cashier only ``view_own_sales`` for reporting).
- ``manage_customers`` is not in the matrix; creating/editing customer records
  defaults to Admin-only pending confirmation (see ``OPEN_DECISIONS.md``).
"""

from __future__ import annotations

from app.data.models import ROLE_ADMIN, ROLE_CASHIER, User
from app.domain.errors import AuthorizationError

# --- Capabilities --------------------------------------------------------- #

CAP_LOGIN = "login"
CAP_MAKE_SALE = "make_sale"
CAP_PROCESS_PAYMENT = "process_payment"
CAP_SCAN_BARCODE = "scan_barcode"
CAP_VIEW_OWN_SALES = "view_own_sales"

CAP_CREATE_PRODUCT = "create_product"
CAP_EDIT_PRODUCT = "edit_product"
CAP_CHANGE_PRICE = "change_price"
CAP_DISCOUNT = "discount"
CAP_CANCEL_SALE = "cancel_sale"
CAP_EXCHANGE = "exchange"
CAP_STOCK_IN = "stock_in"
CAP_STOCK_ADJUSTMENT = "stock_adjustment"
CAP_VIEW_PROFIT = "view_profit"
CAP_VIEW_REPORTS = "view_reports"
CAP_MANAGE_USERS = "manage_users"
CAP_MANAGE_CUSTOMERS = "manage_customers"
CAP_BACKUP = "backup"
CAP_RESTORE = "restore"
CAP_MANAGE_EXPENSES = "manage_expenses"
CAP_MANAGE_PURCHASES_SUPPLIERS = "manage_purchases_suppliers"

# --- Role → capabilities -------------------------------------------------- #

_SHARED = {
    CAP_LOGIN,
    CAP_MAKE_SALE,
    CAP_PROCESS_PAYMENT,
    CAP_SCAN_BARCODE,
    CAP_VIEW_OWN_SALES,
}

_ADMIN_ONLY = {
    CAP_CREATE_PRODUCT,
    CAP_EDIT_PRODUCT,
    CAP_CHANGE_PRICE,
    CAP_DISCOUNT,
    CAP_CANCEL_SALE,
    CAP_EXCHANGE,
    CAP_STOCK_IN,
    CAP_STOCK_ADJUSTMENT,
    CAP_VIEW_PROFIT,
    CAP_VIEW_REPORTS,
    CAP_MANAGE_USERS,
    CAP_MANAGE_CUSTOMERS,
    CAP_BACKUP,
    CAP_RESTORE,
    CAP_MANAGE_EXPENSES,
    CAP_MANAGE_PURCHASES_SUPPLIERS,
}

PERMISSIONS = {
    ROLE_ADMIN: _SHARED | _ADMIN_ONLY,
    ROLE_CASHIER: set(_SHARED),
}


def permissions_for_role(role: str) -> frozenset[str]:
    """Return the capabilities a role may exercise (empty for unknown roles)."""
    return frozenset(PERMISSIONS.get(role, ()))


def has_permission(user: User | None, capability: str) -> bool:
    """Whether ``user`` may exercise ``capability``.

    Unknown capabilities are denied, and an unknown/inactive role is denied.
    """
    if user is None or not user.is_active:
        return False
    return capability in permissions_for_role(user.role)


def require_permission(user: User | None, capability: str) -> None:
    """Raise ``AuthorizationError`` unless ``user`` may exercise ``capability``."""
    if not has_permission(user, capability):
        role = user.role if user is not None else "none"
        raise AuthorizationError(
            f"'{role}' role does not have permission for '{capability}'."
        )
