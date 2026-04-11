@echo off
:: =============================================================
::  NWS RADAR — TRAFFIC CAMERA FEED TERMINAL LAUNCHER
::  Double-click this file to start the camera monitor.
::
::  Requirements: Python 3.8+ installed and on PATH
::                (https://www.python.org/downloads/)
::
::  Options (edit below):
::    INTERVAL  — seconds between scans (default: 30)
::    STATE     — limit to one state code: NY, VA, IA, or ALL
::    OPEN_HTML — open index.html in browser when starting
::    LOG_FILE  — path to log file (leave blank to skip)
:: =============================================================
setlocal EnableDelayedExpansion

:: ── User-configurable options ────────────────────────────────
set INTERVAL=30
set STATE=ALL
set OPEN_HTML=1
set LOG_FILE=camera_terminal.log

:: ── Derived paths ────────────────────────────────────────────
:: Script lives next to index.html and camera_terminal.py
set SCRIPT_DIR=%~dp0
set PY_SCRIPT=%SCRIPT_DIR%camera_terminal.py

:: ── Window appearance ────────────────────────────────────────
title NWS Radar — Camera Feed Terminal
color 0A

:: ── Header ──────────────────────────────────────────────────
echo.
echo  =======================================================
echo   NWS RADAR -- TRAFFIC CAMERA FEED TERMINAL
echo  =======================================================
echo   Interval : %INTERVAL%s
echo   State    : %STATE%
echo   Log      : %LOG_FILE%
echo   Script   : %PY_SCRIPT%
echo  =======================================================
echo.

:: ── Python check ────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python not found on PATH.
    echo  Please install Python 3.8+ from https://www.python.org/
    echo  and make sure "Add Python to PATH" is checked during install.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%V in ('python --version 2^>^&1') do set PY_VER=%%V
echo  [SYS] Python %PY_VER% found.

:: ── Script check ────────────────────────────────────────────
if not exist "%PY_SCRIPT%" (
    echo  [ERROR] camera_terminal.py not found at:
    echo          %PY_SCRIPT%
    echo  Make sure this .bat file is in the same folder as camera_terminal.py
    echo.
    pause
    exit /b 1
)

:: ── Build argument string ────────────────────────────────────
set ARGS=--interval %INTERVAL%

if not "%STATE%"=="ALL" (
    set ARGS=%ARGS% --state %STATE%
)

if not "%LOG_FILE%"=="" (
    set ARGS=%ARGS% --log "%SCRIPT_DIR%%LOG_FILE%"
)

if "%OPEN_HTML%"=="1" (
    if exist "%HTML_FILE%" (
        set ARGS=%ARGS% --open
    )
)

:: ── Launch ──────────────────────────────────────────────────
echo  [SYS] Starting camera terminal...
echo  [SYS] Args: %ARGS%
echo  [SYS] Press Ctrl+C to stop.
echo.

python "%PY_SCRIPT%" %ARGS%

:: ── Exit handler ────────────────────────────────────────────
echo.
echo  [SYS] Camera terminal exited (code %errorlevel%).
echo.
pause
exit /b %errorlevel%
