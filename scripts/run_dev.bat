@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo [funmite] creating virtual environment...
  python -m venv .venv
  echo [funmite] installing dependencies...
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)
echo [funmite] launching Funmite POS...
.venv\Scripts\python.exe -m app.main
