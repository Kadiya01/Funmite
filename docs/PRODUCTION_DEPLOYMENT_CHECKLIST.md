# Funmite POS — Production Deployment Checklist

**Version:** 1.2.0
**Date:** _______________
**Deployed by:** _______________

---

## 1. PC Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| OS | Windows 10 64-bit | Windows 11 64-bit |
| RAM | 4 GB | 8 GB |
| Disk | 500 MB + data growth | 1 GB + data growth |
| Screen | 1280×720 | 1920×1080 |
| USB | 2 ports | 2 ports |

---

## 2. Installation Procedure

### Step 1: Copy Application
```
Copy the entire FunmitePOS/ folder to:
C:\FunmitePOS\
```

### Step 2: Verify Files
```
C:\FunmitePOS\
├── FunmitePOS.exe
├── data/           (created on first launch)
├── logs/           (created on first launch)
└── backups/        (created on first launch)
```

### Step 3: Create Configuration (Optional)
Create `.env` in `C:\FunmitePOS\`:
```
FUNMITE_LOG_LEVEL=WARNING
FUNMITE_CLOUD_SYNC=true
FUNMITE_CLOUD_DB_URL=postgresql://user:password@host/funmite_cloud
```

### Step 4: First Launch
1. Double-click `FunmitePOS.exe`
2. Wait for first launch (5-10 seconds)
3. Login dialog appears

---

## 3. Directory Locations

| Item | Default Location | Configure Via |
|------|------------------|---------------|
| Database | `C:\FunmitePOS\data\funmite.db` | `FUNMITE_DATA_DIR` |
| Logs | `C:\FunmitePOS\logs\funmite.log` | `FUNMITE_LOG_DIR` |
| Backups | `C:\FunmitePOS\backups\` | `FUNMITE_BACKUP_DIR` |
| Config | `C:\FunmitePOS\.env` | — |
| Sync credentials | `C:\FunmitePOS\data\sync_credentials.json` | — |

---

## 4. Hardware Setup

### 4.1 Barcode Scanner
1. Connect USB barcode scanner
2. Scanner should be in keyboard (HID) mode
3. Test in Notepad — scanning should type characters
4. No driver installation required for HID mode

### 4.2 Thermal Receipt Printer
1. Connect 80mm thermal printer via USB
2. Install printer driver (from manufacturer)
3. Verify in Windows Settings > Devices > Printers
4. Set as default printer (optional)

---

## 5. Admin Setup

### Step 1: Login
- Username: `admin`
- Password: `admin123` (CHANGE IMMEDIATELY)

### Step 2: Change Password
1. Go to Settings
2. Change admin password to a strong password
3. Document the new password securely

### Step 3: Create Cashier Account
1. The cashier account is pre-created (`cashier` / `cashier123`)
2. Change the cashier password
3. Or create a new cashier account

### Step 4: Add Categories
1. Go to Products > Categories
2. Add product categories (e.g., "Clothing", "Accessories")

### Step 5: Add Products
1. Go to Products
2. Add products with names, categories, prices
3. Barcodes are auto-generated
4. Print barcode labels

### Step 6: Test Hardware
1. Test barcode scanner on POS screen
2. Test receipt printer with a test sale

---

## 6. Cashier Setup

### Step 1: Login
- Username: `cashier`
- Password: (set by Admin)

### Step 2: Verify Access
- Cashier should only see POS screen
- No access to Products, Inventory, Reports, etc.

### Step 3: Test Sale
1. Scan a barcode
2. Select a customer
3. Complete a sale with POS or Transfer payment
4. Verify receipt prints

---

## 7. Cloud Registration

### Step 1: Register Admin PC
1. Open Settings > Cloud Sync
2. Enter cloud database URL
3. Enter device name: "Admin PC"
4. Click Register
5. Verify status shows device ID

### Step 2: Register Cashier PC
1. Open Settings > Cloud Sync
2. Enter same cloud database URL
3. Enter device name: "Cashier PC"
4. Click Register
5. Verify status shows device ID

### Step 3: Test Sync
1. Create a product on Admin PC
2. Click Sync Now
3. On Cashier PC, click Sync Now
4. Verify product appears

---

## 8. Network Requirements

| Requirement | Details |
|-------------|---------|
| Internet | Required for cloud sync only |
| Offline | Application works fully offline |
| Bandwidth | Minimal (small JSON payloads) |
| Firewall | No special configuration needed |
| Ports | None (outbound HTTP/HTTPS only) |

---

## 9. Offline Operation

The application is designed to work without internet:

1. All POS operations work offline
2. Sales are saved locally
3. Inventory changes are local
4. Reports use local data
5. Backups work offline
6. When internet returns, pending sync is automatic

---

## 10. Backup Procedure

### Daily Backup
1. Open Settings
2. Click Create Backup
3. Backup file appears in list
4. Copy backup to USB drive (recommended)

### Backup Location
Default: `C:\FunmitePOS\backups\`
Files: `funmite_YYYYMMDD_HHMMSS_<8hex>.db`

### Restore Procedure
1. Open Settings
2. Select backup from list
3. Click Restore
4. Pre-restore backup is created automatically
5. Database is replaced with backup

---

## 11. Recovery Procedure

### Database Corruption
1. Close the application
2. Open Settings > Restore
3. Select a recent backup
4. Click Restore
5. If no backup exists, delete `data/funmite.db` and restart (loses all data)

### Application Won't Start
1. Check `logs/funmite.log` for errors
2. Try running as Administrator
3. Reinstall from the distribution folder

### Printer Issues
1. Check printer is powered on
2. Check Windows printer settings
3. Reinstall printer driver
4. Sale is saved even if printing fails — reprint from Admin

---

## 12. Update Procedure

1. Back up the current installation
2. Copy the new `FunmitePOS/` folder
3. The database (`data/funmite.db`) is preserved
4. Launch and verify

---

## 13. Support Procedure

### For Issues
1. Check `docs/TROUBLESHOOTING.md`
2. Check `logs/funmite.log`
3. Contact developer with error details

### Information to Provide
- Windows version
- Error message (if any)
- Steps to reproduce
- `logs/funmite.log` contents

---

## 14. Security Checklist

- [ ] Default admin password changed
- [ ] Default cashier password changed
- [ ] `.env` file does not contain plaintext passwords
- [ ] Cloud credentials are in `data/sync_credentials.json` (not in source)
- [ ] Backups are stored securely
- [ ] Application runs with standard user privileges (not Administrator)

---

## 15. Sign-Off

| Item | Verified | Initials | Date |
|------|----------|----------|------|
| Application installed | | | |
| Database initialized | | | |
| Admin login works | | | |
| Cashier login works | | | |
| Barcode scanner works | | | |
| Receipt printer works | | | |
| Backup created | | | |
| Cloud sync registered | | | |
| Passwords changed | | | |
| Documentation handed over | | | |

**Deployed by:** _______________
**Date:** _______________
