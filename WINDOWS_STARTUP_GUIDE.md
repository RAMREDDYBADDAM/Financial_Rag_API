# FastAPI Server Startup Guide - Windows

## Overview
This project uses FastAPI with uvicorn. On Windows, special care is needed to prevent multiple uvicorn processes from binding to the same port (port 8000).

## Quick Start

### Option 1: Simple Batch File (RECOMMENDED)
```cmd
START_SERVER.bat
```
- Double-click or run from cmd
- Automatically checks port availability
- Activates virtual environment
- Logs all startup info

### Option 2: Direct Python
```bash
python serve.py
```
- Uses CLI-based uvicorn (not `uvicorn.run()`)
- Includes port check and safety guards
- Logs PID at startup

### Option 3: Direct uvicorn CLI
```bash
uvicorn app.core.server:app --host 127.0.0.1 --port 8000
```

## Important: The Windows Issue (SOLVED)

**Problem**: Calling `uvicorn.run()` with `--reload` on Windows can spawn multiple worker processes, all binding to port 8000.

**Root Cause**: 
- `uvicorn.run()` uses Python's multiprocessing module
- On Windows, multiprocessing spawns new Python interpreters (not fork)
- With reload enabled, multiple processes end up listening on the same port

**Solution**:
- `serve.py` now uses `subprocess.run()` with CLI uvicorn instead of `uvicorn.run()`
- Pre-startup port check prevents launching if port already in use
- PID logging at startup helps identify which process is running

## Files Changed

### `serve.py` (FIXED)
**Before**: Used `uvicorn.run()` directly
```python
uvicorn.run("app.core.server:app", host=args.host, port=args.port, reload=args.reload)
```

**After**: Uses subprocess + CLI uvicorn + port check
```python
# Check port is free first
if _check_port_in_use(args.port):
    logger.error("FATAL: Port %d is already in use", args.port)
    return 1

# Run uvicorn as subprocess (CLI-based)
cmd = [sys.executable, "-m", "uvicorn", "app.core.server:app", ...]
result = subprocess.run(cmd, check=False)
```

**Why this works**:
- CLI invocation doesn't use multiprocessing on Windows
- Single process binds to port (no worker forking)
- Port check prevents accidental duplicate launches

### `app/core/server.py` (ENHANCED)
**Added**:
- Docstring explaining Windows safety precautions
- PID logging in startup event
- Clear instructions for killing stuck processes
- Timestamp of when server started

## Troubleshooting

### Issue: "Address already in use" or multiple processes on port 8000

**Symptoms**:
```
Address already in use
netstat shows multiple LISTENING on :8000
```

**Solution**:
```cmd
REM Find all Python processes
tasklist | findstr python

REM Kill by PID (example: 12345)
taskkill /PID 12345 /F

REM Verify port is free
netstat -ano | findstr :8000

REM Retry startup
START_SERVER.bat
```

### Issue: "Python is not available in PATH"

**Solution**:
```cmd
REM Option 1: Add Python to PATH (permanent)
setx PATH "%PATH%;C:\Python311"

REM Option 2: Use full path to Python
C:\Python311\python.exe serve.py

REM Option 3: Use virtual environment
venv\Scripts\python.exe serve.py
```

### Issue: "Cannot import app"

**Solution**:
```cmd
REM Make sure you're in the project root directory
cd c:\Users\ramre\OneDrive\Desktop\project LangChain

REM Verify project structure
dir app\core\server.py

REM Run from project root only
python serve.py
```

### Issue: Server starts but port doesn't respond

**Symptoms**:
- Server shows "Uvicorn running on http://127.0.0.1:8000"
- But curl/browser can't connect

**Solution**:
```cmd
REM Check if server is actually listening
netstat -ano | findstr :8000

REM If nothing appears, port binding failed
REM Check server output for errors

REM If port shows LISTENING:
REM Check firewall (Windows Defender)
REM Firewall > Allow an app > Find Python > Check boxes
```

### Issue: Multiple "Uvicorn running" messages

**Symptoms**:
```
[STARTUP] Starting Financial RAG FastAPI Server
Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

**Root Cause**: Reload is enabled and worker processes are spawning

**Solution**:
```cmd
REM Kill all instances
taskkill /IM python.exe /F

REM Wait 5 seconds
timeout /t 5

REM Start without reload (recommended on Windows)
python serve.py
```

## Safety Guards Implemented

### Port Check Before Startup
```python
def _check_port_in_use(port: int) -> bool:
    """Returns True if port is already in use"""
    with socket.socket() as s:
        return s.connect_ex(('127.0.0.1', port)) == 0
```

If port is in use, `serve.py` exits with error code 1 and helpful message.

### PID Logging at Startup
```
[STARTUP] Process ID: 12345 - THIS IS THE ONLY PROCESS THAT SHOULD EXIST
```

You can verify only one process is running:
```cmd
tasklist /FI "PID eq 12345"
```

### CLI-based uvicorn (No multiprocessing)
By using `subprocess.run()` with `python -m uvicorn` instead of `uvicorn.run()`, we avoid Windows' multiprocessing issues entirely.

## Testing the Fix

### Verify Single Process Startup
```cmd
REM Terminal 1: Start server
START_SERVER.bat

REM Terminal 2: Check port
netstat -ano | findstr :8000
```

Expected output:
```
TCP    127.0.0.1:8000         0.0.0.0:0              LISTENING       12345
```

**Only ONE line** should appear. If you see multiple PIDs, the fix didn't work.

### Test API Endpoints
```cmd
REM In a separate terminal
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/dashboard
```

Expected output:
```json
{"status":"ok"}
```

## Performance Notes

- **No reload mode** (default): Fastest, most stable, best for production
- **With reload** (`--reload` flag): Slower startup, may cause issues on Windows, only for development
- **Multiprocessing**: Completely avoided - all processing single-threaded via FastAPI's async model

## Environment Variables

Set in `.env`:
```
OLLAMA_ENABLED=true
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=mistral
LLM_TEMPERATURE=0.7
VECTOR_DB_DIR=./data/vectorstore
KMP_DUPLICATE_LIB_OK=TRUE
OMP_NUM_THREADS=4
```

## Files Reference

- `serve.py` - Main startup script with port guard and subprocess wrapper
- `START_SERVER.bat` - Windows batch file wrapper
- `app/core/server.py` - FastAPI app with PID logging
- `.env` - Environment configuration (required)

## Summary: What Changed

| File | Change | Why |
|------|--------|-----|
| `serve.py` | Replaced `uvicorn.run()` with `subprocess.run()` + CLI | Prevents worker forking on Windows |
| `serve.py` | Added `_check_port_in_use()` function | Fail-fast if port already in use |
| `app/core/server.py` | Added PID logging to startup event | Easy debugging of multiple processes |
| `START_SERVER.bat` | New file | User-friendly Windows startup |

## Contact / Support

If you see multiple uvicorn processes:
1. Run: `taskkill /IM python.exe /F`
2. Wait 5 seconds
3. Try: `START_SERVER.bat`
4. Check: `netstat -ano | findstr :8000` (should show only one PID)
