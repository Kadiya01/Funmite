# Funmite POS

Desktop POS for **Funmite Clothing & Beyond** (Kano). Offline-first, Windows,
two roles (ADMIN / CASHIER), payments limited to POS and TRANSFER, generated
product barcodes, receipt barcodes, two-day exchanges, and low-stock alerts.

This is the implementation project. The full specification pack lives in the
parent folder (`00_START_HERE.md` onward). See `OPEN_DECISIONS.md` for
unresolved client decisions.

## Status

**Phase 00 (Foundation) — complete.**

Implemented so far:

- Project skeleton per the approved architecture (`04_Technical_Architecture`).
- Python virtual environment and dependency management (`requirements.txt`).
- Configuration handling (`app/config.py`, `.env.example`, no secrets).
- Logging setup (console + rotating file in `logs/`).
- Minimal application shell window (no business features).
- Testing framework (pytest + pytest-qt).
- `README.md`, `CHANGELOG.md`, `OPEN_DECISIONS.md`, `docs/`.

Phases 01–12 remain; see `00_START_HERE.md` for sequencing. Do not jump phases.

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
  main.py            # entry point, minimal application shell
  config.py          # settings loaded from env / .env
  logging_config.py  # console + rotating file logging
  ui/                # screens (later phases)
  domain/            # models, services, rules, permissions
  data/              # SQLAlchemy layer, repositories, migrations (Phase 01)
  api/               # local FastAPI service (later phase)
  sync/ printing/ barcode/ reports/ security/ utils/   # placeholders
tests/               # pytest suite
scripts/             # development helpers
docs/                # project documentation
```

No business features are implemented yet.
