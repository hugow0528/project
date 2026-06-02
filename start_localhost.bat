@echo off
setlocal EnableDelayedExpansion

REM Portable launcher: run from USB folder root.
cd /d "%~dp0"

if not exist ".venv" (
    echo [1/4] Creating virtual environment...
    py -3 -m venv .venv
)

echo [2/4] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [3/4] Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo [4/4] Starting local server...
set PORT=8000

echo.
echo Local URL: http://127.0.0.1:%PORT%
echo Same Wi-Fi URL will be shown by app.py after startup.
echo.
start "" "http://127.0.0.1:%PORT%"
python app.py
