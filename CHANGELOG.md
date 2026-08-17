# Changelog

All notable changes to this project are documented here.

## [1.0.0] — Phase 09 Backup & Recovery

- Added `BackupService` (`app/domain/services/backup_service.py`):
  safe offline local backup and restore for the SQLite database. Uses
  Python's `sqlite3.Connection.backup()` for atomic online backup and
  `VACUUM INTO` for safe restore. Authorization enforced at the service
  layer via `CAP_BACKUP` and `CAP_RESTORE`.
- Added `SettingsPage` (`app/ui/settings/settings_page.py`): Admin
  settings screen with backup creation, backup listing, and database
  restore functionality. Restore creates a pre-restore safety backup
  automatically.
- Added audit constants `ACTION_BACKUP` and `ACTION_RESTORE` to
  `AuditService` (`app/domain/services/audit_service.py`). Backup and
  restore actions are audit-logged with filenames, sizes, and timestamps.
- Added `format_file_size()` helper to `app/utils/formatting.py` for
  human-readable file size display.
- `app/main.py`: Admin sidebar now includes Settings (10 screens total
  for Admin).
- Backup features:
  - **Create Backup**: Admin-only, creates safe SQLite backup using
    `sqlite3.Connection.backup()`. Files stored as
    `funmite_YYYYMMDD_HHMMSS_MICROSECONDS.db` in the configured backup
    directory.
  - **List Backups**: Shows all backups sorted newest-first with filename,
    size, and creation date.
  - **Validate Backup**: Checks SQLite magic bytes and integrity before
    any operation.
  - **Restore**: Replaces live database with selected backup. Always
    creates a pre-restore safety backup first. Validates integrity after
    restore; rolls back to safety backup on integrity failure.
- Backup directory configurable via `FUNMITE_BACKUP_DIR` environment
  variable (default: `<project_root>/backups/`).
- 37 new tests: authorization (6), backup creation (7), listing (4),
  validation (5), restore (5), audit logging (4), edge cases (6).
- All 533 tests passing.

## [0.9.0] — Phase 08 Reports & Dashboard

- Added `ReportingRepository` (`app/data/repositories/reporting_repository.py`):
  read-only aggregation queries for all reports and dashboard KPIs. Uses
  database-level aggregation where possible. Money values are `Decimal` throughout.
- Added `ReportingService` (`app/domain/services/reporting_service.py`):
  authorization wrapper over the repository. Admin has full access to all
  reports (`CAP_VIEW_REPORTS`, `CAP_VIEW_PROFIT`). Cashier is restricted to
  own daily sales via `CAP_VIEW_OWN_SALES` and blocked from profit views.
- Enhanced `DashboardPage` (`app/ui/dashboard/dashboard_page.py`): today's KPI
  widgets — Sales, Gross Profit, Net Profit, Transactions, POS Total,
  Transfer Total — displayed above the existing low-stock indicator. Refresh
  reloads both KPIs and low-stock list.
- Added `ReportsPage` (`app/ui/reports/reports_page.py`): tab-based Admin
  reporting screen with date-range filters (From / To / Run). Tabs: Sales,
  Profit, Inventory, Payments, Purchases, Expenses, Product Sales, Cashier
  Sales, End of Day. Each tab shows a data table with column totals; the
  Profit tab shows the five-line summary (Total Sales, COGS, Gross Profit,
  Expenses, Net Profit). All monetary values formatted with `format_money`.
- `app/main.py`: Admin sidebar now includes Reports (9 screens total for Admin).
- Reports implemented:
  - **Sales report**: receipt, date, customer, cashier, subtotal, discount,
    total, payment method; filtered by date range and optional cashier.
  - **Profit report**: Total Sales, COGS (historical `sale_items.cost_price`),
    Gross Profit, Expenses, Net Profit; date-range filtered. Admin-only.
  - **Inventory report**: product, category, qty, cost, price, inventory value
    (`quantity * cost_price`), min stock, status; sorted by name.
  - **Low stock report**: products with `quantity <= threshold` (default 3).
  - **Payments report**: method, amount, reference, date, recorded by, receipt;
    POS/Transfer totals.
  - **Purchases report**: supplier, date, total cost, amount paid, balance,
    created by; date-range filtered.
  - **Expenses report**: category, description, amount, date, created by;
    date-range filtered.
  - **Product sales report**: per-product qty sold, revenue, cost, profit;
    date-range filtered.
  - **Cashier sales report**: per-cashier total sales and transaction count;
    date-range filtered.
  - **End of day report**: today's complete summary combining sales, expenses,
    payments, and profit.
