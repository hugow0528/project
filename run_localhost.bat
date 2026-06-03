@echo off
setlocal enabledelayedexpansion
cd /d %~dp0

set VENV_DIR=.venv
set PYTHON_CMD=python
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set PYTHON_CMD=py -3
)

echo ================================================
echo SyncCast Localhost Setup

echo ================================================

if not exist %VENV_DIR% (
    echo Creating virtual environment...
    %PYTHON_CMD% -m venv %VENV_DIR%
    if %ERRORLEVEL% NEQ 0 (
        echo Failed to create virtual environment. Ensure Python 3.10+ is installed.
        pause
        exit /b 1
    )
)

call %VENV_DIR%\Scripts\activate.bat
if %ERRORLEVEL% NEQ 0 (
    echo Failed to activate virtual environment.
    pause
    exit /b 1
)

echo Installing/updating libraries...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo Failed to install dependencies.
    pause
    exit /b 1
)

echo.
for /f "tokens=2 delims=:" %%A in ('ipconfig ^| findstr /c:"IPv4 Address"') do (
    set HOST_IP=%%A
    goto :trim
)
set HOST_IP=127.0.0.1
:trim
set HOST_IP=%HOST_IP: =%

echo Starting server...
echo Local URL: http://127.0.0.1:5000
echo LAN URL  : http://%HOST_IP%:5000
start "" "http://127.0.0.1:5000"

echo Keep this window open while hosting.
python app.py
pause
