"""Authorization/permission rules.

See ``catalog.py`` for the capability catalog and the role→capability map.
"""

from app.domain.permissions.catalog import (  # noqa: F401
    CAP_BACKUP,
    CAP_CANCEL_SALE,
    CAP_CHANGE_PRICE,
    CAP_CREATE_PRODUCT,
    CAP_DISCOUNT,
    CAP_EDIT_PRODUCT,
    CAP_EXCHANGE,
    CAP_LOGIN,
    CAP_MAKE_SALE,
    CAP_MANAGE_CUSTOMERS,
    CAP_MANAGE_EXPENSES,
    CAP_MANAGE_PURCHASES_SUPPLIERS,
    CAP_MANAGE_USERS,
    CAP_PROCESS_PAYMENT,
    CAP_RESTORE,
    CAP_SCAN_BARCODE,
    CAP_STOCK_ADJUSTMENT,
    CAP_STOCK_IN,
    CAP_VIEW_OWN_SALES,
    CAP_VIEW_PROFIT,
    CAP_VIEW_REPORTS,
    PERMISSIONS,
    has_permission,
    permissions_for_role,
    require_permission,
)
