# Funmite POS — Project Status

Status file for the implementation project. On resume, verify against the
actual code and test output before trusting the claims below.

## Current phase

**v1.3.0 UI/UX Polish COMPLETE - Ready for Physical Validation & UAT** (657 tests passing)

## Completed phases

| Phase | Name | Status |
|-------|------|--------|
| 00 | Foundation | COMPLETE |
| 01 | Database | COMPLETE |
| 02 | Authentication & Authorization | COMPLETE |
| 03 | Products, Customers & Barcodes | COMPLETE |
| 04 | Inventory | COMPLETE |
| 05 | POS Sales | COMPLETE |
| 06 | Exchanges | COMPLETE |
| 07 | Purchases, Suppliers & Expenses | COMPLETE |
| 08 | Reports & Dashboard | COMPLETE |
| 09 | Backup & Recovery | COMPLETE |
| 10 | Hybrid Offline-First Cloud Sync | COMPLETE |
| 11 | Production Hardening & Deployment | COMPLETE |
| -- | UI/UX Polish (v1.3.0) | COMPLETE |
| 12 | Physical Hardware Validation & UAT | PENDING - waiting for hardware |

## Next action

Physical hardware validation required: barcode scanner, thermal printer, two-PC
sync, clean Windows installation. Then client UAT. Do not proceed to website
development.

## Phase 05 summary

Implemented the cashier/Admin POS screen and the atomic offline sale per the
phase prompt, the spec, the approved wireframe and the confirmed rules:

- `app/domain/services/sale_service.py` — `SaleService.complete_sale` is the
  only way a sale is written. One `session_scope` transaction: create the sale
  header (receipt number, subtotal, discount, total), the `sale_items` rows
  (historical cost/price snapshots), the `payments` row (only when the total is
  positive), then per line deduct stock through the shared
  `InventoryService.change_stock` (capability `CAP_MAKE_SALE`,
  `reference_type=REFERENCE_SALE`, reason `"Sale"`). Any failure rolls the whole
  transaction back. Stock sufficiency is enforced atomically by `change_stock`;
  there is no pre-validation, so a mid-transaction shortage proves real rollback.
- Confirmed rules enforced: every sale needs a customer; Bank POS and Bank
  Transfer are the only payment methods (`CASH`/`CREDIT`/anything else is
  rejected); discount is Admin-only (`CAP_DISCOUNT`), `PERCENT` or `FIXED`,
  and cannot make the total negative; product quantity must be a positive whole
  number; products must exist and be active; the same product cannot appear on
  two cart lines.
- Receipt numbering: candidate `FUN-<YYYYMMDD>-<NNN>` (daily sequence scanned
  with `SaleRepository.max_receipt_sequence`); the database `UNIQUE` constraint
  is the final guard and a collision rolls the transaction back.
- `app/domain/services/customer_service.py` — `create_for_sale` lets the
  Cashier register a minimal walk-in customer (name required, phone optional)
  under `CAP_MAKE_SALE`; full customer management stays Admin-only.
- Printing layer (technical architecture section 8 — POS business logic never
  touches printer code):
  - `app/printing/receipt.py` — detached `ReceiptData`/`ReceiptLine` and
    `ReceiptBuilder` (safe to render after the session closes), wireframe
    branding defaults, `discount_label` and `render_receipt_text`.
  - `app/printing/escpos.py` — pure-Python ESC/POS renderer for an 80mm thermal
    printer (init, PC437, alignment, `GS k` Code128 receipt barcode, partial
    cut); the naira sign renders as a plain `N` (PC437 has no ₦ glyph).
  - `app/printing/printer.py` — `ReceiptPrinter` abstraction: `NullPrinter`
    (default until the Phase 11 hardware), `InMemoryPrinter` (tests) and
    `EscPosFilePrinter`.
- `app/domain/services/receipt_service.py` — build/print after the sale
  commits (a sale is never lost because printing failed) and the Admin-only
  reprint (UC-06) gated by `CAP_VIEW_REPORTS`.