- Confirmed formulas enforced:
  - COGS = `SUM(sale_items.quantity * sale_items.cost_price)` (historical).
  - Gross Profit = Total Sales - COGS.
  - Net Profit = Gross Profit - Total Expenses.
  - Inventory Value = `SUM(products.quantity * products.cost_price)`.
- No database migration needed: all reports are read-only queries over the
  existing schema.
- Added 39 Phase 08 tests (authorization, dashboard KPIs, sales/profit/
  inventory/payment/purchase/expense/product-sales/cashier-sales/eod reports,
  date boundaries, decimal precision, offline operation).
  Full suite: 497 passing.

## [0.8.0] — Phase 07 Purchases, Suppliers & Expenses

- Added the supplier service (`app/domain/services/supplier_service.py`):
  Admin-only (`CAP_MANAGE_PURCHASES_SUPPLIERS`) CRUD for suppliers — list with
  search by name/phone, create, update. Suppliers are referenced by purchases;
  they do not yet have payment terms or credit semantics (open decision).
- Added the supplier repository (`app/data/repositories/supplier_repository.py`):
  list with search and count.
- Added the purchase service (`app/domain/services/purchase_service.py`):
  `PurchaseService.complete_purchase` writes a whole purchase atomically in one
  `session_scope` transaction — validates the supplier, validates each product
  (exists, active), validates quantities and unit costs, creates the purchase
  header (total_cost, amount_paid, balance), creates `purchase_items` rows
  (historical unit_cost), increases stock per item through the shared
  `InventoryService.change_stock` (`CAP_MANAGE_PURCHASES_SUPPLIERS`,
  `reference_type=STOCK_IN`), and updates each product's `cost_price` to the
  latest purchase unit cost. Any failure rolls the whole transaction back.
- Confirmed rules enforced: Admin is the only role that may record purchases;
  every purchase must have a supplier and at least one item; products must exist
  and be active; quantities must be positive; unit costs must be non-negative;
  amount paid cannot exceed total cost; duplicate product lines are rejected;
  `purchases.balance` = `total_cost - amount_paid` (whether this represents a
  true payable is an open decision — see `OPEN_DECISIONS.md`).
- Added the expense service (`app/domain/services/expense_service.py`):
  Admin-only (`CAP_MANAGE_EXPENSES`) create, update and list for business
  expenses. The `category` field is free-text (scope is an open decision);
  amount must be positive; description is optional.
- Added the expense repository (`app/data/repositories/expense_repository.py`):
  list with date range and category filter.
- Added `PurchaseLine` dataclass and exported `PurchaseService`,
  `SupplierService`, `ExpenseService` from `app/domain/services/__init__.py`.
- Added the Admin Suppliers screen (`app/ui/suppliers/`): list with search,
  add/edit form. Added the Admin Purchases screen (`app/ui/purchases/`):
  list with date display, create-purchase dialog with supplier selection,
  product add (quantity + unit cost), live total, amount-paid field and
  complete action. Added the Admin Expenses screen (`app/ui/expenses/`):
  list with category filter and total, add/edit form with category, amount,
  description and date.
- `app/main.py`: Admin navigation is now Dashboard, POS, Products, Inventory,
  Customers, Purchases, Suppliers, Expenses; the Cashier sees only the POS
  screen.
- No database migration was needed: the frozen `001_initial` schema already
  contains `suppliers`, `purchases`, `purchase_items` and `expenses`.
- Added 63 Phase 07 tests (19 supplier service, 27 purchase service,
  17 expense service — authorization, validation, stock effects, cost-price
  update, rollback, list/get, header/items).
  Full suite: 458 passing.

## [0.7.0] — Phase 06 Exchanges

- Added the exchange service (`app/domain/services/exchange_service.py`):
  `ExchangeService.complete_exchange` writes a whole exchange atomically in one
  `session_scope` transaction — validates the original sale, enforces the 2-day
  window, creates the exchange header (difference amount/type, payment method,
  status), the `exchange_items` rows (historical original price, current
  replacement price), and stock changes through the shared
  `InventoryService.change_stock` (`CAP_EXCHANGE`,
  `reference_type=REFERENCE_EXCHANGE`). Any failure — late exchange, unknown
  product, insufficient replacement stock — rolls everything back.
