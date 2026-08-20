# Project Documentation

Layered architecture per `04_Technical_Architecture`:

```
UI  ->  Application Services  ->  Data Access  ->  SQLite
```

- `app/ui` — screens (login, dashboard, pos, products, customers, inventory,
  exchanges, purchases, suppliers, expenses, reports, settings implemented;
  more later).
- `app/domain` — business rules, permissions, services, session handling.
- `app/data` — SQLAlchemy engine, repositories, migrations (Phases 01, 10).
- `app/barcode` — barcode generation, labels, scanner normalization (Phase 03).
- `app/printing` — receipt data, ESC/POS rendering and the printer abstraction
  (Phase 05).
- `app/sync` — cloud sync layer: outbox pattern, worker, cloud API, device
  registration, conflict resolution, FK resolution (Phase 10).

Business rules are never placed directly in UI event handlers; UI calls
application services and displays results.

## Exchanges (Phase 06)

- `app/domain/services/exchange_service.py` — `ExchangeService.complete_exchange()`
  is the single way an exchange is written. In one `session_scope` transaction it
  validates the original sale (must exist, within the 2-day window, Admin-only via
  `CAP_EXCHANGE`), creates the exchange header (difference amount/type, payment
  method, status) and `exchange_items` rows (historical original price, current
  replacement price), and then returns items to stock and deducts replacements
  through `InventoryService.change_stock` (`CAP_EXCHANGE`,
  `reference_type=REFERENCE_EXCHANGE`). Late exchanges, unknown products, duplicate
  lines, over-returns, insufficient replacement stock, and customer-owed refunds
  all raise and roll back.
- `app/data/repositories/exchange_repository.py` — `list_for_sale` and
  `exchanged_quantities_for_sale` (aggregate original quantities across completed
  exchanges for over-exchange protection).
- `app/ui/exchanges/exchange_page.py` — the wireframe-faithful ExchangePage with
  receipt-number lookup, return item selection from the original sale (with quantity
  spinner), replacement product search/add (with quantity), live difference label,
  Admin-only POS/Transfer payment radios, confirmation popup and complete action.
- `app/ui/exchanges/exchange_dialog.py` — wraps `ExchangePage` in a modal dialog;
  exchange and confirmation popups are injected for testability.
- `app/ui/pos/pos_page.py` — Admin-only "Exchange..." button in the title bar
  opens the `ExchangeDialog`. The button is hidden for the Cashier.

## Purchases, suppliers & expenses (Phase 07)

- `app/domain/services/supplier_service.py` — `SupplierService` provides
  Admin-only (`CAP_MANAGE_PURCHASES_SUPPLIERS`) CRUD for suppliers: list with
  search by name/phone, create, update. Suppliers are referenced by purchases.
- `app/domain/services/purchase_service.py` — `PurchaseService.complete_purchase()`
  is the single way a purchase is written. In one `session_scope` transaction it
  validates the supplier and each product (exists, active, not duplicate), validates
  quantities and unit costs, creates the purchase header (total_cost, amount_paid,
  balance), creates `purchase_items` rows (historical unit_cost), increases stock
  per item through `InventoryService.change_stock` (`CAP_MANAGE_PURCHASES_SUPPLIERS`,
  `reference_type=STOCK_IN`), and updates each product's `cost_price` to the latest
  purchase unit cost. `purchases.balance` = `total_cost - amount_paid` (payable
  semantics are an open decision).
- `app/domain/services/expense_service.py` — `ExpenseService` provides
  Admin-only (`CAP_MANAGE_EXPENSES`) create, update and list for business expenses.
  Free-text category, positive amount, optional description. Expenses are deducted
  from gross profit to produce net profit (Phase 08 reports).
- `app/data/repositories/supplier_repository.py` — list with search, count.
- `app/data/repositories/purchase_repository.py` — list with date range and
  supplier filter, get with details (joined supplier, items).
- `app/data/repositories/expense_repository.py` — list with date range and
  category filter, get with details.
- `app/ui/suppliers/` — Admin screen: supplier list with search, add/edit form.
- `app/ui/purchases/` — Admin screen: purchase list, create-purchase dialog with
  supplier selection, product add (qty + unit cost), live total, amount-paid field,
  complete action.
- `app/ui/expenses/` — Admin screen: expense list with category filter and
  total, add/edit form with category, amount, description and date.
- `app/ui/reports/reports_page.py` — Admin screen: tab-based reporting with
  date-range filters (From/To/Run). Tabs: Sales, Profit, Inventory, Payments,
  Purchases, Expenses, Product Sales, Cashier Sales, End of Day. Each tab
  shows a data table; the Profit tab shows the five-line summary.
