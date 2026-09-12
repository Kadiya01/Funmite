# Render web process for the Funmite cloud sync service (Phase 2 M3 hosting).
# The platform injects the managed PostgreSQL URL as FUNMITE_CLOUD_DB_URL
# (see render.yaml) or DATABASE_URL; both are honoured by the app settings.
web: python -m uvicorn app.sync.cloud_api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1