@echo off
setlocal
cd /d "%~dp0"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo No venv found. Creating one and installing dependencies...
    python -m venv .venv || goto :error
    "%VENV_PY%" -m pip install --upgrade pip || goto :error
    "%VENV_PY%" -m pip install -r requirements.txt || goto :error
)

"%VENV_PY%" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
goto :eof

:error
echo.
echo Setup failed. See output above.
exit /b 1