- `app/ui/pos/` — `PosPage` mirrors the wireframe: barcode scan (auto-focused),
  search + results, cart table with quantity spinners and remove, customer
  filter/combo + New Customer…, Admin-only discount row, Subtotal/Discount/TOTAL
  readout, BANK POS / BANK TRANSFER (no cash/credit buttons), payment reference,
  COMPLETE SALE, offline status label, low-stock note scoped to the sold items,
  Sale Complete / Insufficient Stock / Barcode Not Found popups and the
  Admin-only Reprint. Popups and the printer are injected so the page is fully
  testable.
- `app/main.py` — Admin navigation per the wireframe sidebar: Dashboard, POS,
  Products, Inventory, Customers; the Cashier sees only the POS screen. Barcode
  "Add product" from the POS jumps to Products.
- No database migration was needed: the frozen `001_initial` schema already
  contains `sales`, `sale_items` and `payments`.
- Version bumped to 0.6.0.

## Phase 06 summary

Implemented the exchange screen and the atomic offline exchange per the
phase prompt, the spec, the approved wireframe and the confirmed rules:

- `app/domain/services/exchange_service.py` — `ExchangeService.complete_exchange`
  is the only way an exchange is written. One `session_scope` transaction:
  validate the original sale (must exist, within the 2-day window, Admin-only
  via `CAP_EXCHANGE`), create the exchange header (difference amount/type,
  payment method, status) and `exchange_items` rows (historical original price,
  current replacement price), then return items to stock and deduct replacements
  through `InventoryService.change_stock` (`CAP_EXCHANGE`,
  `reference_type=REFERENCE_EXCHANGE`). Any failure rolls the whole transaction
  back.
- Confirmed rules enforced: Admin is the only role that may exchange
  (`CAP_EXCHANGE`); the 2-day window is enforced from the original sale date;
  the original sale is never modified or deleted; returned items go back into
  stock; replacements are deducted; when the replacement costs more, Bank POS
  or Bank Transfer payment is required; when the customer would be owed money,
  the exchange is refused (see `OPEN_DECISIONS.md`).
- `app/data/repositories/exchange_repository.py` — `list_for_sale` and
  `exchanged_quantities_for_sale` (aggregate original quantities across
  completed exchanges for over-exchange protection).
- `app/ui/exchanges/` — wireframe-faithful `ExchangePage` with receipt-number
  lookup, return item selection from the original sale (with quantity spinner),
  replacement product search/add (with quantity), live difference label,
  Admin-only POS/Transfer payment radios, confirmation popup and complete
  action. `ExchangeDialog` wraps the page in a modal dialog.
- `app/ui/pos/pos_page.py` — Admin-only "Exchange..." button in the title bar
  opens the `ExchangeDialog`. The button is hidden for the Cashier. Exchange
  and confirmation popups are injected for testability.
- No database migration was needed: the frozen `001_initial` schema already
  contains `exchanges` and `exchange_items`.
- Version bumped to 0.7.0.

## Phase 07 summary

Implemented the back-office stock and expense workflows per the phase prompt,
the spec, the approved wireframe and the confirmed rules:

- `app/domain/services/supplier_service.py` — `SupplierService` provides
  Admin-only (`CAP_MANAGE_PURCHASES_SUPPLIERS`) CRUD for suppliers: list with
  search by name/phone, create, update. Suppliers are referenced by purchases.
- `app/domain/services/purchase_service.py` — `PurchaseService.complete_purchase`
  is the only way a purchase is written. One `session_scope` transaction:
  validate supplier and each product (exists, active, not duplicate), validate
  quantities and unit costs, create the purchase header (total_cost, amount_paid,
  balance), create `purchase_items` rows (historical unit_cost), increase stock
  per item through `InventoryService.change_stock` (`CAP_MANAGE_PURCHASES_SUPPLIERS`,
  `reference_type=STOCK_IN`), and update each product's `cost_price` to the
  latest purchase unit cost. Any failure rolls the whole transaction back.
