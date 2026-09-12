@echo off
REM Funmite cloud sync server launcher (Phase 2 - M1).
REM
REM Starts the FastAPI cloud service that POS devices push/pull against.
REM The single implementation is app.sync.cloud_api (create_app / app).
REM
REM Configuration (optional environment variables):
REM   FUNMITE_CLOUD_DB_URL   Cloud database URL.
REM                          Default: sqlite:///cloud.db  (dev/test).
REM                          Production PostgreSQL provisioning is
REM                          Phase 2 M2/M3 - see docs/CLOUD_SERVER.md.
REM   FUNMITE_API_HOST       Bind host.  Default: 127.0.0.1
REM   FUNMITE_API_PORT       Bind port.  Default: 8000
REM
REM Example:
REM   set FUNMITE_CLOUD_DB_URL=sqlite:///cloud.db
REM   scripts\run_cloud_server.bat

setlocal
cd /d "%~dp0.."

if not defined FUNMITE_API_HOST set FUNMITE_API_HOST=127.0.0.1
if not defined FUNMITE_API_PORT set FUNMITE_API_PORT=8000

echo Starting Funmite cloud server on %FUNMITE_API_HOST%:%FUNMITE_API_PORT%
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m uvicorn app.sync.cloud_api:app --host %FUNMITE_API_HOST% --port %FUNMITE_API_PORT%
) else (
    python -m uvicorn app.sync.cloud_api:app --host %FUNMITE_API_HOST% --port %FUNMITE_API_PORT%
)

endlocal