- Confirmed rules enforced: Admin is the only role that may exchange
  (`CAP_EXCHANGE`); the exchange window is 2 days from the original sale; the
  returned item must have been sold on the original receipt and the returned
  quantity cannot exceed what was sold (already-exchanged quantities across
  prior completed exchanges count against the sale, so the same item cannot be
  over-returned); the original sale is never modified or deleted; returned items
  go back into stock; replacements are deducted. When the replacement is worth
  more than the returned item, Bank POS or Bank Transfer payment is required.
  When the returned items are worth more than the replacement (the customer would
  be owed money), the exchange is refused because the settlement for that case is
  not confirmed — see `OPEN_DECISIONS.md`.
- Added the exchange repository (`app/data/repositories/exchange_repository.py`):
  `list_for_sale` and `exchanged_quantities_for_sale` (aggregate original
  quantities across completed exchanges per sale for over-exchange protection).
- Added the exchange screen (`app/ui/exchanges/`): wireframe-faithful
  `ExchangePage` with receipt-number lookup, return item selection from the
  original sale (quantity spinner per product), replacement product search/add
  with quantity, live difference label, Admin-only POS/Transfer payment radios,
  confirmation popup and complete action. `ExchangeDialog` wraps the page in a
  modal dialog.
- `app/ui/pos/pos_page.py`: Admin-only "Exchange..." button in the title bar
  opens the `ExchangeDialog`. The button is hidden for the Cashier. Exchange
  and confirmation popups are injected for testability.
- Exported `ExchangeService`, `REFERENCE_EXCHANGE` and exchange-related
  constants from `app/domain/services/__init__.py`.
- Added 67 Phase 06 tests (44 exchange service: window, authorization,
  original-receipt validation, returned/replacement item validation, price
  difference under the no-cash rule, atomic stock restore/deduction, audit/history,
  original-sale preservation, over-exchange protection, multi-item, offline;
  23 exchange UI: find, return selection, replacement search/add, live
  difference, payment radios, confirm/complete flow, errors, PosPage button).
  Full suite: 395 passing.

## [0.6.0] — Phase 05 POS Sales

- Added the sale service (`app/domain/services/sale_service.py`):
  `SaleService.complete_sale` writes a whole sale atomically in one
  `session_scope` transaction — header (receipt number, subtotal, discount,
  total), `sale_items` (historical cost/price snapshots), the `payments` row
  (only when the total is positive) and per-line stock deduction through the
  shared `InventoryService.change_stock` (`CAP_MAKE_SALE`,
  `reference_type=REFERENCE_SALE`, reason `"Sale"`). Any failure — including a
  mid-transaction stock shortage — rolls everything back.
- Confirmed rules enforced: a customer is required for every sale; Bank POS and
  Bank Transfer are the only payment methods (cash, credit and anything else
  are rejected); discount is Admin-only (`CAP_DISCOUNT`) with `PERCENT`/`FIXED`
  types that can never make the total negative; quantities must be positive
  whole numbers; products must exist and be active; no duplicate cart lines.
- Added receipt numbering `FUN-<YYYYMMDD>-<NNN>` (daily sequence via
  `SaleRepository.max_receipt_sequence`; the database `UNIQUE` constraint is the
  final guard). This format is a wireframe candidate recorded in
  `OPEN_DECISIONS.md`.
- Added the printing layer: detached receipt data (`app/printing/receipt.py`),
  a pure-Python ESC/POS renderer for an 80mm thermal printer
  (`app/printing/escpos.py`, Code128 receipt barcode, ₦ rendered as `N`), and a
  printer abstraction (`app/printing/printer.py`: `NullPrinter` default,
  `InMemoryPrinter`, `EscPosFilePrinter`). The physical USB printer is Phase 11.
- Added `app/domain/services/receipt_service.py`: build/print after the sale
  commits (printing failure never loses a sale) and the Admin-only reprint
  (UC-06) gated by `CAP_VIEW_REPORTS`.
- Added the POS screen (`app/ui/pos/`): barcode scan + search, cart with
  quantity/remove, customer filter + quick walk-in registration
  (`CustomerService.create_for_sale`), Admin-only discount row,
  BANK POS / BANK TRANSFER payment (no cash/credit buttons), offline status
  label, Sale Complete / Insufficient Stock / Barcode Not Found popups, a
  low-stock note scoped to the sale's own items, and Admin-only reprint.
