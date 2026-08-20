# Funmite POS — Production Configuration Guide

## Overview

Funmite POS reads configuration from environment variables and an optional `.env` file located next to the executable (or project root in development).

## Configuration File

Create a `.env` file in the application directory:

```
# Log level: DEBUG, INFO, WARNING, ERROR
FUNMITE_LOG_LEVEL=WARNING

# Cloud sync (set to true to enable)
FUNMITE_CLOUD_SYNC=true
FUNMITE_CLOUD_DB_URL=postgresql://user:password@host/funmite_cloud

# Sync intervals (seconds)
FUNMITE_SYNC_PUSH_INTERVAL=30
FUNMITE_SYNC_PULL_INTERVAL=60

# Custom paths (optional — defaults are relative to executable)
# FUNMITE_DATA_DIR=C:\FunmitePOS\data
# FUNMITE_LOG_DIR=C:\FunmitePOS\logs
# FUNMITE_BACKUP_DIR=C:\FunmitePOS\backups

# Development seed overrides (optional)
# FUNMITE_SEED_ADMIN_PASSWORD=your_admin_password
# FUNMITE_SEED_CASHIER_PASSWORD=your_cashier_password
```

## Required Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| None | — | Application runs with defaults for offline use |

## Optional Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `FUNMITE_LOG_LEVEL` | `INFO` | Logging verbosity |
| `FUNMITE_DATA_DIR` | `./data` | Database storage location |
| `FUNMITE_LOG_DIR` | `./logs` | Log file location |
| `FUNMITE_BACKUP_DIR` | `./backups` | Backup file location |
| `FUNMITE_API_HOST` | `127.0.0.1` | Local API host |
| `FUNMITE_API_PORT` | `8000` | Local API port |

## Cloud Sync Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `FUNMITE_CLOUD_SYNC` | `false` | Enable cloud sync |
| `FUNMITE_CLOUD_DB_URL` | `sqlite:///cloud.db` | Cloud database URL |
| `FUNMITE_SYNC_PUSH_INTERVAL` | `30` | Seconds between push attempts |
| `FUNMITE_SYNC_PULL_INTERVAL` | `60` | Seconds between pull attempts |

## Development vs Production

| Aspect | Development | Production |
|--------|-------------|------------|
| Database | `data/funmite.db` (auto-created) | Same |
| Seed users | Created automatically with defaults | Created with env var overrides |
| Log level | `INFO` | `WARNING` |
| Cloud sync | Disabled | Enabled after registration |
| Backup | Manual from Settings | Manual from Settings |

## First Launch Behavior

1. Application creates `data/`, `logs/`, `backups/` directories
2. `data/funmite.db` is created with the full schema via migrations
3. Seed users are created if they don't exist:
   - `admin` / `admin123` (or `FUNMITE_SEED_ADMIN_PASSWORD`)
   - `cashier` / `cashier123` (or `FUNMITE_SEED_CASHIER_PASSWORD`)
4. A warning is logged: "Seeded development accounts with default passwords"

## Security Notes

- Default passwords must be changed before production use
- Cloud credentials are stored in `data/sync_credentials.json` (runtime-generated)
- Never commit `.env` files with real credentials to source control
- Backups are not encrypted (open decision — confirm with client)

## Device Registration

For cloud sync, each PC must be registered:

1. Open Settings > Cloud Sync
2. Enter the cloud database URL
3. Enter a device name (e.g., "Admin PC" or "Cashier PC")
4. Click Register
5. Credentials are saved to `data/sync_credentials.json`

## Directory Structure (Production)

```
C:\FunmitePOS\
├── FunmitePOS.exe
├── .env                    (optional configuration)
├── data/
│   ├── funmite.db          (main database)
│   └── sync_credentials.json (cloud sync credentials)
├── logs/
│   └── funmite.log
└── backups/
    └── funmite_YYYYMMDD_HHMMSS_<8hex>.db
```
