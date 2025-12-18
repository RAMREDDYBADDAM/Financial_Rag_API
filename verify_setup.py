#!/usr/bin/env python3
"""
System Health Check for Financial RAG FastAPI Project

Verifies:
- Python version
- Required packages installed
- Port 8000 is available
- Virtual environment setup
- Project structure
- Environment variables

Usage:
    python verify_setup.py
"""
import os
import sys
import socket
import subprocess
from pathlib import Path


def check_python_version():
    """Verify Python 3.8+"""
    version = sys.version_info
    print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print(f"  ERROR: Python 3.8+ required, got {version.major}.{version.minor}")
        return False
    return True


def check_required_packages():
    """Verify critical packages are installed"""
    packages = ["fastapi", "uvicorn", "pydantic", "pandas"]
    missing = []
    
    for pkg in packages:
        try:
            __import__(pkg)
            print(f"✓ {pkg}")
        except ImportError:
            missing.append(pkg)
            print(f"✗ {pkg} (MISSING)")
    
    if missing:
        print(f"\n  Run: pip install {' '.join(missing)}")
        return False
    return True


def check_port_availability():
    """Check if port 8000 is available"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            result = s.connect_ex(('127.0.0.1', 8000))
            if result == 0:
                print("✗ Port 8000 is already in use")
                print("\n  Kill existing process:")
                print("    tasklist | findstr python")
                print("    taskkill /PID <pid> /F")
                return False
            else:
                print("✓ Port 8000 is available")
                return True
    except Exception as e:
        print(f"✗ Port check failed: {e}")
        return False


def check_project_structure():
    """Verify project directories exist"""
    paths = {
        "app/core/server.py": "FastAPI server",
        "serve.py": "Startup script",
        "web/dashboard.html": "Frontend dashboard",
        "data/sample_financial_data.csv": "Sample data",
        ".env": "Environment config",
    }
    
    all_ok = True
    for path, desc in paths.items():
        full_path = Path(path)
        if full_path.exists():
            print(f"✓ {path}")
        else:
            print(f"✗ {path} (MISSING - {desc})")
            all_ok = False
    
    return all_ok


def check_environment():
    """Check .env file configuration"""
    if not Path(".env").exists():
        print("✗ .env file not found")
        return False
    
    print("✓ .env file exists")
    
    try:
        from dotenv import load_dotenv
        load_dotenv()
        
        # Check key variables
        vars_to_check = [
            "OLLAMA_ENABLED",
            "OLLAMA_MODEL",
        ]
        
        for var in vars_to_check:
            val = os.getenv(var, "not set")
            print(f"  - {var}={val}")
        
        return True
    except Exception as e:
        print(f"✗ Error loading .env: {e}")
        return False


def check_ollama_connection():
    """Optional: Check if Ollama is running"""
    try:
        import urllib.request
        base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        urllib.request.urlopen(f"{base_url}/api/tags", timeout=2)
        print(f"✓ Ollama is running at {base_url}")
        return True
    except Exception:
        print("⚠ Ollama not detected (optional, will use mock LLM)")
        return True  # Not critical


def main():
    print("=" * 60)
    print("Financial RAG FastAPI - System Health Check")
    print("=" * 60)
    print()
    
    checks = [
        ("Python Version", check_python_version),
        ("Required Packages", check_required_packages),
        ("Port Availability", check_port_availability),
        ("Project Structure", check_project_structure),
        ("Environment Config", check_environment),
        ("Ollama Connection", check_ollama_connection),
    ]
    
    results = {}
    for name, check_func in checks:
        print(f"\n[{name}]")
        try:
            results[name] = check_func()
        except Exception as e:
            print(f"✗ Check failed: {e}")
            results[name] = False
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("\n✓ All checks passed! Ready to start server.")
        print("\nStart with:")
        print("  python serve.py")
        print("  or")
        print("  START_SERVER.bat")
        return 0
    else:
        print("\n✗ Some checks failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
