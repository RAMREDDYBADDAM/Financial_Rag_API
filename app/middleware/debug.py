"""
Debug Middleware and Timing Decorators
======================================
Comprehensive request/response logging and performance profiling for development.

Features:
- Full request/response body logging (with sensitive field masking)
- X-Debug-Info header with execution details
- Timing decorators for function profiling
- Request ID tracking for distributed tracing
- Configurable via DEBUG environment variable

Usage:
    from app.middleware.debug import DebugMiddleware, timed
    
    app.add_middleware(DebugMiddleware)
    
    @timed("my_function")
    def my_function():
        ...
"""

import json
import time
import uuid
import logging
from typing import Callable, Any, Optional
from functools import wraps
from datetime import datetime
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from fastapi import FastAPI

from app.config import settings

logger = logging.getLogger(__name__)

# Context variable for request ID tracking across async boundaries
request_id_context: ContextVar[str] = ContextVar("request_id", default="")
debug_context: ContextVar[dict] = ContextVar("debug_context", default={})


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def sanitize_sensitive_data(data: dict) -> dict:
    """
    Mask sensitive fields in request/response data.
    
    Args:
        data: Dict potentially containing sensitive data
    
    Returns:
        Dict with sensitive fields masked
    """
    sensitive_fields = {
        "api_key",
        "apikey",
        "password",
        "token",
        "secret",
        "authorization",
        "openai_api_key",
    }
    
    if not isinstance(data, dict):
        return data
    
    sanitized = {}
    for key, value in data.items():
        key_lower = key.lower()
        if any(field in key_lower for field in sensitive_fields):
            sanitized[key] = "***MASKED***"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_sensitive_data(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_sensitive_data(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value
    
    return sanitized


def get_request_id() -> str:
    """
    Get current request ID from context.
    
    Returns:
        str: Request ID or empty string if not set
    """
    return request_id_context.get()


def set_debug_info(key: str, value: Any) -> None:
    """
    Set debug information for current request.
    
    Args:
        key: Debug info key
        value: Debug info value
    """
    context = debug_context.get().copy()
    context[key] = value
    debug_context.set(context)


def get_debug_info() -> dict:
    """
    Get all debug information for current request.
    
    Returns:
        Dict with debug information
    """
    return debug_context.get().copy()


# ============================================================================
# MIDDLEWARE
# ============================================================================


class DebugMiddleware(BaseHTTPMiddleware):
    """
    Debug middleware for request/response logging and profiling.
    
    Only active when DEBUG=true in environment configuration.
    Logs full request/response details and adds X-Debug-Info header.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with debug logging.
        
        Args:
            request: Incoming request
            call_next: Next middleware/handler
        
        Returns:
            Response with X-Debug-Info header
        """
        # Skip if debug mode disabled
        if not settings.debug:
            return await call_next(request)
        
        # Generate request ID
        request_id = str(uuid.uuid4())
        request_id_context.set(request_id)
        
        # Initialize debug context
        debug_info = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "query_params": dict(request.query_params),
            "timestamp": datetime.utcnow().isoformat(),
            "timings": {},
        }
        debug_context.set(debug_info)
        
        # Log request
        start_time = time.time()
        logger.debug(f"[{request_id}] {request.method} {request.url.path}")
        
        # Read and log request body (if present)
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                if body:
                    try:
                        body_json = json.loads(body)
                        sanitized_body = sanitize_sensitive_data(body_json)
                        logger.debug(
                            f"[{request_id}] Request Body: {json.dumps(sanitized_body, indent=2)}"
                        )
                        debug_info["request_body"] = sanitized_body
                    except json.JSONDecodeError:
                        logger.debug(f"[{request_id}] Request Body: <non-JSON data>")
                        debug_info["request_body"] = "<non-JSON>"
                
                # Reconstruct request with body for next middleware
                async def receive():
                    return {"type": "http.request", "body": body}
                
                request._receive = receive
            except Exception as e:
                logger.warning(f"[{request_id}] Failed to read request body: {e}")
        
        # Process request
        response = await call_next(request)
        
        # Calculate total time
        total_time = time.time() - start_time
        debug_info["timings"]["total_ms"] = round(total_time * 1000, 2)
        
        # Log response
        logger.debug(
            f"[{request_id}] Response: {response.status_code} "
            f"({debug_info['timings']['total_ms']}ms)"
        )
        
        # Add debug info to response header
        if settings.debug:
            debug_summary = {
                "request_id": request_id,
                "processing_time_ms": debug_info["timings"]["total_ms"],
                **get_debug_info(),
            }
            
            # Remove large nested objects for header
            debug_summary.pop("request_body", None)
            
            response.headers["X-Debug-Info"] = json.dumps(debug_summary)
        
        return response


# ============================================================================
# TIMING DECORATORS
# ============================================================================


def timed(operation_name: str, log_args: bool = False):
    """
    Decorator to time function execution and add to debug context.
    
    Args:
        operation_name: Name for timing entry
        log_args: Whether to log function arguments
    
    Example:
        @timed("classify_query")
        def classify_query(question: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not settings.debug:
                # Skip timing overhead in production
                return await func(*args, **kwargs)
            
            request_id = get_request_id()
            start = time.time()
            
            if log_args:
                logger.debug(
                    f"[{request_id}] {operation_name} called with args={args}, kwargs={kwargs}"
                )
            
            try:
                result = await func(*args, **kwargs)
                duration_ms = round((time.time() - start) * 1000, 2)
                
                # Add timing to debug context
                set_debug_info(f"timing_{operation_name}", duration_ms)
                
                logger.debug(f"[{request_id}] {operation_name} completed in {duration_ms}ms")
                return result
            except Exception as e:
                duration_ms = round((time.time() - start) * 1000, 2)
                logger.error(
                    f"[{request_id}] {operation_name} failed after {duration_ms}ms: {e}"
                )
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not settings.debug:
                return func(*args, **kwargs)
            
            request_id = get_request_id()
            start = time.time()
            
            if log_args:
                logger.debug(
                    f"[{request_id}] {operation_name} called with args={args}, kwargs={kwargs}"
                )
            
            try:
                result = func(*args, **kwargs)
                duration_ms = round((time.time() - start) * 1000, 2)
                
                set_debug_info(f"timing_{operation_name}", duration_ms)
                
                logger.debug(f"[{request_id}] {operation_name} completed in {duration_ms}ms")
                return result
            except Exception as e:
                duration_ms = round((time.time() - start) * 1000, 2)
                logger.error(
                    f"[{request_id}] {operation_name} failed after {duration_ms}ms: {e}"
                )
                raise
        
        # Return appropriate wrapper
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def log_execution_time(func: Callable) -> Callable:
    """
    Simple timing decorator that always logs (no debug check).
    
    Args:
        func: Function to time
    
    Returns:
        Wrapped function with timing
    
    Example:
        @log_execution_time
        def expensive_operation():
            ...
    """
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        start = time.time()
        result = await func(*args, **kwargs)
        duration = time.time() - start
        logger.info(f"{func.__name__} took {duration:.3f}s")
        return result
    
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start
        logger.info(f"{func.__name__} took {duration:.3f}s")
        return result
    
    import inspect
    if inspect.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper


# ============================================================================
# PROFILING CONTEXT MANAGER
# ============================================================================


class ProfileBlock:
    """
    Context manager for profiling code blocks.
    
    Example:
        with ProfileBlock("database_query"):
            result = await db.query(...)
    """
    
    def __init__(self, name: str):
        """
        Initialize profiling block.
        
        Args:
            name: Name for this profiling block
        """
        self.name = name
        self.start_time = None
    
    def __enter__(self):
        """Start timing."""
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop timing and log."""
        if self.start_time:
            duration_ms = round((time.time() - self.start_time) * 1000, 2)
            if settings.debug:
                request_id = get_request_id()
                logger.debug(f"[{request_id}] Block '{self.name}' took {duration_ms}ms")
                set_debug_info(f"block_{self.name}", duration_ms)
