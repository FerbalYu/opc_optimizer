@echo off
chcp 65001 >nul
title OPC Kill Occupied Web UI Ports
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

set "PORTS=8765 8766 8767 8768 8769 8770"
set "FOUND_ANY=0"

echo ===================================================
echo Cleaning occupied OPC Web UI ports...
echo Target ports: %PORTS%
echo Only python.exe processes will be terminated.
echo ===================================================
echo.

for %%P in (%PORTS%) do (
    for /f "tokens=5" %%I in ('netstat -ano ^| findstr /R /C:":%%P .*LISTENING"') do (
        set "FOUND_ANY=1"
        set "PID=%%I"
        set "PROCNAME="
        for /f "tokens=1,*" %%A in ('tasklist /FI "PID eq !PID!" /FO CSV /NH') do (
            set "PROCNAME=%%~A"
        )

        if /I "!PROCNAME!"=="python.exe" (
            echo [KILL] Port %%P - PID !PID! - !PROCNAME!
            taskkill /PID !PID! /F >nul 2>&1
            if errorlevel 1 (
                echo        Failed to terminate PID !PID!
            ) else (
                echo        Terminated successfully.
            )
        ) else (
            if defined PROCNAME (
                echo [SKIP] Port %%P - PID !PID! - !PROCNAME!
            ) else (
                echo [SKIP] Port %%P - PID !PID! - unknown process
            )
        )
        echo.
    )
)

if "%FOUND_ANY%"=="0" (
    echo No listeners found on the target ports.
    echo.
)

echo Done.
pause
