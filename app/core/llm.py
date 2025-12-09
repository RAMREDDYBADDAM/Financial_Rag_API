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


def _check_ollama_health() -> bool:
    """Check if Ollama is running and accessible.

    This performs a small HTTP probe to the Ollama API. It does not
    instantiate any clients.
    """
    if not OLLAMA_IMPORT_OK or not settings.ollama_enabled:
        return False
    try:
        resp = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=2)
        return resp.status_code == 200
    except Exception:
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


def _create_openai_llm():
    """Create and return a ChatOpenAI instance (langchain-openai).

    Import is lazy to avoid import-time errors when package not installed.
    """
    try:
        from langchain_openai import ChatOpenAI  # type: ignore
    except Exception as e:
        raise RuntimeError("langchain-openai not available") from e

    return ChatOpenAI(model=settings.llm_model, temperature=float(settings.temperature))


def get_llm() -> Any:
    """Lazily return a configured LLM instance (cached).

    Preference order:
      1. Ollama (langchain-ollama)
      2. OpenAI (langchain-openai)
      3. Mock LLM (demo fallback)

    This function never performs heavy work at import time and caches the
    created model for subsequent calls. Creating the model is done only once
    and only when requested.
    """
    global _cached_llm
    if _cached_llm is not None:
        return _cached_llm

    # Try Ollama first
    if settings.ollama_enabled and OLLAMA_IMPORT_OK:
        try:
            _cached_llm = _create_ollama_llm()
            print(f"✅ Using Ollama LLM: {settings.ollama_model}")
            return _cached_llm
        except Exception as e:
            print(f"⚠️ Ollama initialization failed: {e}")

    # Try OpenAI
    if settings.openai_api_key:
        try:
            _cached_llm = _create_openai_llm()
            print(f"✅ Using OpenAI LLM: {settings.llm_model}")
            return _cached_llm
        except Exception as e:
            print(f"⚠️ OpenAI initialization failed: {e}")

    # Fallback mock LLM
    print("⚠️ No LLM backend available, using mock LLM (demo mode)")
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
