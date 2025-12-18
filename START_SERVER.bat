@echo off
REM ============================================================================
REM Windows Server Startup Script - Financial RAG FastAPI
REM ============================================================================
REM
REM This batch file starts the FastAPI server on Windows with proper safeguards
REM to prevent multiple uvicorn instances from binding to port 8000.
REM
REM WHAT THIS DOES:
REM 1. Checks if Python is available
REM 2. Checks if port 8000 is already in use (safety guard)
REM 3. Activates virtual environment (if exists)
REM 4. Runs serve.py which uses CLI uvicorn (not uvicorn.run)
REM
REM ============================================================================

setlocal enabledelayedexpansion

echo.
echo ============================================================================
echo Financial RAG FastAPI - Windows Startup
echo ============================================================================
echo.

REM Check for Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not available in PATH
    echo [ERROR] Please install Python or add it to your PATH
    pause
    exit /b 1
)

REM Check if venv exists and activate it
if exist "venv\Scripts\activate.bat" (
    echo [SETUP] Activating virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo [WARNING] Virtual environment not found at venv\Scripts\activate.bat
    echo [WARNING] Assuming Python packages are installed globally
)

REM Check if port 8000 is in use (safety guard)
echo [CHECK] Verifying port 8000 is available...
netstat -ano | findstr ":8000" >nul
if not errorlevel 1 (
    echo.
    echo [FATAL] Port 8000 is already in use!
    echo [FATAL] A server instance may already be running.
    echo.
    echo [HELP] To find and kill the existing process:
    echo   1. Run: tasklist | findstr python
    echo   2. Find the PID with port 8000
    echo   3. Kill it: taskkill /PID ^<pid^> /F
    echo.
    pause
    exit /b 1
)

echo [OK] Port 8000 is available
echo.

REM Start the server using serve.py
echo ============================================================================
echo [STARTUP] Starting Financial RAG FastAPI Server
echo [STARTUP] Command: python serve.py
echo ============================================================================
echo.

python serve.py %*

echo.
echo [SHUTDOWN] Server stopped
pause