- `app/ui/settings/settings_page.py` — Admin screen: backup creation, backup
  listing (newest-first), and database restore with confirmation dialog.
  Restore creates a pre-restore safety backup automatically.
- `app/main.py` — Admin sidebar: Purchases, Suppliers, Expenses, Reports,
  and Settings added after Customers.

## Backup & recovery (Phase 09)

- `app/domain/services/backup_service.py` — `BackupService` provides
  Admin-only (`CAP_BACKUP`, `CAP_RESTORE`) offline local backup and restore.
  Uses `sqlite3.Connection.backup()` for safe online backup (no file copy of
  an in-use database). Backup files stored as
  `funmite_YYYYMMDD_HHMMSS_MICROSECONDS.db` in the configured backup directory.
  Listing returns backups sorted newest-first with filename, size, and creation
  date. Restore validates the backup, creates a pre-restore safety backup,
  replaces the live database, and validates integrity with `PRAGMA
  integrity_check`. Rolls back to safety backup on integrity failure. All
  operations audit-logged via `AuditService` (`ACTION_BACKUP`, `ACTION_RESTORE`).
- `app/ui/settings/settings_page.py` — Settings page with "Create Backup"
  button, backup table (filename, size, created), backup count label, and
  "Restore from Backup" button with confirmation dialog. Uses `BackupService`.
- Permissions: `CAP_BACKUP` and `CAP_RESTORE` are both Admin-only, defined
  in `app/domain/permissions/catalog.py`.

## POS sales (Phase 05)

- `app/domain/services/sale_service.py` — `SaleService.complete_sale()` is the
  single way a sale is written. In one `session_scope` transaction it creates
  the sale header (receipt number `FUN-YYYYMMDD-NNN`, subtotal, discount,
  total), the `sale_items` rows (historical cost/price), the `payments` row
  (only when the total is positive) and then deducts stock per line through
  `InventoryService.change_stock` (`CAP_MAKE_SALE`, `reference_type=REFERENCE_SALE`,
  reason `"Sale"`). Customer is mandatory; `POS`/`TRANSFER` are the only
  accepted payment methods; discount is Admin-only (`CAP_DISCOUNT`,
  `PERCENT`/`FIXED`, never making the total negative); a stock shortage rolls
  everything back.
- `app/domain/services/receipt_service.py` — builds detached receipt data from a
  completed sale, prints it after the transaction commits, and reprints (UC-06)
  Admin-only via `CAP_VIEW_REPORTS`.
- `app/printing/receipt.py` — `ReceiptData`/`ReceiptLine` plain dataclasses
  (safe after the session closes), `ReceiptBuilder` with configurable wireframe
  branding defaults, `render_receipt_text()` and `discount_label()`.
- `app/printing/escpos.py` — pure-Python ESC/POS byte renderer for an 80mm
  thermal printer (init, PC437, alignment, `GS k` Code128 receipt barcode,
  partial cut). ₦ renders as `N` on paper (PC437 has no naira glyph).
- `app/printing/printer.py` — `ReceiptPrinter` abstraction: `NullPrinter`
  (default until the Phase 11 USB printer), `InMemoryPrinter` (tests) and
  `EscPosFilePrinter`.
- `app/ui/pos/` — the POS screen (`PosPage`): barcode scan (auto-focused),
  search, cart with quantity/remove, customer filter/combo + quick walk-in
  registration, Admin-only discount row, BANK POS / BANK TRANSFER payment (no
  cash/credit), offline status label, Sale Complete / Insufficient Stock /
  Barcode Not Found popups, low-stock note scoped to the sale's items, and
  Admin-only reprint. Popups and the printer are injected for testability.
- `app/domain/services/customer_service.py` — `create_for_sale()` lets the
  Cashier register a minimal walk-in customer (name, optional phone) under
  `CAP_MAKE_SALE`; full customer management stays Admin-only.

## Inventory (Phase 04)

- `app/domain/services/inventory_service.py` — `InventoryService` is the single
  way stock changes. `stock_in()` (Admin, `CAP_STOCK_IN`) adds a positive
  quantity; `adjust()` (Admin, `CAP_STOCK_ADJUSTMENT`) sets an absolute
  quantity and requires a reason; both write a full `inventory_logs` row.
  `change_stock()` is the shared movement writer (signed change, reason,
  optional reference type/id, capability parameter) that Phase 05 sales and
  Phase 06 exchanges consume with `CAP_MAKE_SALE` / `CAP_EXCHANGE`. Negative
  results are rejected; no stock ever changes without a logged movement.
  `list_low_stock()` (Admin) applies the confirmed rule `quantity <= 3`.
