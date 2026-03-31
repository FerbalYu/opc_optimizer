@echo off
chcp 65001 >nul
title OPC Local Optimizer

REM Switch to script directory
cd /d "%~dp0"

REM Check if venv exists
if not exist "venv\Scripts\activate.bat" (
    echo [Error] venv not found!
    echo Please install according to README.md:
    echo 1. python -m venv venv
    echo 2. venv\Scripts\activate
    echo 3. pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

REM Activate venv
call venv\Scripts\activate.bat

REM Start Web UI
echo ===================================================
echo Starting OPC Local Optimizer (Web UI Mode)...
echo ===================================================
echo If 8765/8766 are busy, OPC will automatically switch to the next free port pair.
echo.
python main.py --web-ui %*

pause