- `app/main.py`: Admin navigation is now Dashboard, POS, Products, Inventory,
  Customers; the Cashier sees only the POS screen. Barcode "Add product" from
  the POS jumps to Products.
- Added the shared `user_record_id` helper (`app/domain/session.py`) used by the
  sale, payment and inventory-movement writes.
- No database migration was needed (the frozen `001_initial` schema already has
  `sales`, `sale_items` and `payments`).
- Added 87 Phase 05 tests (sale service, receipt service, ESC/POS, POS UI,
  customer quick-create, Admin/Cashier navigation).
  Full suite: 328 passing.

Exchanges, purchases/suppliers/expenses, reports and website screens are not
implemented yet.

## [0.5.0] — Phase 04 Inventory

- Added the inventory service (`app/domain/services/inventory_service.py`):
  stock-in (Admin-only, `CAP_STOCK_IN`) and stock adjustment (Admin-only,
  `CAP_STOCK_ADJUSTMENT`, mandatory reason), both recording a full movement in
  `inventory_logs` (product, previous/change/new quantity, reason, user,
  reference type/id, timestamp).
- Added a shared movement writer (`change_stock`) so Phase 05 sales and Phase 06
  exchanges consume the same inventory logic with their own capability
  (`CAP_MAKE_SALE` / `CAP_EXCHANGE`) instead of duplicating stock rules.
- Enforced the no-negative-stock rule in the service layer (the database CHECK
  constraint remains the final guard); every change is refused if it would push
  quantity below zero.
- Confirmed low-stock rule `quantity <= 3` (`LOW_STOCK_THRESHOLD`) surfaced
  through the service (`list_low_stock`), the Dashboard indicator and a
  popup/notification (`app/ui/widgets/low_stock_popup.py`) with
  View Stock / Dismiss actions.
- Added the Admin Inventory screen (`app/ui/inventory/`) with the approved
  wireframe sections: Current Stock, Stock In, Adjust, Movement and Low Stock.
- Added the Admin Dashboard screen (`app/ui/dashboard/`) with the low-stock
  indicator and a View Stock shortcut to the Inventory screen (sales/profit
  widgets are Phase 08).
- Extended `InventoryLogRepository` with newest-first `list_recent` (product and
  user eager-loaded) for the Movement tab.
- Added Admin Dashboard/Inventory navigation to `app/main.py`.
- No database migration was needed (the schema from `001_initial` already
  contains `inventory_logs`; only repository/service/UI layers changed).
- Added 40 Phase 04 tests (inventory service, movement writer, low-stock
  popup, Dashboard UI, Inventory UI, Admin navigation).
  Full suite: 241 passing.

No POS sales, exchanges, purchases/suppliers/expenses, reports or website
screens are implemented yet.

## [0.4.0] — Phase 03 Products, Customers & Barcodes

- Added unique product barcode generation (`app/barcode/codes.py`): 13-digit
  numeric values (12-digit sequence + Luhn check digit), seeded above the
  largest existing barcode, guaranteed unique per batch and guarded by the
  database `UNIQUE` constraint. Rendered as Code128.
- Added barcode label rendering/printing abstraction (`app/barcode/labels.py`)
  with a printer-independent SVG renderer (product name, price and the code
  under the bars).
- Added scanner input handling (`app/barcode/scanner.py` +
  `app/ui/widgets/barcode_input.py`): a USB scanner types the code and presses
  Enter; `BarcodeScanInput` emits `barcode_scanned` with the cleaned value and
  resets for the next scan.
- Added the product catalogue service (`app/domain/services/product_service.py`):
  Admin-only create/edit/deactivate/activate, automatic `PRD-######` product
  codes, price changes additionally gated by `CAP_CHANGE_PRICE`, fast
  search by name/code/barcode with category filter, and scanner lookup shared
  with the Cashier (`CAP_SCAN_BARCODE`).
- Added category management (`app/domain/services/category_service.py`), gated
  by `CAP_CREATE_PRODUCT` (no separate capability exists in the matrix).
- Added customer registration (`app/domain/services/customer_service.py`):
  auto-generated `CUS-#####` codes, optional phone/address, Admin-only by
  default (see `OPEN_DECISIONS.md`).
