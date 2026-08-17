"""Application services.

Phase 02 adds authentication and audit logging; Phase 03 adds the product
catalogue, customer and bulk-import services plus their permissions.
Phase 10 adds device identity and sync services.
"""

from app.domain.services.audit_service import (  # noqa: F401
    ACTION_LOGIN_FAILED,
    ACTION_LOGIN_SUCCESS,
    ACTION_LOGOUT,
    ACTION_PASSWORD_CHANGE,
    ACTION_PASSWORD_CHANGE_FAILED,
    AuditService,
)
from app.domain.services.auth_service import (  # noqa: F401
    AuthService,
    GENERIC_LOGIN_ERROR,
)
from app.domain.services.category_service import CategoryService  # noqa: F401
from app.domain.services.customer_service import (  # noqa: F401
    CUSTOMER_CODE_PREFIX,
    CustomerService,
)
from app.domain.services.device_service import DeviceIdentity  # noqa: F401
from app.domain.services.exchange_service import (  # noqa: F401
    EXCHANGE_REPLACEMENT_REASON,
    EXCHANGE_RETURN_REASON,
    EXCHANGE_WINDOW_DAYS,
    ExchangeService,
)
from app.domain.services.expense_service import ExpenseService  # noqa: F401
from app.domain.services.inventory_service import (  # noqa: F401
    DEFAULT_STOCK_IN_REASON,
    REFERENCE_EXCHANGE,
    REFERENCE_STOCK_ADJUSTMENT,
    REFERENCE_STOCK_IN,
    InventoryService,
)
from app.domain.services.purchase_service import (  # noqa: F401
    PurchaseLine,
    PurchaseService,
)
from app.domain.services.receipt_service import ReceiptService  # noqa: F401
from app.domain.services.sale_service import (  # noqa: F401
    RECEIPT_PREFIX,
    SALE_ITEM_REASON,
    SaleService,
)
from app.domain.services.product_import import (  # noqa: F401
    DEFAULT_TEMPLATE_HEADER,
    ImportResult,
    ProductImportService,
    RowError,
)
from app.domain.services.product_service import (  # noqa: F401
    PRODUCT_CODE_PREFIX,
    ProductService,
)
from app.domain.services.supplier_service import SupplierService  # noqa: F401
from app.domain.services.reporting_service import ReportingService  # noqa: F401
from app.domain.services.backup_service import (  # noqa: F401
    BackupInfo,
    BackupResult,
    BackupService,
    RestoreResult,
)
from app.domain.services.sync_service import (  # noqa: F401
    ENTITY_CATEGORY,
    ENTITY_CUSTOMER,
    ENTITY_EXCHANGE,
    ENTITY_EXCHANGE_ITEM,
    ENTITY_EXPENSE,
    ENTITY_INVENTORY_LOG,
    ENTITY_PAYMENT,
    ENTITY_PRODUCT,
    ENTITY_PURCHASE,
    ENTITY_PURCHASE_ITEM,
    ENTITY_SALE,
    ENTITY_SALE_ITEM,
    ENTITY_SUPPLIER,
    OP_CREATE,
    OP_DELETE,
    OP_UPDATE,
    SyncService,
)
