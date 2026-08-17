# Funmite POS

Desktop POS for **Funmite Clothing & Beyond** (Kano). Offline-first, Windows,
two roles (ADMIN / CASHIER), payments limited to POS and TRANSFER, generated
product barcodes, receipt barcodes, two-day exchanges, and low-stock alerts.

This is the implementation project. The full specification pack lives in the
parent folder (`00_START_HERE.md` onward). See `OPEN_DECISIONS.md` for
unresolved client decisions.

## Status

**Phase 09 (Backup & Recovery) — complete.** Phases 00 (Foundation), 01
(Database), 02 (Authentication & Authorization), 03 (Products, Customers &
Barcodes), 04 (Inventory), 05 (POS Sales), 06 (Exchanges), 07 (Purchases,
Suppliers & Expenses) and 08 (Reports & Dashboard) are also complete.

Implemented so far:

- Phase 00: project skeleton per the approved architecture
  (`04_Technical_Architecture`), Python venv + `requirements.txt`, configuration
  (`app/config.py`, `.env.example`, no secrets), logging (console + rotating file),
  minimal application shell, pytest + pytest-qt framework.
- Phase 01: SQLAlchemy 2.0 models for all 16 tables from the approved schema
  (`funmite_production_candidate.sql`), SQLite pragmas (`foreign_keys=ON`,
  busy timeout), session/transaction helpers, a custom lightweight migration
  runner (no Alembic), idempotent seed users, PBKDF2 password hashing, and
  repositories (`app/data/repositories/`).
- Phase 02: login dialog + logout flow, session/current-user handling, the
  role-based permission catalog (Admin/Cashier from the use-case matrix),
  service-level authorization, and audit logging (`audit_logs` table via
  migration 002) for sensitive actions.
- Phase 03: the product catalogue (Admin CRUD, categories, search/filter),
  unique system-generated product barcodes (13-digit numeric + Luhn check
  digit, rendered as Code128), printer-independent SVG barcode labels,
  USB-scanner input handling, bulk product import (validated CSV), customer
  registration, and Admin-only Products/Customers screens.
- Phase 04: the inventory service (stock-in, adjustment, movement history,
  low-stock detection at `quantity <= 3`), the Admin Inventory screen
  (Current Stock / Stock In / Adjust / Movement / Low Stock), the Admin
  Dashboard with the low-stock indicator, and the low-stock popup/notification.
- Phase 05: the atomic offline sale. The POS screen (Cashier and Admin) scans
  or searches products into a cart, requires a customer (or registers a quick
  walk-in), lets the Admin apply a PERCENT/FIXED discount, takes Bank POS or
  Bank Transfer payment only (no cash/credit), and completes the sale as one
  transaction that also deducts stock through the shared inventory service. A
  receipt with a Code128 receipt-number barcode renders and prints through a
  printer abstraction (no hardware needed yet); printing failure never loses a
  sale,   and the Admin can reprint (UC-06).
- Phase 06: the exchange screen (Admin only, `CAP_EXCHANGE`). From the POS
  screen the Admin clicks "Exchange..." to open a modal dialog; they look up
  the original sale by receipt number, select which item(s) to return (with
  quantity), search and add a replacement product (with quantity), review the
  live price difference, and confirm. When the replacement costs more, Bank POS
  or Bank Transfer payment is required; when it costs the same, the exchange is
  flat. Items returned go back into stock; replacements are deducted. The
  original sale is never modified. The 2-day window and the over-exchange rule
  are enforced. When the customer would be owed money, the exchange is refused
  until the settlement method is confirmed (see `OPEN_DECISIONS.md`). All
  exchange writes go through the shared inventory service with
  `CAP_EXCHANGE`.
- Phase 07: the back-office stock and expense workflows. The Admin can record
  a supplier (name, phone, address) and manage suppliers from a dedicated
  screen. Purchases are recorded atomically: select a supplier, add product
  lines (product, quantity, unit cost), set the amount paid, and complete.
  The transaction increases stock through the shared inventory service, updates
  each product's current cost price to the latest purchase unit cost, and
  records the purchase header and items (historical unit cost). The balance
  is `total_cost - amount_paid` (whether this is a true payable is an open
  decision). Expenses are recorded with a free-text category, amount, optional
  description and date, and are later used for net-profit reporting. All
  purchase and expense operations are Admin-only (`CAP_MANAGE_PURCHASES_SUPPLIERS`
  and `CAP_MANAGE_EXPENSES`). Purchases, Suppliers and Expenses screens are
  in the Admin sidebar.