- `app/domain/services/expense_service.py` — `ExpenseService` provides
  Admin-only (`CAP_MANAGE_EXPENSES`) create, update and list for business
  expenses. Free-text category, positive amount, optional description.
- Confirmed rules enforced: Admin is the only role that may record purchases
  or expenses; every purchase must have a supplier and at least one item;
  products must exist and be active; quantities must be positive; unit costs
  must be non-negative; amount paid cannot exceed total cost; duplicate product
  lines are rejected; `purchases.balance` = `total_cost - amount_paid` (payable
  semantics are an open decision — see `OPEN_DECISIONS.md`).
- `app/data/repositories/supplier_repository.py` — list with search, count.
- `app/data/repositories/purchase_repository.py` — list with date range and
  supplier filter, get with details.
- `app/data/repositories/expense_repository.py` — list with date range and
  category filter, get with details.
- `app/ui/suppliers/` — Admin screen: supplier list with search, add/edit form.
- `app/ui/purchases/` — Admin screen: purchase list, create-purchase dialog
  with supplier selection, product add (qty + unit cost), live total,
  amount-paid field, complete action.
- `app/ui/expenses/` — Admin screen: expense list with category filter and
  total, add/edit form with category, amount, description and date.
- `app/main.py` — Admin sidebar: Purchases, Suppliers, Expenses added after
  Customers (8 screens total for Admin).
- No database migration was needed: the frozen `001_initial` schema already
  contains `suppliers`, `purchases`, `purchase_items` and `expenses`.
- Version bumped to 0.8.0.

## Phase 08 summary

Implemented the reporting dashboard and report screens per the phase prompt,
the spec, the approved wireframe and the confirmed rules:

- `app/data/repositories/reporting_repository.py` — `ReportingRepository`:
  read-only aggregation queries for all reports and dashboard KPIs. Uses
  database-level aggregation where possible. Money values are `Decimal`.
- `app/domain/services/reporting_service.py` — `ReportingService`:
  authorization wrapper over the repository. Admin has full access
  (`CAP_VIEW_REPORTS`, `CAP_VIEW_PROFIT`). Cashier is restricted to own
  daily sales via `CAP_VIEW_OWN_SALES` and blocked from profit views.
- Enhanced `app/ui/dashboard/dashboard_page.py`: today's KPI widgets —
  Sales, Gross Profit, Net Profit, Transactions, POS Total, Transfer Total —
  displayed above the existing low-stock indicator.
- `app/ui/reports/reports_page.py` — `ReportsPage`: tab-based Admin
  reporting screen with date-range filters (From / To / Run). Tabs: Sales,
  Profit, Inventory, Payments, Purchases, Expenses, Product Sales, Cashier
  Sales, End of Day.
- `app/main.py` — Admin sidebar now includes Reports (9 screens total).
- Reports implemented:
  - Sales report: receipt, date, customer, cashier, subtotal, discount,
    total, payment method; filtered by date range and optional cashier.
  - Profit report: Total Sales, COGS (historical `sale_items.cost_price`),
    Gross Profit, Expenses, Net Profit; date-range filtered. Admin-only.
  - Inventory report: product, category, qty, cost, price, inventory value,
    min stock, status.
  - Low stock report: products with `quantity <= threshold`.
  - Payments report: method, amount, reference, date, recorded by, receipt;
    POS/Transfer totals.
  - Purchases report: supplier, date, total cost, amount paid, balance.
  - Expenses report: category, description, amount, date, created by.
  - Product sales report: per-product qty sold, revenue, cost, profit.
  - Cashier sales report: per-cashier total sales and transaction count.
  - End of day report: today's complete summary.
- Confirmed formulas enforced:
  - COGS = `SUM(sale_items.quantity * sale_items.cost_price)` (historical).
  - Gross Profit = Total Sales - COGS.
  - Net Profit = Gross Profit - Total Expenses.
  - Inventory Value = `SUM(products.quantity * products.cost_price)`.