- Added bulk product import (`app/domain/services/product_import.py`): a
  documented default CSV template with flexible header aliases, validates
  every row before writing, reports per-row errors, skips invalid rows, and
  imports valid rows atomically in one transaction. Duplicate codes/barcodes
  (in-file or in-database) are reported and never overwritten.
- Added the Admin Products screen (`app/ui/products/`): search, category
  filter, add/edit forms, barcode scan-to-select, bulk import dialog and SVG
  barcode-label export.
- Added the Admin Customers screen (`app/ui/customers/`): list, search and
  add/edit forms.
- Added Admin-only Products/Customers navigation to the main window; the
  Cashier sees a placeholder until the POS screen (Phase 05).
- Added `python-barcode>=0.15` to `requirements.txt`.
- Added 71 Phase 03 tests (barcode codes/labels, product/category/customer
  services, import, scanner widget, Products/Customers UI, main-window nav).
  Full suite: 201 passing.

No POS sales, inventory, exchanges, reports or website screens are implemented
yet.

## [0.3.0] — Phase 02 Authentication & Authorization

- Added the role-based permission catalog (`app/domain/permissions/`) mirroring
  the matrix in `02_Use_Cases_Workflows`; authorization is enforced in the
  domain layer (`require_permission`/`has_permission`), never only via UI.
- Added domain exceptions (`AuthenticationError`, `AuthorizationError`).
- Added the `AuthService`: local login (valid/unknown/wrong/disabled account),
  logout, and password change with audit entries on every outcome. Failed
  logins are audited and committed even though they raise.
- Added current-user/session handling (`app/domain/session.py`:
  `CurrentUser`, `AuthSession`).
- Added audit logging (`app/domain/services/audit_service.py`) and the
  `audit_logs` table via migration `002_audit_logs` (passwords are never
  written to the audit log).
- Migration `001_initial` was frozen to the approved 16 tables so later
  additive migrations are the only place their tables are created.
- Added the login dialog (`app/ui/login/`) with masked password input, safe
  error messages and an "Offline mode supported" hint, plus the signed-in
  user/role display and logout in `app/main.py`.
- Added 74 Phase 02 tests (permissions, auth service, audit, session, login
  UI, audit-log migration, main-window user display). Full suite: 130 passing.

No business screens (products, POS, inventory, reports) are implemented yet.

## [0.2.0] — Phase 01 Database

- Added SQLAlchemy 2.0 models for all 16 tables from the approved schema
  (`users`, `categories`, `products`, `customers`, `sales`, `sale_items`,
  `payments`, `inventory_logs`, `suppliers`, `purchases`, `purchase_items`,
  `expenses`, `exchanges`, `exchange_items`, `sync_queue`, `sync_state`).
- Money columns use `Numeric(12, 2)` / `Decimal`; timestamps are naive,
  shop-local datetimes.
- CHECK constraints and indexes generated from app-level constants
  (`app/data/models.py`), including `ck_payments_amount`, low stock <= 3.
- Added SQLite engine/session/transaction helpers (`app/data/db.py`) with
  `PRAGMA foreign_keys=ON` and busy timeout.
- Added a custom lightweight migration runner (`app/data/migrations/`) — no
  Alembic dependency, offline/PyInstaller friendly — with initial migration
  (`001_initial`).
- Added idempotent dev seed users (`app/data/seed.py`), overridable via
  `FUNMITE_SEED_ADMIN_*` / `FUNMITE_SEED_CASHIER_*` env vars.
- Added PBKDF2-HMAC-SHA256 password hashing (`app/security/passwords.py`).
- Added repositories under `app/data/repositories/` (users, categories,
  products with barcode/code/search/low-stock lookups, customers, sales with
  receipt/date/cashier lookups, inventory logs).
- Added 46 Phase 01 tests (schema, constraints, relationships, transaction
  rollback, repositories, seeding + password hashing). Full suite: 56 passing.

No business UI features are implemented in this version.

## [0.1.0] — Phase 00 Foundation

- Created the project skeleton per the approved technical architecture.
- Added configuration handling (`app/config.py`, `.env.example`).
- Added logging setup (console + rotating file handler).
- Added a minimal desktop application shell (`app/main.py`).
- Added pytest + pytest-qt testing framework with initial tests.
- Added `README.md`, `OPEN_DECISIONS.md`, `docs/`, `scripts/`.

No business features are implemented in this version.