- Phase 08: the reporting dashboard and report screens. The Admin dashboard
  shows today's KPIs — sales, gross profit, net profit, transaction count,
  POS total, transfer total — above the low-stock indicator. The Reports
  screen provides tab-based access to Sales, Profit, Inventory, Payments,
  Purchases, Expenses, Product Sales, Cashier Sales, and End of Day reports.
  All reports accept a date-range filter. Profit uses historical
  `sale_items.cost_price`. Cashier is restricted to own daily sales
  (`CAP_VIEW_OWN_SALES`); profit views are Admin-only (`CAP_VIEW_PROFIT`).
  Reports are read-only aggregation queries over the local database — fully
  offline.
- Phase 09: offline local backup and restore. The Admin can create safe
  SQLite backups from the Settings screen using `sqlite3.Connection.backup()`.
  Backups are stored as `funmite_YYYYMMDD_HHMMSS_MICROSECONDS.db` in the
  configured backup directory (`FUNMITE_BACKUP_DIR`). The Admin can list all
  backups (sorted newest-first), validate them, and restore from any backup.
  Restore always creates a pre-restore safety backup first, validates integrity
  after restore, and rolls back on integrity failure. All backup/restore
  actions are audit-logged. Cashier cannot access backup/restore functions
  (`CAP_BACKUP`, `CAP_RESTORE` are Admin-only).

Phases 10–12 remain; see `00_START_HERE.md` for sequencing. Do not jump phases.

### Phase 05 highlights

- `SaleService.complete_sale` is the only way a sale is written. It commits the
  header (receipt number `FUN-YYYYMMDD-NNN`), the item lines (historical cost),
  the payment row (only when the total is positive) and per-line stock
  deduction through `InventoryService.change_stock` in one atomic transaction —
  a mid-sale stock shortage rolls the whole thing back.
- Payments are validated: only `POS` and `TRANSFER` (as `BANK POS` / `BANK
  TRANSFER` in the UI) are accepted; cash, credit and split payments are
  rejected in the domain layer, not just hidden in the UI.
- Discounts are Admin-only (`CAP_DISCOUNT`) with `PERCENT` or `FIXED` types and
  can never make the total negative.
- Printing is decoupled from POS logic: `ReceiptData` is a detached dataclass,
  the ESC/POS renderer is pure Python (80mm thermal printer, Code128 barcode,
  ₦ rendered as `N` on paper), and `NullPrinter` is the default until the
  physical printer ships in Phase 11. The Cashier nav shows only the POS screen;
  the Admin nav is Dashboard, POS, Products, Inventory, Customers.

### Phase 04 highlights

- Every stock change goes through `InventoryService` and writes a complete
  `inventory_logs` row: product, previous quantity, change, new quantity,
  reason, user, timestamp, and a reference type/id where a related transaction
  exists. Nothing silently modifies `Product.quantity`.
- Stock-in is Admin-only (`CAP_STOCK_IN`); adjustment is Admin-only
  (`CAP_STOCK_ADJUSTMENT`) and requires a reason. Changes that would push stock
  below zero are rejected in the service layer (the DB CHECK constraint is the
  final guard).
- The shared `change_stock` movement writer is what Phase 05 sales and Phase 06
  exchanges will consume with their own capabilities, so sales/exchanges reuse
  the same inventory logic.
- Low stock is `quantity <= 3` (`LOW_STOCK_THRESHOLD`): it shows on the Admin
  Dashboard and in the Inventory screen's Low Stock tab, and a
  popup/notification appears after a stock change that leaves a product low.
- The Inventory screen mirrors the approved wireframe sections: Current Stock
  (with LOW/OK status), Stock In, Adjust, Movement (newest-first audit trail,
  filterable by product), and Low Stock.

