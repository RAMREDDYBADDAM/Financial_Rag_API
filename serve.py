"""Serve helper for the Financial RAG project.

WINDOWS FIX: This script uses subprocess to invoke CLI uvicorn instead of
uvicorn.run() to prevent multiple worker processes from binding to port 8000.

Features:
- Loads `.env` automatically
- Checks for existing instances (safety guard)
- Optional `--ingest` flag to call the ingestion pipeline before serving
- CLI-based uvicorn invocation (prevents worker forking on Windows)

Usage examples:
  # start normally (recommended - no reload on Windows)
  python serve.py

  # start with reload (use with caution on Windows)
  python serve.py --reload --port 8000

  # run ingestion then start
  python serve.py --ingest

NOTE: On Windows, uvicorn --reload can spawn multiple processes. This script
      detects existing instances and fails fast to prevent the issue.
"""
from __future__ import annotations

import argparse
import logging
import os
import socket
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run the Financial RAG FastAPI app")
    p.add_argument("--host", default="127.0.0.1", help="Host to bind (default 127.0.0.1)")
    p.add_argument("--port", type=int, default=8000, help="Port to bind (default 8000)")
    p.add_argument("--reload", action="store_true", help="Enable uvicorn reload (NOT recommended on Windows)")
    p.add_argument("--ingest", action="store_true", help="Run document ingestion before starting the server")
    p.add_argument("--raw-docs", default="./data/raw_docs", help="Path to raw documents for ingestion")
    return p


def _check_port_in_use(port: int) -> bool:
    """Check if a port is already in use. Returns True if in use."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            result = s.connect_ex(('127.0.0.1', port))
            return result == 0  # 0 = connection succeeded (port in use)
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # Load .env if present
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger(__name__)

    # SAFETY GUARD: Fail if port already in use (prevents multiple uvicorn instances)
    if _check_port_in_use(args.port):
        logger.error("FATAL: Port %d is already in use. Kill existing process first:", args.port)
        logger.error("  tasklist | findstr python")
        logger.error("  taskkill /PID <pid> /F")
        return 1

    if args.ingest:
        logger.info("Running document ingestion from %s", args.raw_docs)
        try:
            from app.ingestion.ingestion_docs import ingest_documents
            ingest_documents(args.raw_docs)
            logger.info("Ingestion finished")
        except Exception as e:
            logger.exception("Ingestion failed: %s", e)
            return 2

    # WINDOWS FIX: Use subprocess with CLI uvicorn instead of uvicorn.run()
    # This prevents multiple processes from forking on Windows.
    try:
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "app.core.server:app",
            "--host", args.host,
            "--port", str(args.port),
            "--log-level", "info",
        ]
        
        if args.reload:
            cmd.append("--reload")
        
        pid = os.getpid()
        logger.info("=" * 60)
        logger.info("[STARTUP] FastAPI Server Starting (PID: %d)", pid)
        logger.info("[STARTUP] Command: %s", " ".join(cmd))
        logger.info("[STARTUP] Listening: http://%s:%d", args.host, args.port)
        logger.info("=" * 60)
        
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except Exception as e:
        logger.exception("Failed to start server: %s", e)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