- No database migration needed: all reports are read-only queries.
- Version bumped to 0.9.0.

### Engineering decisions recorded

- Product `cost_price` is updated to the latest purchase unit cost. Historical
  sale-item costs are preserved in `sale_items.cost_price` and never overwritten.
  This means the product's current cost reflects the latest purchase while old
  profit reports remain correct.
- `purchases.balance` = `total_cost - amount_paid`. Whether this represents a
  true payable with aging or is simply an informational record is an open
  decision (see `OPEN_DECISIONS.md`). Until confirmed, no payment tracking,
  aging or supplier-statement functionality is implemented.
- Expense `category` is free-text. Whether the allowed set is constrained or
  open is an open decision (see `OPEN_DECISIONS.md`).
- Stock-in from purchases goes through the same `InventoryService.change_stock`
  writer as standalone stock-in, sales and exchanges, with
  `reference_type=STOCK_IN`. This ensures every stock movement is auditable.

### Engineering decisions recorded

- The payment method for exchanges is validated against
  `VALID_PAYMENT_METHODS`; only POS and TRANSFER are accepted, matching the
  sale rules. Cash and credit are rejected.
- Customer-owed refunds (when the returned item costs more than the replacement)
  are blocked with `ValidationError`. The settlement method must be confirmed
  before that branch can be implemented (see `OPEN_DECISIONS.md`).
- Over-exchange protection uses `exchanged_quantities_for_sale` to aggregate
  already-exchanged quantities from all completed exchanges on the same sale,
  preventing the same item from being returned more times than it was sold.
- Multi-item exchanges (multiple return lines and/or multiple replacement lines
  in a single exchange) are validated per line; mixed settlement across lines
  is not yet confirmed (see `OPEN_DECISIONS.md`).

### Engineering decisions recorded

- The payment method is validated against `VALID_PAYMENT_METHODS`; cash, credit
  and split payments are rejected (Phase 06 exchanges already need a decision
  on the no-cash refund rule).
- Receipt branding, header/address/phone/footer and the `FUN-…` receipt number
  format are candidates from the wireframe — all configurable in
  `ReceiptBuilder` — pending client confirmation (recorded in
  `OPEN_DECISIONS.md`).
- Reprint is Admin-only and gated by `CAP_VIEW_REPORTS` because the permission
  matrix has no dedicated "reprint" capability.
- A fully-discounted sale (total 0) gets no `payments` row (DB CHECK
  `amount > 0`); the header records the zero total.
- ESC/POS output renders ₦ as `N`; the physical USB printer arrives in Phase 11.
- `app/domain/session.py` gained the shared `user_record_id` helper so services
  can record the correct user id for ORM rows whether they are handed a
  `CurrentUser` or an ORM `User`.

## Phase 10 summary

Implemented hybrid offline-first cloud synchronization so two independent PCs
can each run the full POS from local SQLite and periodically push/pull changes
to a cloud PostgreSQL (via SQLite in development) for remote owner access.

Architecture: **Option A — Dual Independent SQLite + Cloud Sync**. Each PC has
its own `funmite.db`. A sync outbox (`sync_queue` table) buffers mutations. A
background `SyncWorker` thread pushes pending items and pulls cloud changes.

- `app/sync/cloud_models.py` — Cloud-only ORM models (cloud-only engine, not
  the local SQLite schema). `CloudSale.customer_sync_uuid` is nullable for
  walk-in customers.
- `app/sync/cloud_db.py` — Cloud engine/session management with `StaticPool`
  for in-memory test databases.
- `app/sync/schemas.py` — Pydantic wire format models (`PushPayload`,
  `PushMutation`, `PulledMutation`, `PullResponse`).
- `app/sync/cloud_api.py` — FastAPI endpoints: `/api/sync/push`,
  `/api/sync/pull`, `/api/sync/status`, `/api/sync/devices/register`. Version
  column is conditionally injected (`hasattr(model_cls, "version")`) for
  append-only entities that lack it.
- `app/sync/client.py` — `SyncClient` (httpx-based, creates new
  `httpx.Client` per request for thread safety).
