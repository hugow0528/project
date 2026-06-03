@echo off
setlocal EnableDelayedExpansion

REM Portable launcher: run from USB folder root.
cd /d "%~dp0"

set "PYTHON_CMD="
where py >nul 2>nul
if %errorlevel%==0 set "PYTHON_CMD=py -3"

if not defined PYTHON_CMD (
    where python >nul 2>nul
    if %errorlevel%==0 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    echo Python 3 was not found.
    echo Please install Python 3 and enable PATH (or py launcher).
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [1/4] Creating virtual environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo [2/4] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [3/4] Installing dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo [4/4] Starting local server...
if not defined PORT set PORT=8000

echo.
echo Local URL: http://127.0.0.1:%PORT%
echo Same Wi-Fi URL will be shown by app.py after startup.
echo.
start "" "http://127.0.0.1:%PORT%"
python app.py
