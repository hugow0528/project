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
for /f %%i in ('python -c "import socket; print(socket.gethostbyname(socket.gethostname()))"') do set LAN_IP=%%i
if not defined LAN_IP set LAN_IP=127.0.0.1

echo.
echo Local URL: http://127.0.0.1:%PORT%
if defined LAN_IP echo Same Wi-Fi URL: http://%LAN_IP%:%PORT%
echo.
start "" "http://127.0.0.1:%PORT%"
python app.py
