"""
Prometheus Metrics for Production Monitoring
============================================
Comprehensive metrics collection for FastAPI application performance tracking.

Metrics Categories:
- HTTP Request metrics (count, duration, status codes)
- LLM usage tracking (provider, model, tokens)
- Cache performance (hits, misses, evictions)
- Background task monitoring
- System resource utilization

Integration:
- Use metrics_middleware() for automatic HTTP tracking
- Call instrument_llm_call() in LLM invocation paths
- Call track_cache_operation() in cache access paths
- Expose via /metrics endpoint for Prometheus scraping
"""

from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
)
from functools import wraps
from typing import Callable, Any, Optional
from datetime import datetime
import time
import logging

logger = logging.getLogger(__name__)

# ============================================================================
# METRICS REGISTRY
# ============================================================================

# Use default registry for global metrics
registry = CollectorRegistry()

# ============================================================================
# HTTP REQUEST METRICS
# ============================================================================

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests received",
    ["method", "endpoint", "status_code"],
    registry=registry,
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=registry,
)

http_requests_in_progress = Gauge(
    "http_requests_in_progress",
    "Number of HTTP requests currently being processed",
    ["method", "endpoint"],
    registry=registry,
)

# ============================================================================
# LLM METRICS
# ============================================================================

llm_requests_total = Counter(
    "llm_requests_total",
    "Total LLM API requests",
    ["provider", "model", "status"],
    registry=registry,
)

