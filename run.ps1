$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# Use the venv's Python directly so this script works regardless of
# PowerShell execution policy (no Activate.ps1 needed).
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "No venv found. Creating one and installing dependencies..." -ForegroundColor Yellow
    python -m venv .venv
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r requirements.txt
}

& $venvPython -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
