# Project Documentation

Layered architecture per `04_Technical_Architecture`:

```
UI  ->  Application Services  ->  Data Access  ->  SQLite
```

- `app/ui` — screens (later phases).
- `app/domain` — business rules, permissions, models, services.
- `app/data` — SQLAlchemy engine, repositories, migrations (Phase 01).
- `app/api` — local FastAPI LAN service (later phase).
- `app/printing`, `app/barcode`, `app/reports`, `app/security`, `app/sync` —
  dedicated service layers (later phases).

Business rules are never placed directly in UI event handlers; UI calls
application services and displays results.