- `app/sync/apply.py` — Apply pulled mutations to local DB with FK
  resolution, append-only dedup, version-based conflict resolution, and
  user-record skip.
- `app/sync/worker.py` — `SyncWorker` background daemon thread with
  `trigger_push()` and `trigger_pull()` public methods.
  `resolve_push_payload()` translates local integer FKs to sync_uuid
  references. `customer_id=0` is treated as unresolvable (walk-in).
- `app/sync/device_registration.py` — Device registration module
  (`register_device()`, `is_registered()`, `load_credentials()`,
  `save_credentials()`). Uses httpx to call cloud `/api/sync/devices/register`.
- `app/sync/__init__.py` — Package exports.
- `app/data/migrations/003_sync_metadata.py` — Adds `sync_uuid`,
  `version`, `device_id` columns to all synced entity tables.
- `app/main.py` — `AppController` creates/starts/stops `SyncWorker` on
  login/logout. Worker starts only when `cloud_sync_enabled` AND
  `sync_credentials.json` exists. `MainWindow` accepts `sync_worker`
  parameter and refreshes a cloud sync status indicator every 5 seconds.
- `app/ui/settings/settings_page.py` — Extended with Cloud Sync section:
  status display, device ID, pending count, registration form (URL + device
  name + Register button), and Sync Now button.
- 10 services updated with `SyncService.enqueue_create/update/delete` calls:
  CategoryService, CustomerService, SupplierService, ProductService,
  InventoryService, SaleService, ExchangeService, PurchaseService,
  ExpenseService, and auth service (login/logout audit entries).
- Conflict strategy: append-only for financial records (sale, sale_item,
  payment, exchange, exchange_item, purchase, purchase_item, expense,
  inventory_log); version column + last-write-wins for mutable reference
  data (category, product, customer, supplier); users are never synced.
- Globally unique IDs: `sync_uuid TEXT` (UUID v4) on all synced entities.
  Local `id INTEGER PRIMARY KEY` stays as local PK.
- Receipt numbers: `FUN-YYYYMMDD-NNN` format preserved through sync
  round-trip (device prefix deferred — ambiguous in source-of-truth).

## Tests

### Phase 10 — sync tests (124 new, 657 total)

- `test_sync.py` — 47 tests: sync queue/state repositories, device
  identity, sync service enqueue, model sync fields, FK migration.
- `test_cloud_sync.py` — 56 tests: cloud API push/pull endpoints (39),
  FK resolution round-trip (10), device registration flow (7).
- `test_sync_integration.py` — 21 tests: production-style end-to-end
  integration tests (A through J):
  - A: Category push/pull round-trip between two PCs
  - B: Reference data last-write-wins conflict resolution
  - C: Append-only entities (sale + sale_item) preserved on conflict
  - D: User records never synced to cloud
  - E: Sync does not block local POS operations
  - F: Inventory logs sync with quantity derived from movements
  - G: Receipt number format preserved after sync round-trip
  - H: User records are never synced (pull skip + cloud absence)
  - I: Pull applies mutations to local DB correctly
  - J: FK resolution end-to-end for all entity types
- Pre-existing flaky test: `test_multiple_backups_all_valid` (backup
  filename collision due to second-precision timestamps). Documented,
  does not block sync integration.

657 tests passing (the flaky backup test is a known pre-existing
issue unrelated to Phase 10; it may fail or pass depending on timing).

- `app/data/repositories/reporting_repository.py` (new)
- `app/domain/services/reporting_service.py` (new)
- `app/domain/services/__init__.py` (exports `ReportingService`)
- `app/ui/dashboard/dashboard_page.py` (enhanced with KPI widgets)
- `app/ui/reports/__init__.py` (new)
- `app/ui/reports/reports_page.py` (new)
- `app/main.py` (added Reports to Admin sidebar)
- `app/__init__.py`, `pyproject.toml` (version 0.9.0)
- Tests (new): `test_reporting_service.py`
- Updated: `tests/test_app_shell.py` (navigation assertions for 9 Admin screens)
- Docs: `CHANGELOG.md`, `README.md`, `docs/README.md`, `PROJECT_STATUS.md`

