# Funmite POS — Admin User Manual

## Getting Started

### Login
1. Launch FunmitePOS.exe
2. Enter your username and password
3. Click Login

### First Time Setup
1. Change the default admin password (Settings > Change Password)
2. Change the default cashier password
3. Add your products with categories
4. Set up barcode labels for products
5. Configure cloud sync if needed (Settings > Cloud Sync)

## Dashboard

The Dashboard shows today's key metrics:
- **Sales** — total sales amount for today
- **Gross Profit** — Sales minus Cost of Goods Sold
- **Net Profit** — Gross Profit minus Expenses
- **Transactions** — number of sales today
- **POS Total** — sales paid via Bank POS
- **Transfer Total** — sales paid via Bank Transfer
- **Low Stock** — products with quantity at or below 3

## Product Management

### Adding a Product
1. Go to Products screen
2. Click Add Product
3. Fill in: Name, Category, Cost Price, Selling Price
4. Product code is auto-generated (PRD-XXXXXX)
5. Barcode is auto-generated (13 digits)
6. Click Save

### Printing Barcode Labels
1. Select a product
2. Click Print Label
3. The barcode label prints with product name and barcode

### Editing a Product
1. Select the product from the list
2. Edit the fields
3. Click Save

## Inventory Management

### Stock-In (Receiving Goods)
1. Go to Inventory screen
2. Click Stock-In
3. Select the product
4. Enter quantity received
5. Enter unit cost (for purchase tracking)
6. Click Confirm

### Stock Adjustment
1. Go to Inventory screen
2. Click Stock Adjustment
3. Select the product
4. Enter the adjustment quantity (positive to add, negative to remove)
5. Enter a reason (required)
6. Click Confirm

### Viewing Stock Levels
- The Inventory screen shows all products with current quantity, cost, and value
- Low stock products are highlighted (quantity ≤ 3)

## Making Sales (Admin)

1. Go to POS screen
2. Scan a barcode or search for a product
3. Select the product — it's added to the cart
4. Adjust quantity if needed
5. Select or create a customer
6. (Optional) Apply discount — Admin only
7. Select payment method: Bank POS or Bank Transfer
8. Enter payment reference
9. Click COMPLETE SALE
10. Receipt prints automatically (if printer is connected)

## Exchanges

1. Go to POS screen
2. Click Exchange (Admin button)
3. Enter the original receipt number
4. Select items to return
5. Add replacement products
6. Review the difference amount
7. Select payment method if additional payment needed
8. Click Complete Exchange

**Note:** Exchanges must be within 2 days of the original sale.

## Purchases & Suppliers

### Adding a Supplier
1. Go to Suppliers screen
2. Click Add Supplier
3. Enter name, phone, address
4. Click Save

### Recording a Purchase
1. Go to Purchases screen
2. Click Create Purchase
3. Select a supplier
4. Add products with quantities and unit costs
5. Enter amount paid
6. Click Complete Purchase
7. Stock is automatically increased

## Expenses

1. Go to Expenses screen
2. Click Add Expense
3. Enter category, amount, description, date
4. Click Save

## Reports

### Available Reports
- **Sales** — receipt-level sales with filters
- **Profit** — Total Sales, COGS, Gross Profit, Expenses, Net Profit
- **Inventory** — current stock levels and values
- **Payments** — POS and Transfer payment totals
- **Purchases** — supplier purchase records
- **Expenses** — recorded expenses by category
- **Product Sales** — per-product sales breakdown
- **Cashier Sales** — per-cashier performance
- **End of Day** — today's complete summary

### Running a Report
1. Go to Reports screen
2. Select a tab
3. Set date range (From / To)
4. Click Run

## Backup & Restore

### Creating a Backup
1. Go to Settings
2. Click Create Backup
3. Backup file appears in the list

### Restoring a Backup
1. Go to Settings
2. Select a backup from the list
3. Click Restore
4. A safety backup of the current database is created automatically
5. The selected backup replaces the current database

**Warning:** Restore replaces the current database. A safety backup is always created first.

## Cloud Sync

### Setting Up
1. Go to Settings > Cloud Sync
2. Enter the cloud database URL
3. Enter a device name
4. Click Register

### Monitoring Sync
- Status bar shows sync indicator (☁ Synced / ☁ N pending / ☁ Offline)
- Click Sync Now to trigger immediate sync
- Pending operations are automatically retried

## Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Focus barcode scan | Auto-focused on POS screen |
| Complete sale | Click COMPLETE SALE button |

## Tips

- Back up regularly — at least daily
- Change default passwords immediately
- Keep the application updated
- If sync shows "pending" for a long time, check internet connection
- Receipt numbers are sequential: FUN-YYYYMMDD-NNN
