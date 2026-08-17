# Funmite POS — Project Status

Status file for the implementation project. On resume, verify against the
actual code and test output before trusting the claims below.

## Current phase

**Phase 09 — Backup & Recovery: COMPLETE** (533 tests passing)

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

## Next action

Begin **Phase 10** when instructed. Do not jump phases.

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

## Files worked on this session (Phase 08)

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
- [x] Existing functionality remains intact (497/497 baseline green).
- [x] Service tests pass (39 new).
- [x] Full regression suite passes (497/497).
- [x] Documentation updated.
- [x] Version bumped to 0.9.0.

## Phase 07 acceptance criteria verification

- [x] Suppliers are managed (create, update, list with search). Admin-only.
- [x] Purchases are recorded atomically: supplier validated, products validated,
      purchase header and items created, stock increased through the shared
      inventory writer, product cost_price updated, inventory logs written.
- [x] Expenses are recorded (create, update, list with category filter).
      Admin-only.
- [x] `purchases.balance` = `total_cost - amount_paid` (payable semantics open).
- [x] Purchase and expense operations are Admin-only
      (`CAP_MANAGE_PURCHASES_SUPPLIERS`, `CAP_MANAGE_EXPENSES`).
- [x] Full offline operation (no network calls).
- [x] Tests pass (458/458).

## Blockers

- None for Phase 07.

## Open decisions (blocking later phases)

| Decision | Blocks | Open? |
|----------|--------|-------|
| Exchange refund / price-difference under the no-cash rule | Phase 06 (exchanges) | Yes |
| Receipt number prefix/format | Phase 05 (receipts) | Yes — candidate `FUN-YYYYMMDD-NNN` implemented |
| Discount limits and who may discount | Phase 05 (POS) | Partly — Admin-only discount is confirmed |
| Barcode symbology/format (currently candidate: 13-digit numeric → Code128) | Phase 03 (labels) | Yes — candidate pending confirmation |
| Import columns / format (currently documented default template) | Phase 03 (bulk import) | Yes — default implemented, confirmation pending |
| Backup retention / destination | Phase 09 (backup) | Yes — all backups kept; no auto-purge |
| Selected cloud/hybrid package and LAN sync method | Phase 10 (sync) | Yes |
| Deployment topology (single local `.db` vs Admin-hosted LAN FastAPI) | Phase 01 data access + Phase 10 | Yes |
| Receipt barcode content (receipt number exactly?) | Phase 05 (receipt barcode) | Yes — currently the receipt number |
| Expenses scope (all vs selected categories) | Phase 07 (expenses) | Yes — free-text category, no constraint |
| Supplier purchase `balance` semantics (true payable vs record only) | Phase 07 (purchases) | Yes — balance = total_cost - amount_paid |
| Final report list | Phase 08 (reports) | Partially — core reports implemented; export/print format unconfirmed |
| Customer-record management permission | Phase 03 (customers) | Yes — defaulted to Admin-only |
| Inventory management permission (stock/history viewing) | Phase 04 (inventory) | Yes — defaulted to Admin-only |
| Receipt branding/header/footer text | Phase 05 (receipts) | Yes — wireframe candidate implemented |
| Low-stock note shown after a sale | Phase 05 (POS) | Yes — scoped to the sale's own items only |
| ESC/POS naira rendering (₦ → `N`) | Phase 11 (printer) | Yes — `N` used until then |

Details and rationale in `OPEN_DECISIONS.md`.

## Verification / resume notes

On restart:

1. Run `.venv\Scripts\python.exe -m pytest` — expect 533 passing tests.
2. Run the offscreen smoke: `python -m app.main` should show the login dialog
   (offline-safe). Log in with `admin/admin123` (Admin) to see the Dashboard
   (today KPIs + low-stock), POS, Products, Inventory, Customers, Purchases,
   Suppliers, Expenses, Reports, and Settings screens; `cashier/cashier123`
   sees only the POS screen.
3. Inspect `app/domain/services/backup_service.py`,
   `app/ui/settings/settings_page.py` before touching them.
4. Re-read `PROJECT_STATUS.md` and `OPEN_DECISIONS.md` before starting
   Phase 10.
5. Do not proceed to Phase 10 without explicit instruction.
