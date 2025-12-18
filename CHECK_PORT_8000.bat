@echo off
REM ============================================================================
REM Check for Multiple uvicorn/Python Processes on Port 8000
REM ============================================================================
REM
REM This script helps diagnose the multiple process issue on Windows
REM Run this to see exactly which processes are using port 8000
REM
REM ============================================================================

setlocal enabledelayedexpansion

echo.
echo ============================================================================
echo Port 8000 Process Diagnostic
echo ============================================================================
echo.

echo [STEP 1] Checking for processes listening on port 8000...
echo.

netstat -ano | findstr ":8000" > nul
if errorlevel 1 (
    echo No processes found on port 8000
    echo [OK] Port 8000 is available
    echo.
    pause
    exit /b 0
)

echo Processes listening on port 8000:
echo.
netstat -ano | findstr ":8000"
echo.

REM Count the matches
for /f %%i in ('netstat -ano ^| findstr ":8000" ^| find /c /v ""') do set count=%%i

echo [STEP 2] Process count: !count! process(es)
echo.

if !count! equ 1 (
    echo [OK] Only 1 process - This is correct
    echo.
    
    REM Extract PID
    for /f "tokens=5" %%i in ('netstat -ano ^| findstr ":8000"') do (
        echo [INFO] PID: %%i
        tasklist /FI "PID eq %%i"
    )
    
    pause
    exit /b 0
) else (
    echo [ERROR] Multiple processes detected: !count!
    echo [ERROR] This is the multiple uvicorn instance problem
    echo.
    echo [ACTION] To fix:
    echo.
    echo Step 1: Kill all Python processes
    echo   taskkill /IM python.exe /F
    echo.
    echo Step 2: Wait 5 seconds
    echo   timeout /t 5
    echo.
    echo Step 3: Verify port is free
    echo   netstat -ano ^| findstr ":8000"
    echo.
    echo Step 4: Start fresh
    echo   START_SERVER.bat
    echo.
)

pause