### Phase 09 highlights

- Backup uses Python's `sqlite3.Connection.backup()` for safe online backup
  (no file copy of an in-use database). Restore replaces the live database
  and validates integrity with `PRAGMA integrity_check`.
- A pre-restore safety backup is always created before any restore, so the
  current database state is never silently lost.
- The Settings page (Admin sidebar) provides the backup/restore UI with
  backup listing, creation, and restore with confirmation dialog.
- All backup/restore actions are audit-logged via `AuditService`.

### Phase 03 highlights

- Every new product gets a unique barcode: a 13-digit value (12-digit sequence
  + Luhn check digit) generated above the largest existing barcode, unique per
  batch and guarded by the database `UNIQUE` constraint. Blank product codes
  become `PRD-######`; blank customer codes `CUS-#####`.
- A USB barcode scanner behaves like a keyboard — the `BarcodeScanInput`
  widget emits `barcode_scanned` on Enter and resets for the next scan. On the
  Products screen a scan selects the matching row; the shared service
  `lookup_by_barcode` is ready for the POS screen (Phase 05).
- Barcode labels are exported as printer-independent SVG files (Code128 +
  product name/price) from the Products screen; physical label printing is
  Phase 11.
- Bulk import validates every row first, reports per-row errors, skips invalid
  rows, and imports valid rows atomically in one transaction. Duplicate codes
  or barcodes (in the file or the database) are reported and never overwritten.
- Product/category/customer management is Admin-only and enforced in the
  domain layer; Cashier still shares barcode scan + catalogue search
  (`CAP_SCAN_BARCODE`).

### Phase 02 highlights

- Login uses the seed `admin`/`cashier` accounts (hashed with PBKDF2). Wrong
  credentials and disabled accounts fail with the same generic message, and
  every login success/failure/logout is recorded in `audit_logs`.
- Authorization is enforced in the domain layer
  (`app/domain/permissions/`), never only by hiding UI controls, so a Cashier
  cannot execute Admin operations even if the UI is bypassed.
- The permission catalog mirrors the matrix in `02_Use_Cases_Workflows`
  (e.g. discount, exchanges, price changes, stock adjustment, users,
  backup/restore, expenses, purchases/suppliers and profit are Admin-only).

### Phase 01 highlights

- Money is `Numeric(12, 2)` backed by `Decimal` (no float arithmetic).
- Timestamps are naive, shop-local datetimes (single location, no DST).
- CHECK constraints are generated from the same constants the app uses
  (roles, payment methods, discount types, exchange types, sync statuses), so
  the database can never store a value the app does not know about.
- Low stock is `quantity <= 3` (`LOW_STOCK_THRESHOLD`); default minimum stock 3.
- Password hashes use PBKDF2-HMAC-SHA256 from the standard library
  (format `pbkdf2_sha256$<iterations>$<salt_hex>$<digest_hex>`).
- The login screen and the signed-in user/role display are implemented; the
  business screens (products, POS, inventory, reports, ...) are later phases.

## Requirements

- Python 3.11 or newer (developed against 3.12).
- Windows (target platform). PySide6 works on other OSes too.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
```

Optional: copy `.env.example` to `.env` and adjust paths/log level.

## Run

```powershell
python -m app.main
```

or double-click `scripts\run_dev.bat`.

## Test

```powershell
pytest
```

## Project structure

```
app/
  main.py            # entry point + login/logout lifecycle + nav (Phases 02–05)
  config.py          # settings loaded from env / .env
  logging_config.py  # console + rotating file logging
  ui/                # screens; login, dashboard, pos, products, customers, inventory
  domain/            # errors, session, services, rules, permissions
  data/              # SQLAlchemy layer, repositories, migrations
  barcode/           # barcode generation, labels, scanner input (Phase 03)
  printing/          # receipt data + ESC/POS renderer + printer abstraction (Phase 05)
  api/               # local FastAPI service (later phase)
  sync/ reports/ security/ utils/   # service layers
tests/               # pytest suite
scripts/             # development helpers
docs/                # project documentation
```

Business screens (exchanges, reports, ...) are later phases.
