"""LLM wiring supporting both Ollama (local) and OpenAI backends.

Priority order:
1. Ollama (if enabled and available at OLLAMA_BASE_URL)
2. OpenAI (if OPENAI_API_KEY is set)
3. Mock LLM (demo fallback)
"""
from typing import Any
import requests
from app.config import settings

# Prefer the official `langchain-ollama` package. It's imported lazily below.
try:
    # New package name: langchain-ollama -> provides `ChatOllama`
    from langchain_ollama import ChatOllama  # type: ignore
    OLLAMA_IMPORT_OK = True
except Exception:
    ChatOllama = None  # type: ignore
    OLLAMA_IMPORT_OK = False


def _check_ollama_health(log: bool = True) -> bool:
    """Check if Ollama is running and accessible.

    This performs a small HTTP probe to the Ollama API. It does not
    instantiate any clients.
    """
    def _log(message: str):
        if log:
            print(message)

    if not OLLAMA_IMPORT_OK:
        _log("[LLM] langchain-ollama package missing. Run: pip install langchain-ollama==0.3.10")
        return False
    if not settings.ollama_enabled:
        _log("[LLM] Ollama disabled in config (OLLAMA_ENABLED=false)")
        return False
    try:
        resp = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=5)
        if resp.status_code == 200:
            # Check if configured model is available
            models = resp.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            
            if any(settings.ollama_model in name for name in model_names):
                _log(f"[LLM] Ollama health check PASSED - model '{settings.ollama_model}' available at {settings.ollama_base_url}")
                return True
            else:
                _log(f"[LLM] Ollama running but model '{settings.ollama_model}' NOT FOUND")
                _log(f"[LLM] Available models: {', '.join(model_names) if model_names else 'none'}")
                _log(f"[LLM] Run: ollama pull {settings.ollama_model}")
                return False
        else:
            _log(f"[LLM] Ollama health check FAILED - HTTP {resp.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        _log(f"[LLM] Ollama NOT REACHABLE at {settings.ollama_base_url}")
        _log("[LLM] Start Ollama: ollama serve")
        return False
    except requests.exceptions.Timeout:
        _log(f"[LLM] Ollama health check TIMEOUT at {settings.ollama_base_url}")
        return False
    except Exception as e:
        _log(f"[LLM] Ollama health check error: {str(e)}")
        return False


_cached_llm = None


def _create_ollama_llm():
    """Create and return a ChatOllama instance using simple kwargs.

    We avoid creating this at import time; callers should use `get_llm()`.
    """
    if not OLLAMA_IMPORT_OK:
        raise RuntimeError("langchain-ollama not installed")

    # Try to construct the ChatOllama client even if the simple health probe
    # failed; some environments may accept connections but not respond to
    # the tags endpoint. The constructor will raise if it's unusable.
    try:
        return ChatOllama(model=settings.ollama_model, temperature=float(settings.temperature), base_url=settings.ollama_base_url)  # type: ignore
    except Exception as e:
        # Re-raise to allow caller to fallback gracefully
        raise RuntimeError(f"Failed to instantiate ChatOllama: {e}") from e

# ❌ OpenAI support removed - using local Ollama instead (free, no API keys needed)
# def _create_openai_llm():
#     """Create and return a ChatOpenAI instance (langchain-openai).
#
#     Import is lazy to avoid import-time errors when package not installed.
#     """
#     try:
#         from langchain_openai import ChatOpenAI  # type: ignore
#     except Exception as e:
#         raise RuntimeError("langchain-openai not available") from e
#
#     return ChatOpenAI(model=settings.llm_model, temperature=float(settings.temperature))


def get_llm() -> Any:
    """Lazily return a configured LLM instance (cached).

    Preference order (Ollama-only setup):
      1. Ollama (langchain-ollama) - LOCAL, FREE, NO API KEYS
      2. Mock LLM (demo fallback) - only if Ollama unavailable

    This function never performs heavy work at import time and caches the
    created model for subsequent calls. Creating the model is done only once
    and only when requested.
    """
    global _cached_llm
    if _cached_llm is not None:
        return _cached_llm

    # Try Ollama (primary, local, free LLM) with health check first
    if settings.ollama_enabled and OLLAMA_IMPORT_OK and _check_ollama_health():
        try:
            _cached_llm = _create_ollama_llm()
            print(f"[LLM] Using Ollama LLM: {settings.ollama_model} at {settings.ollama_base_url}")
            print("[LLM] Ollama integration ACTIVE (local, free, no API keys)")
            return _cached_llm
        except Exception as e:
            print(f"[LLM] Failed to initialize Ollama: {str(e)}")
            print("[LLM] Falling back to mock LLM")

    # Fallback mock LLM (demo mode only)
    print("[LLM] Ollama unavailable - using MOCK LLM (demo mode)")
    print("[LLM] To use Ollama: 1) ollama serve, 2) ollama pull mistral")
    from app.core.mock_llm import get_mock_llm
    _cached_llm = get_mock_llm()
    return _cached_llm


import anyio


async def call_llm(messages_or_prompt: Any) -> Any:
    """Safely invoke the underlying LLM in a thread to avoid blocking the event loop.

    Accepts either a prompt string or a messages structure depending on the
    consumer. The low-level LLM invocation is run in a worker thread using
    anyio.to_thread.run_sync.
    """
    llm = get_llm()

    def _invoke(arg):
        # Try a few common interfaces
        try:
            if hasattr(llm, "invoke"):
                # many local/community LLMs expose .invoke(prompt)
                return llm.invoke(arg)
            if hasattr(llm, "__call__"):
                return llm(arg)
            # Last resort
            return llm
        except Exception:
            raise

    # Run blocking call in worker thread
    return await anyio.to_thread.run_sync(_invoke, messages_or_prompt)