## Files worked on this session (Phase 07)

- `app/domain/services/supplier_service.py` (new)
- `app/domain/services/purchase_service.py` (new)
- `app/domain/services/expense_service.py` (new)
- `app/domain/services/__init__.py` (exports `SupplierService`, `PurchaseService`,
  `PurchaseLine`, `ExpenseService`)
- `app/data/repositories/supplier_repository.py` (new)
- `app/data/repositories/purchase_repository.py` (new)
- `app/data/repositories/expense_repository.py` (new)
- `app/ui/suppliers/` (new): `__init__.py`, `suppliers_page.py`, `supplier_form.py`
- `app/ui/purchases/` (new): `__init__.py`, `purchases_page.py`, `purchase_form.py`
- `app/ui/expenses/` (new): `__init__.py`, `expenses_page.py`, `expense_form.py`
- `app/main.py` (added Purchases/Suppliers/Expenses to Admin sidebar)
- `app/__init__.py`, `pyproject.toml` (version 0.8.0)
- Tests (new): `test_supplier_service.py`, `test_purchase_service.py`,
  `test_expense_service.py`
- Updated: `tests/test_app_shell.py` (navigation assertions for 8 Admin screens)
- Docs: `CHANGELOG.md`, `README.md`, `docs/README.md`, `PROJECT_STATUS.md`

## Files worked on this session (Phase 06)

- `app/domain/services/exchange_service.py` (new); `app/domain/services/__init__.py`
  (exports `ExchangeService`, `REFERENCE_EXCHANGE`, `EXCHANGE_WINDOW_DAYS`,
  `EXCHANGE_RETURN_REASON`, `EXCHANGE_REPLACEMENT_REASON`)
- `app/data/repositories/exchange_repository.py` (new)
- `app/ui/exchanges/` (new): `__init__.py`, `exchange_page.py`,
  `exchange_dialog.py`, `popups.py`
- `app/ui/pos/pos_page.py` (added "Exchange..." button + `_open_exchange`)
- `app/__init__.py`, `pyproject.toml` (version 0.7.0)
- Tests (new): `test_exchange_service.py`, `test_exchange_ui.py`
- Docs: `CHANGELOG.md`, `README.md`, `docs/README.md`, `OPEN_DECISIONS.md`,
  `PROJECT_STATUS.md`

## Files worked on this session (Phase 05)

- `app/domain/services/sale_service.py` (new); `app/domain/services/__init__.py`
  (exports `SaleService`, `ReceiptService`, `RECEIPT_PREFIX`, `SALE_ITEM_REASON`)
- `app/domain/services/customer_service.py` (added `create_for_sale`)
- `app/domain/services/receipt_service.py` (new)
- `app/data/repositories/sale_repository.py` (added `max_receipt_sequence`)
- `app/domain/session.py` (added `user_record_id`);
  `app/domain/services/inventory_service.py` (uses it)
- `app/utils/formatting.py` (new: `format_money`, `NAIRA`)
- `app/printing/` (new): `receipt.py`, `escpos.py`, `printer.py`, `__init__.py`
- `app/ui/pos/` (new): `pos_page.py`, `popups.py`, `quick_customer.py`, `__init__.py`
- `app/main.py` (POS navigation for Admin + Cashier)
- `app/__init__.py`, `pyproject.toml` (version 0.6.0)
- Tests (new): `test_sale_service.py`, `test_receipt_service.py`,
  `test_escpos.py`, `test_pos_ui.py`; updated `test_customer_service.py` and
  `test_app_shell.py`
- Docs: `README.md`, `CHANGELOG.md`, `docs/README.md`, `PROJECT_STATUS.md`,
  `OPEN_DECISIONS.md`

## Tests

Run with `.venv\Scripts\python.exe -m pytest` (497 tests):