- `app/data/repositories/inventory_repository.py` — `list_recent()` returns the
  movement history newest-first with the product and user eager-loaded.
- `app/ui/widgets/low_stock_popup.py` — `show_low_stock_alert()` raises the
  low-stock popup with View Stock / Dismiss actions; callers can inject it so
  the decision logic stays testable.
- `app/ui/dashboard/dashboard_page.py` — Admin Dashboard with the low-stock
  indicator and a View Stock shortcut to the Inventory screen (sales/profit
  widgets are Phase 08).
- `app/ui/inventory/inventory_page.py` — Admin Inventory screen with the
  approved wireframe sections: Current Stock (LOW/OK status), Stock In, Adjust,
  Movement and Low Stock.

## Products, customers & barcodes (Phase 03)

- `app/barcode/codes.py` — `NumericBarcodeGenerator` produces unique 13-digit
  barcodes (12-digit sequence + Luhn check digit) starting above the largest
  existing numeric barcode. Uniqueness: above-DB-max seed + in-batch dedup +
  the `products.barcode` `UNIQUE` constraint.
- `app/barcode/labels.py` — `SvgLabelRenderer` renders printer-independent
  Code128 SVG labels (product name + price + digits); physical label printing
  is Phase 11.
- `app/barcode/scanner.py` + `app/ui/widgets/barcode_input.py` — a USB scanner
  types the code and presses Enter; `BarcodeScanInput` emits `barcode_scanned`
  with the cleaned value and resets.
- `app/domain/services/product_service.py` — Admin-only catalogue CRUD + soft
  deactivate/activate; auto `PRD-######` codes; price changes require
  `CAP_CHANGE_PRICE`; `lookup_by_barcode`/`search_products` are shared with
  the Cashier (`CAP_SCAN_BARCODE`).
- `app/domain/services/category_service.py` — category get-or-create/rename,
  gated by `CAP_CREATE_PRODUCT` (the matrix has no separate category
  capability).
- `app/domain/services/customer_service.py` — registration with auto
  `CUS-#####` codes; Admin-only by default (see `OPEN_DECISIONS.md`).
- `app/domain/services/product_import.py` — validated CSV import (per-row
  validation first, per-row errors, valid rows written atomically in one
  transaction, duplicates never overwritten). `sample_template()` documents
  the default header.
- `app/ui/products/` and `app/ui/customers/` — Admin screens; `app/main.py`
  exposes them in Admin navigation only.

## Authentication & authorization (Phase 02)

- `app/domain/permissions/` — the capability catalog and the role→capability
  map taken from the permission matrix in `02_Use_Cases_Workflows`.
  `require_permission(user, capability)` is the single enforcement point used
  by services, so authorization holds even if the UI is bypassed.
- `app/domain/services/auth_service.py` — `AuthService.authenticate()` verifies
  local credentials via PBKDF2 (`app/security/passwords.py`), rejects unknown,
  wrong and disabled accounts with one generic message, and audits every
  outcome. `change_password()` is available for future user management.
- `app/domain/session.py` — `CurrentUser` (immutable snapshot) and `AuthSession`
  (in-memory session holder for the single-user desktop run).
- `app/domain/services/audit_service.py` — writes sensitive-action entries to
  `audit_logs` (migration `002`). Passwords are never stored in the audit log.
- `app/ui/login/login_dialog.py` — the login screen; `app/main.py` orchestrates
  login → main window → logout and shows the signed-in user/role.

## Data layer (Phase 01)

- `app/data/models.py` — ORM models for all 16 approved tables. Constants
  (`ROLE_ADMIN`, `PAYMENT_POS`, `DISCOUNT_PERCENT`, `LOW_STOCK_THRESHOLD`, ...)
  live here and drive the CHECK constraints via `_in_clause()`.
- `app/data/db.py` — `create_db_engine()` sets `PRAGMA foreign_keys=ON` and a
  busy timeout; `session_scope()` / `transaction()` give commit/rollback
  semantics. `DB_FILENAME` is `funmite.db`.
- `app/data/migrations/` — custom versioned runner (no Alembic; chosen so the
  app stays single-file-offline and PyInstaller-friendly). `runner.upgrade()`
  applies `versions/*.py` in order; version history in `schema_version`.
- `app/data/seed.py` — `ensure_seed_users()` creates only safe development
  accounts (Admin + Cashier) when none exist.
- `app/security/passwords.py` — PBKDF2-HMAC-SHA256 via the standard library.
- `app/data/repositories/` — data-access helpers per aggregate
  (`ProductRepository.get_by_barcode`, `SaleRepository.list_between`, ...).
  Business rules belong in `app/domain` services, not here.
