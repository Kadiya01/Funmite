# Funmite POS — Production Deployment Checklist

Version: 1.1.0 (Phase 10 complete)
Date: August 2026

## 1. Pre-Deployment Preparation

### 1.1 Build Verification
- [ ] Run full regression suite: `.venv\Scripts\python.exe -m pytest` — 657 tests passing
- [ ] Build executable: `.venv\Scripts\python.exe -m PyInstaller funmite_pos.spec --noconfirm`
- [ ] Verify `dist/FunmitePOS/FunmitePOS.exe` exists
- [ ] Launch exe and confirm login dialog appears
- [ ] Log in as `admin/admin123` — Dashboard should load
- [ ] Log in as `cashier/cashier123` — POS screen should load

### 1.2 Data Persistence Verification
- [ ] After first launch, verify `data/`, `logs/`, `backups/` created next to exe
- [ ] Verify `data/funmite.db` exists (SQLite database)
- [ ] Create a backup from Settings — verify file appears in `backups/`
- [ ] Check `logs/funmite.log` for any errors

### 1.3 Configuration
- [ ] Create `.env` file next to exe with production settings:
  ```
  FUNMITE_LOG_LEVEL=WARNING
  FUNMITE_CLOUD_SYNC=true
  ```
- [ ] Verify `.env` is read correctly (check log level changes)

## 2. Installation on Target Machine