- Phase 00: 10 tests — passing
- Phase 01: 46 tests — passing
- Phase 02: 74 tests — passing
- Phase 03: 71 tests — passing
- Phase 04: 40 tests — passing
- Phase 05: 87 tests — passing
- Phase 06: 67 tests — passing
- Phase 07: 63 tests — passing
- Phase 08 (39 tests):
  - `test_reporting_service.py` — authorization (admin allowed, cashier
    blocked from dashboard/profit, unauthenticated blocked, cashier sales
    restricted to own), dashboard KPIs (empty, sales, transfer, expenses,
    multiple sales, date filtering), sales report (empty, with data, date
    filter), profit report (empty, with sales+expenses, historical cost),
    inventory report (empty, with products, current cost), low stock
    (none, products, custom threshold), payment report (empty, POS+transfer),
    purchase report (empty), expense report (empty, with data), product
    sales report (empty, with data), cashier sales report (empty, multiple
    users), end of day (empty, with data), date boundaries (excludes out of
    range, specific range), decimal precision (Decimal not float), offline
    operation (all reports complete without network)

Result on resume: **497 passed**.

## Phase 08 acceptance criteria verification

- [x] All approved reports are implemented (Sales, Profit, Inventory, Low Stock,
      Payments, Purchases, Expenses, Product Sales, Cashier Sales, End of Day).
- [x] Dashboard works correctly with today's KPIs (Sales, Gross Profit, Net
      Profit, Transactions, POS/Transfer totals).
- [x] Calculations verified: COGS uses historical cost, Gross Profit = Sales -
      COGS, Net Profit = Gross Profit - Expenses, Inventory Value = qty * cost.
- [x] Permissions enforced: Admin full access; Cashier restricted to own daily
      sales; profit views Admin-only.
- [x] Offline operation works (all reports from local SQLite).
- [x] Existing functionality remains intact.
- [x] Service tests pass (39 new).
- [x] Full regression suite passes.
- [x] Documentation updated.
- [x] Version bumped to 0.9.0.

## Phase 10 acceptance criteria verification

- [x] Each PC runs independently with its own SQLite database.
- [x] Offline-first: all POS, sales, inventory, receipt, exchange, report,
      and backup operations work without Internet.
- [x] Cloud sync never blocks local operations.
- [x] Sync outbox pattern: mutations queued locally, pushed in background.
- [x] Push: local mutations sent to cloud PostgreSQL.
- [x] Pull: cloud mutations applied locally with FK resolution.
- [x] Conflict resolution: append-only for financial records, version-based
      for mutable reference data, users never synced.
- [x] Globally unique `sync_uuid` on all synced entities.
- [x] Device registration flow working end-to-end.
- [x] Settings UI: Cloud Sync section with registration, status, Sync Now.
- [x] Sync status indicator in main window status bar.
- [x] Receipt number format preserved through sync round-trip.
- [x] Inventory sync: movement-based (sync inventory_logs, not product.quantity).
- [x] Production integration tests (21 tests, A through J) all passing.
- [x] Full regression suite passes (657/657 — 1 pre-existing flaky backup test).
- [x] Documentation updated.
- [x] Version bumped to 1.1.0.

## UI/UX Polish (v1.3.0) summary

Professionalized the UI for client presentation. No new business logic;
all 657 tests continue to pass. Changes: theme consolidation, page
titles, empty states, consistent tokens, visual cleanup.

- Theme: consolidated `_darken`/`_lighten` into `theme.py` as public
  `darken()`/`lighten()` functions; removed 3 duplicate local definitions.
- Added `INFO` and `INFO_LIGHT` tokens; added `empty_state_message()` helper.
- Added page titles and subtitles to Customers, Suppliers, Expenses,
  Purchases, Products, and Settings pages.
- Replaced all hardcoded font sizes (`20px`, `16px`) with theme tokens.
- Replaced hardcoded color hex values in settings page with theme tokens.
- Removed QGraphicsDropShadowEffect from dashboard cards.
- Polished status bar: `"Admin * Jamilu | v1.3.0"` format.
- Added empty-state labels to 10+ tables (Customers, Suppliers, Expenses,
  Purchases, Products, Inventory tabs) and POS cart.