llm_request_duration_seconds = Histogram(
    "llm_request_duration_seconds",
    "LLM request latency in seconds",
    ["provider", "model"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
    registry=registry,
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total tokens processed by LLM",
    ["provider", "model", "token_type"],
    registry=registry,
)

# ============================================================================
# CACHE METRICS
# ============================================================================

cache_operations_total = Counter(
    "cache_operations_total",
    "Total cache operations",
    ["operation", "cache_name", "result"],
    registry=registry,
)

cache_hit_ratio = Gauge(
    "cache_hit_ratio",
    "Cache hit ratio (hits / total operations)",
    ["cache_name"],
    registry=registry,
)

cache_size_bytes = Gauge(
    "cache_size_bytes",
    "Current cache size in bytes",
    ["cache_name"],
    registry=registry,
)

# ============================================================================
# QUERY PROCESSING METRICS
# ============================================================================

query_processing_duration_seconds = Histogram(
    "query_processing_duration_seconds",
    "Query processing latency by type",
    ["query_type"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
    registry=registry,
)

query_classification_total = Counter(
    "query_classification_total",
    "Total queries classified",
    ["query_type"],
    registry=registry,
)

# ============================================================================
# BACKGROUND TASK METRICS
# ============================================================================

background_tasks_total = Counter(
    "background_tasks_total",
    "Total background tasks created",
    ["task_type", "status"],
    registry=registry,
)

background_tasks_duration_seconds = Histogram(
    "background_tasks_duration_seconds",
    "Background task execution time",
    ["task_type"],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 300.0),
    registry=registry,
)

background_tasks_in_queue = Gauge(
    "background_tasks_in_queue",
    "Number of background tasks in queue by status",
    ["status"],
    registry=registry,
)

# ============================================================================
# DATA SOURCE METRICS
# ============================================================================

data_source_requests_total = Counter(
    "data_source_requests_total",
    "Requests to data sources",
    ["source", "status"],
    registry=registry,
)

vectorstore_queries_total = Counter(
    "vectorstore_queries_total",
    "Vector store query count",
    ["operation"],
    registry=registry,
)

# ============================================================================
# INSTRUMENTATION HELPERS
# ============================================================================


def track_http_request(method: str, endpoint: str, status_code: int, duration: float):
    """
    Track HTTP request metrics.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: Endpoint path
        status_code: HTTP status code
        duration: Request duration in seconds
    """
    http_requests_total.labels(
        method=method,
        endpoint=endpoint,
        status_code=status_code
    ).inc()
    
    http_request_duration_seconds.labels(
        method=method,
        endpoint=endpoint
    ).observe(duration)


def track_llm_call(
    provider: str,
    model: str,
    status: str,
    duration: float,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
):
    """
    Track LLM API call metrics.
    
    Args:
        provider: LLM provider (openai, ollama, mock)
        model: Model name
        status: Call status (success, error, timeout)
        duration: Call duration in seconds
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
    """
    llm_requests_total.labels(
        provider=provider,
        model=model,
        status=status
    ).inc()
    
    llm_request_duration_seconds.labels(
        provider=provider,
        model=model
    ).observe(duration)
    
    if input_tokens is not None:
        llm_tokens_total.labels(
            provider=provider,
            model=model,
            token_type="input"
        ).inc(input_tokens)
    
    if output_tokens is not None:
        llm_tokens_total.labels(
            provider=provider,
            model=model,
            token_type="output"
        ).inc(output_tokens)


def track_cache_operation(cache_name: str, operation: str, result: str):
    """
    Track cache operation metrics.
    
    Args:
        cache_name: Name of cache (yahoo, sp500, etc.)
        operation: Operation type (get, set, delete)
        result: Operation result (hit, miss, success, error)
    """
    cache_operations_total.labels(
        operation=operation,
        cache_name=cache_name,
        result=result
    ).inc()


def update_cache_hit_ratio(cache_name: str, hits: int, total: int):
    """
    Update cache hit ratio gauge.
    
    Args:
        cache_name: Name of cache
        hits: Number of cache hits
        total: Total cache operations
    """
    ratio = hits / total if total > 0 else 0.0
    cache_hit_ratio.labels(cache_name=cache_name).set(ratio)


def track_query_classification(query_type: str):
    """
    Track query classification metrics.
    
    Args:
        query_type: Classified query type (DOC, SQL, LIVE_DATA, etc.)
    """
    query_classification_total.labels(query_type=query_type).inc()


def track_background_task(task_type: str, status: str, duration: Optional[float] = None):
    """
    Track background task metrics.
    
    Args:
        task_type: Type of task
        status: Task status (pending, completed, failed)
        duration: Task duration in seconds (if completed)
    """
    background_tasks_total.labels(
        task_type=task_type,
        status=status
    ).inc()
    
    if duration is not None:
        background_tasks_duration_seconds.labels(
            task_type=task_type
        ).observe(duration)


def update_queue_stats(pending: int, running: int, completed: int, failed: int):
    """
    Update background task queue statistics.
    
    Args:
        pending: Number of pending tasks
        running: Number of running tasks
        completed: Number of completed tasks
        failed: Number of failed tasks
    """
    background_tasks_in_queue.labels(status="pending").set(pending)
    background_tasks_in_queue.labels(status="running").set(running)
    background_tasks_in_queue.labels(status="completed").set(completed)
    background_tasks_in_queue.labels(status="failed").set(failed)


# ============================================================================
# DECORATORS
# ============================================================================


def track_time(metric: Histogram, labels: dict):
    """
    Decorator to track function execution time.
    
    Args:
        metric: Histogram metric to update
        labels: Labels to apply
    
    Example:
        @track_time(query_processing_duration_seconds, {"query_type": "DOC"})
        def process_doc_query():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start
                metric.labels(**labels).observe(duration)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start
                metric.labels(**labels).observe(duration)
        
        # Return appropriate wrapper based on function type
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def instrument_llm(provider: str, model: str):
    """
    Decorator to instrument LLM function calls.
    
    Args:
        provider: LLM provider name
        model: Model name
    
    Example:
        @instrument_llm("openai", "gpt-4")
        async def call_openai():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            status = "success"
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                raise
            finally:
                duration = time.time() - start
                track_llm_call(provider, model, status, duration)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            status = "success"
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                raise
            finally:
                duration = time.time() - start
                track_llm_call(provider, model, status, duration)
        
        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


# ============================================================================
# METRICS EXPORT
# ============================================================================


def get_metrics() -> tuple[bytes, str]:
    """
    Get current metrics in Prometheus format.
    
    Returns:
        Tuple of (metrics_data, content_type)
    
    Example:
        data, content_type = get_metrics()
        return Response(content=data, media_type=content_type)
    """
    return generate_latest(registry), CONTENT_TYPE_LATEST


def get_metrics_summary() -> dict:
    """
    Get human-readable metrics summary.
    
    Returns:
        Dict with current metric values
    """
    # This is a simplified summary - in production you'd parse the actual metrics
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "metrics": {
            "http": "See /metrics endpoint for detailed HTTP metrics",
            "llm": "See /metrics endpoint for detailed LLM metrics",
            "cache": "See /metrics endpoint for detailed cache metrics",
            "tasks": "See /metrics endpoint for detailed task metrics",
        },
        "prometheus_endpoint": "/metrics",
    }