### 2.1 Copy Files
- [ ] Copy the entire `dist/FunmitePOS/` folder to target PC
  - Recommended location: `C:\FunmitePOS\`
- [ ] Ensure the target PC runs Windows 10 or later (64-bit)
- [ ] Ensure the target PC has a screen resolution of at least 1280×720

### 2.2 First Launch
- [ ] Double-click `FunmitePOS.exe`
- [ ] Login dialog should appear (may take 5-10 seconds on first launch)
- [ ] Log in as `admin/admin123`
- [ ] Dashboard loads with zero data
- [ ] Seed users (admin, cashier) are created automatically

### 2.3 Verify All Screens
- [ ] Dashboard — KPI widgets visible (all zero)
- [ ] POS — Barcode scan field, product search, cart visible
- [ ] Products — Product list (empty)
- [ ] Inventory — Current Stock (empty)
- [ ] Customers — Customer list (empty)
- [ ] Purchases — Purchase list (empty)
- [ ] Suppliers — Supplier list (empty)
- [ ] Expenses — Expense list (empty)
- [ ] Reports — All tabs accessible
- [ ] Settings — Backup section + Cloud Sync section visible

## 3. Barcode Scanner Test

### 3.1 Setup
- [ ] Connect USB barcode scanner
- [ ] Scanner should appear as a keyboard input device (HID mode)
- [ ] Open POS screen

### 3.2 Test Scan
- [ ] Scan a product barcode — product should appear in search results
- [ ] If no product exists, scan should show "not found" gracefully
- [ ] Create a test product with a barcode, then scan it — should add to cart
- [ ] Verify scanner input is cleared after scan (ready for next scan)
- [ ] Verify rapid consecutive scans don't corrupt input

## 4. Thermal Receipt Printer Test

### 4.1 Setup
- [ ] Connect 80mm thermal receipt printer via USB
- [ ] Install printer driver on Windows
- [ ] Verify printer appears in Windows Devices and Printers

### 4.2 Test Print
- [ ] Complete a test sale
- [ ] Receipt should print with:
  - [ ] Shop name "Funmite Clothing & Beyond"
  - [ ] Receipt number `FUN-YYYYMMDD-NNN`
  - [ ] Product name, quantity, price
  - [ ] Subtotal, discount (if any), total
  - [ ] Payment method
  - [ ] Barcode at bottom (receipt number encoded as Code128)
  - [ ] Naira sign rendered as `N` (PC437 limitation)
- [ ] Verify paper feeds and cuts correctly
- [ ] Test reprint from Settings (Admin only)

## 5. Two-PC Synchronization Test

### 5.1 Setup
- [ ] Copy `FunmitePOS/` to both PC-A (Admin) and PC-B (Cashier)
- [ ] Both PCs should be on the same local network
- [ ] Cloud PostgreSQL database is accessible from both PCs

### 5.2 Register Devices
- [ ] On PC-A: Settings > Cloud Sync > Enter cloud URL > Register
- [ ] On PC-A: Verify status shows "Registered" or device ID
- [ ] On PC-B: Settings > Cloud Sync > Enter cloud URL > Register
- [ ] On PC-B: Verify status shows "Registered" or device ID

### 5.3 Test Push (PC-A → Cloud)
- [ ] On PC-A: Create a category "Test Cat"
- [ ] On PC-A: Click "Sync Now" in Settings
- [ ] Verify status shows pending count decreases
- [ ] Verify cloud database has the category

### 5.4 Test Pull (Cloud → PC-B)
- [ ] On PC-B: Click "Sync Now" in Settings
- [ ] Verify the category "Test Cat" appears on PC-B
- [ ] Verify category data is identical on both PCs

### 5.5 Test Conflict Resolution
- [ ] On PC-A: Update category name to "Cat A"
- [ ] On PC-B: Update category name to "Cat B"
- [ ] Sync both PCs
- [ ] Last write should win (both PCs should show the same final name)

### 5.6 Test Append-Only Records
- [ ] On PC-A: Complete a sale
- [ ] On PC-B: Complete a different sale
- [ ] Sync both PCs
- [ ] Verify both sales appear on both PCs (no conflict, both preserved)

### 5.7 Test User Records
- [ ] Verify user accounts are NOT synced to cloud
- [ ] Each PC has its own local user database

## 6. Offline Operation Test

### 6.1 Disconnect Internet
- [ ] Unplug network cable / disable WiFi on both PCs
- [ ] Verify the app still launches and shows login
- [ ] Verify POS screen is fully functional (no "offline" error)

### 6.2 Offline Sales
- [ ] On PC-A: Complete 3 sales (different products)
- [ ] On PC-B: Complete 2 sales
- [ ] Verify all sales are saved locally
- [ ] Verify receipt numbers are sequential on each PC

### 6.3 Offline Inventory
- [ ] On PC-A: Do a stock-in (10 units of a product)
- [ ] On PC-B: Do a stock adjustment (-2 units of same product)
- [ ] Verify inventory quantities are correct on each PC independently

### 6.4 Offline Reports
- [ ] On PC-A: Run Sales report — shows only PC-A's sales
- [ ] On PC-B: Run Sales report — shows only PC-B's sales
- [ ] Reports work correctly with local data only

### 6.5 Offline Backup
- [ ] On PC-A: Create backup from Settings
- [ ] Verify backup file is created in `backups/`

## 7. Reconnection & Sync Verification

### 7.1 Reconnect Internet
- [ ] Reconnect network cable / enable WiFi on both PCs
- [ ] Wait 30 seconds for automatic sync (or click Sync Now)

### 7.2 Verify Sync
- [ ] On PC-A: Check pending count is 0
- [ ] On PC-B: Check pending count is 0
- [ ] Sync status shows green "Synced"

### 7.3 Verify Data Consistency
- [ ] PC-A shows all 5 sales (3 from PC-A + 2 from PC-B)
- [ ] PC-B shows all 5 sales (3 from PC-A + 2 from PC-B)
- [ ] Inventory on PC-A reflects combined stock changes
- [ ] Inventory on PC-B reflects combined stock changes
- [ ] No duplicate transactions
- [ ] No lost transactions

### 7.4 Verify Receipt Numbers
- [ ] Receipt numbers on PC-A start with `FUN-YYYYMMDD-NNN`
- [ ] Receipt numbers on PC-B start with `FUN-YYYYMMDD-NNN`
- [ ] No duplicate receipt numbers across PCs

## 8. Security Verification

- [ ] Cashier cannot access Admin screens (Products, Inventory, etc.)
- [ ] Cashier cannot create backups
- [ ] Cashier cannot register devices for cloud sync
- [ ] Passwords are not stored in plaintext in the database
- [ ] Failed logins are logged in the audit trail
- [ ] `.env` file does not contain production secrets

## 9. Final Cleanup

- [ ] Remove test data created during deployment testing
- [ ] Verify default admin password is changed for production
- [ ] Verify default cashier password is changed for production
- [ ] Document the final configuration (cloud URL, sync intervals)
- [ ] Hand over deployment documentation to client

## 10. Known Issues & Limitations

| Issue | Status | Impact |
|-------|--------|--------|
| Receipt numbers use `FUN-` prefix (no device prefix) | By design | Low — each PC has unique daily sequences, DB UNIQUE constraint prevents collision |
| Backup filenames use UUID suffix | By design | None — ensures uniqueness even with rapid creation |
| Thermal printer renders ₦ as `N` | PC437 limitation | Low — on-screen text keeps ₦ |
| Cloud sync interval is 30s push / 60s pull | Configurable via `.env` | None |
| No encryption on local backups | Open decision | Medium — confirm with client |
| Users are not synced across PCs | By design | Expected — each PC has its own user database |