- Standardized form save/complete button heights to 44px.
- Improved reports summary label to show tab name and date range.
- Removed redundant 55-line local QSS block from Products page.
- Updated `test_app_shell.py` for new status bar format.
- 657 tests passing (0 failures).
- EXE rebuilt with all 11 SVG icons + logo bundled.


## Blockers

- None.

## Open decisions (blocking later phases)

| Decision | Blocks | Open? |
|----------|--------|-------|
| Exchange refund / price-difference under the no-cash rule | Phase 06 (exchanges) | Yes |
| Receipt number prefix/format | Phase 05 (receipts) | RESOLVED - `FUN-YYYYMMDD-NNN` implemented |
| Discount limits and who may discount | Phase 05 (POS) | RESOLVED - Admin-only discount confirmed and implemented |
| Barcode symbology/format (currently candidate: 13-digit numeric -> Code128) | Phase 03 (labels) | RESOLVED - 13-digit numeric + Luhn, Code128 symbology |
| Import columns / format (currently documented default template) | Phase 03 (bulk import) | Yes — default implemented, confirmation pending |
| Backup retention / destination | Phase 09 (backup) | Yes — all backups kept; no auto-purge |
| Selected cloud/hybrid package and LAN sync method | Phase 10 (sync) | RESOLVED — Option A implemented |
| Deployment topology (single local `.db` vs Admin-hosted LAN FastAPI) | Phase 01 data access + Phase 10 | RESOLVED — dual independent SQLite + cloud |
| Receipt barcode content (receipt number exactly?) | Phase 05 (receipt barcode) | RESOLVED - receipt number encoded as Code128 |
| Expenses scope (all vs selected categories) | Phase 07 (expenses) | Yes — free-text category, no constraint |
| Supplier purchase `balance` semantics (true payable vs record only) | Phase 07 (purchases) | Yes — balance = total_cost - amount_paid |
| Final report list | Phase 08 (reports) | Partially — core reports implemented; export/print format unconfirmed |
| Customer-record management permission | Phase 03 (customers) | RESOLVED - Admin-only + cashier walk-in |
| Inventory management permission (stock/history viewing) | Phase 04 (inventory) | RESOLVED - Admin-only |
| Customer without phone | Phase 03 (customers) | RESOLVED - nullable phone, no uniqueness constraint |
| Receipt branding/header/footer text | Phase 05 (receipts) | RESOLVED - wireframe candidate defaults in ReceiptBuilder |
| Low-stock note shown after a sale | Phase 05 (POS) | RESOLVED - scoped to sale items only |
| Stock-in without purchase record | Phase 04 (inventory) | RESOLVED - both standalone and purchase-linked flow through InventoryService |
| Low-stock popup scope | Phase 04 (inventory) | RESOLVED - triggered after stock ops and sales below threshold |
| ESC/POS naira rendering (₦ → `N`) | Phase 11 (printer) | Yes — `N` used until then |

Details and rationale in `OPEN_DECISIONS.md`.

## Verification / resume notes

On restart:

1. Run `.venv\Scripts\python.exe -m pytest` — expect 657 passing tests.
2. Run the offscreen smoke: `python -m app.main` should show the login dialog
   (offline-safe). Log in with `admin/admin123` (Admin) to see the Dashboard
   (today KPIs + low-stock), POS, Products, Inventory, Customers, Purchases,
   Suppliers, Expenses, Reports, and Settings screens (with Cloud Sync
   section); `cashier/cashier123` sees only the POS screen.
3. Inspect `app/sync/` directory, `app/ui/settings/settings_page.py` before
   touching them.
4. Re-read `PROJECT_STATUS.md` and `OPEN_DECISIONS.md` before starting
   Phase 11.
5. Do not proceed to hardware validation or Phase 11 without explicit instruction.