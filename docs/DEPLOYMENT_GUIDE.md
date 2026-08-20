# Funmite POS — Deployment Guide

## System Requirements

- **OS:** Windows 10 or later (64-bit)
- **RAM:** 4 GB minimum, 8 GB recommended
- **Disk:** 500 MB for application + space for database growth
- **Screen:** 1280×720 minimum resolution
- **USB:** 2 free USB ports (barcode scanner + receipt printer)

## Installation

### Step 1: Copy the Application
Copy the entire `dist/FunmitePOS/` folder to the target PC:
```
C:\FunmitePOS\
```

### Step 2: Create Configuration (Optional)
Create a `.env` file in `C:\FunmitePOS\`:
```
FUNMITE_LOG_LEVEL=WARNING
```

### Step 3: Connect Hardware
1. Connect the USB barcode scanner
2. Connect the 80mm thermal receipt printer
3. Install the printer driver if needed

### Step 4: First Launch
1. Double-click `FunmitePOS.exe`
2. Wait for first launch (may take 5-10 seconds)
3. Login dialog appears
4. Default credentials: `admin` / `admin123`

### Step 5: Initial Setup
1. Change the admin password immediately
2. Change the cashier password
3. Add products with barcodes
4. Test the barcode scanner
5. Test the receipt printer
6. Create a backup

## Network Setup (For Sync)

### Cloud Sync
1. Ensure both PCs have internet access
2. On each PC: Settings > Cloud Sync > Register
3. Enter the cloud database URL and device name
4. Click Register

### Verification
1. Create a test product on PC-A
2. Click Sync Now on PC-A
3. Click Sync Now on PC-B
4. Verify the product appears on PC-B

## Backup Strategy

### Recommended
- Create a backup at the end of each business day
- Store backups on a USB drive or network location
- Keep at least 7 days of backups

### Backup Location
Default: `C:\FunmitePOS\backups\`
Configure: Set `FUNMITE_BACKUP_DIR` in `.env`

## Updating

1. Back up the current installation
2. Copy the new `dist/FunmitePOS/` folder
3. The database (`data/funmite.db`) is preserved
4. Launch and verify

## Uninstalling

1. Back up the database (`data/funmite.db`)
2. Delete the `C:\FunmitePOS\` folder
3. Delete any shortcuts

## Support

- Check `docs/TROUBLESHOOTING.md` for common issues
- Contact the development team for critical issues
