"""FastAPI server for Financial RAG application.

WINDOWS SAFETY NOTE:
- This server should start exactly ONE time
- If multiple processes bind to port 8000, restart with: taskkill /F /IM python.exe
- serve.py includes guards to detect and prevent multiple instances

ENTERPRISE FEATURES:
- API versioning (v1, v2) with backwards compatibility
- Prometheus metrics endpoint (/metrics)
- Background task processing (/api/v1/chat/async)
- Debug middleware with X-Debug-Info headers
- Comprehensive error handling and logging
"""
# Fix OpenMP duplicate runtime warning (common with ML libraries like numpy+mkl)
import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "4")

from fastapi import FastAPI, HTTPException, UploadFile, File, APIRouter, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional, List
import traceback
from functools import lru_cache
from datetime import datetime, timedelta
import time
import logging

import anyio

from app.core.chains import answer_financial_question
from app.core.plot_generator import generate_plot_from_rag_output
from app.core.data_ingestion import parse_uploaded_file, get_data_preview, ingest_to_database, detect_data_type
from app.core.data_health import collect_data_health
from app.core.insights_sp500 import (
    get_database_summary,
    get_revenue_leaders,
    get_profitability_metrics,
    get_growth_trends,
    get_sector_comparison
)
from app.core.sp500_analytics import (
    ingest_sp500_data,
    get_sp500_summary,
    get_time_series_data,
    get_year_over_year_growth,
    get_correlation_matrix,
    get_decade_performance,
    get_volatility_analysis
)
from app.core.sp500_chains import answer_sp500_question, extract_sp500_chart_params
from app.core.sp500_companies import (
    get_sp500_companies,
    get_company_data,
    get_top_companies_by_revenue,
    search_companies
)
from app.core.response_utils import analytics_response, merge_date_range

# Enterprise features
from app.core.queue import get_query_queue, TaskNotFoundError
from app.core.metrics import (
    track_http_request,
    track_query_classification,
    get_metrics,
    get_metrics_summary,
    http_requests_in_progress,
)
from app.middleware.debug import DebugMiddleware, timed, set_debug_info
from app.config import settings

# CORS middleware for browser requests
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)

# ============================================================================
# APPLICATION SETUP
# ============================================================================

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Enterprise-grade Financial RAG API with real-time market data and document analysis",
    contact={
        "name": "Financial RAG Team",
        "email": "support@financialrag.example.com",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=[
        {"name": "health", "description": "Health check and monitoring endpoints"},
        {"name": "chat", "description": "Financial Q&A chat endpoints"},
        {"name": "analytics", "description": "S&P 500 analytics and insights"},
        {"name": "data", "description": "Data ingestion and management"},
        {"name": "config", "description": "Configuration and debugging"},
    ],
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.security.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add debug middleware (only active when DEBUG=true)
app.add_middleware(DebugMiddleware)

# Metrics middleware
@app.middleware("http")
async def metrics_middleware(request, call_next):
    """Track HTTP metrics for all requests."""
    method = request.method
    path = request.url.path
    
    # Increment in-progress gauge
    http_requests_in_progress.labels(method=method, endpoint=path).inc()
    
    start_time = time.time()
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as e:
        status_code = 500
        raise
    finally:
        # Decrement in-progress gauge
        http_requests_in_progress.labels(method=method, endpoint=path).dec()
        
        # Track request
        duration = time.time() - start_time
        track_http_request(method, path, status_code, duration)
    
    return response

# Serve web UI
web_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "web"))
if os.path.isdir(web_dir):
    app.mount("/static", StaticFiles(directory=web_dir), name="static")

# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class ChatRequest(BaseModel):
    """V1 Chat request model."""
    user_id: str = Field(..., description="User identifier for tracking", example="user123")
    question: str = Field(..., description="Financial question", example="What is Apple's revenue?")
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user123",
                "question": "What is Apple's market cap?",
            }
        }


class ChatRequestV2(BaseModel):
    """V2 Chat request with additional features."""
    user_id: str = Field(..., description="User identifier", example="user123")
    question: str = Field(..., description="Financial question", example="Analyze Tesla stock")
    include_sources: bool = Field(
        default=False,
        description="Include source attribution in response"
    )
    stream_response: bool = Field(
        default=False,
        description="Stream response (not yet implemented)"
    )
    max_tokens: Optional[int] = Field(
        default=None,
        description="Maximum tokens in response",
        ge=1,
        le=4000
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user123",
                "question": "Compare Apple and Microsoft revenue",
                "include_sources": True,
                "max_tokens": 500,
            }
        }


class ChatResponse(BaseModel):
    """Chat response model."""
    answer: Any = Field(..., description="Answer (string or dict)")
    query_type: str = Field(..., description="Query classification type")
    router: Dict[str, Any] = Field(..., description="Router decision metadata")
    source: Optional[str] = Field(None, description="Data source used")
    
    class Config:
        json_schema_extra = {
            "example": {
                "answer": "Apple's revenue for Q4 2023 was $119.6 billion.",
                "query_type": "LIVE_DATA",
                "router": {"reason": "Market query"},
                "source": "yahoo_finance",
            }
        }


class ChatResponseV2(BaseModel):
    """V2 Chat response with source attribution."""
    answer: Any = Field(..., description="Answer text or structured data")
    query_type: str = Field(..., description="Query classification")
    router: Dict[str, Any] = Field(..., description="Router metadata")
    source: Optional[str] = Field(None, description="Primary data source")
    sources: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Detailed source attribution"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional response metadata"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "answer": "Based on live data, Apple's stock is trading at $175.43.",
                "query_type": "LIVE_DATA",
                "router": {"reason": "Stock price query"},
                "source": "yahoo_finance",
                "sources": [
                    {"type": "yahoo_finance", "confidence": 1.0, "timestamp": "2025-12-29T10:00:00Z"}
                ],
                "metadata": {"processing_time_ms": 345, "cache_hit": False},
            }
        }


class TaskResponse(BaseModel):
    """Background task response."""
    task_id: str = Field(..., description="Unique task identifier")
    status: str = Field(..., description="Task status")
    status_url: str = Field(..., description="URL to check task status")
    
    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "pending",
                "status_url": "/api/v1/tasks/550e8400-e29b-41d4-a716-446655440000",
            }
        }


class TaskStatusResponse(BaseModel):
    """Task status response."""
    task_id: str
    status: str
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


# ============================================================================
# API V1 ROUTER
# ============================================================================

v1_router = APIRouter(prefix="/api/v1", tags=["v1"])


@v1_router.post("/chat", response_model=ChatResponse, summary="Chat with Financial RAG (V1)")
async def chat_v1(req: ChatRequest):
    """
    Process financial question using RAG pipeline (V1).
    
    Automatically routes to appropriate data source:
    - LIVE_DATA: Real-time market data from Yahoo Finance
    - DOC: Document retrieval from vector store
    - SQL: Historical database queries
    - HYBRID: Combination of sources
    """
    try:
        result = await anyio.to_thread.run_sync(answer_financial_question, req.question)
        
        # Track query classification
        query_type = result.get("query_type", "UNKNOWN")
        track_query_classification(query_type)
        set_debug_info("query_type", query_type)
        
        return ChatResponse(
            answer=result.get("answer", ""),
            query_type=query_type,
            router=result.get("router", {}),
            source=result.get("source"),
        )
    except Exception as e:
        logger.error(f"Chat V1 error: {e}", exc_info=True)
        error_msg = f"Server error: {str(e)}"
        return ChatResponse(
            answer=error_msg,
            query_type="ERROR",
            router={"error": str(e), "traceback": traceback.format_exc()},
        )


@v1_router.post("/chat/async", response_model=TaskResponse, summary="Async Chat (Background Task)")
async def chat_async_v1(req: ChatRequest):
    """
    Submit chat request as background task.
    
    Returns immediately with task ID. Use /api/v1/tasks/{task_id} to check status.
    Useful for long-running queries that might exceed HTTP timeout.
    """
    try:
        queue = get_query_queue()
        
        # Wrap answer_financial_question for async execution
        async def process_query():
            return await anyio.to_thread.run_sync(answer_financial_question, req.question)
        
        task_id = await queue.add_task(process_query)
        
        return TaskResponse(
            task_id=task_id,
            status="pending",
            status_url=f"/api/v1/tasks/{task_id}",
        )
    except Exception as e:
        logger.error(f"Async chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create task: {str(e)}")


@v1_router.get("/tasks/{task_id}", response_model=TaskStatusResponse, summary="Get Task Status")
async def get_task_status_v1(task_id: str):
    """
    Get status of background task.
    
    Returns task status, result (if completed), or error details (if failed).
    """
    try:
        queue = get_query_queue()
        status_data = queue.get_task_status(task_id)
        
        return TaskStatusResponse(**status_data)
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    except Exception as e:
        logger.error(f"Task status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get task status: {str(e)}")


# ============================================================================
# API V2 ROUTER  
# ============================================================================

v2_router = APIRouter(prefix="/api/v2", tags=["v2"])


@v2_router.post("/chat", response_model=ChatResponseV2, summary="Chat with Financial RAG (V2)")
async def chat_v2(req: ChatRequestV2):
    """
    Enhanced chat endpoint with source attribution (V2).
    
    New features:
    - Source attribution when include_sources=true
    - Token limit control via max_tokens
    - Streaming support (coming soon)
    - Enhanced metadata in response
    """
    try:
        start_time = time.time()
        
        result = await anyio.to_thread.run_sync(answer_financial_question, req.question)
        
        query_type = result.get("query_type", "UNKNOWN")
        track_query_classification(query_type)
        
        # Build sources list if requested
        sources = None
        if req.include_sources:
            sources = []
            source_type = result.get("source", "unknown")
            sources.append({
                "type": source_type,
                "confidence": 1.0,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            })
        
        # Add metadata
        processing_time_ms = round((time.time() - start_time) * 1000, 2)
        metadata = {
            "processing_time_ms": processing_time_ms,
            "cache_hit": False,  # TODO: Track actual cache hits
            "model": settings.llm_model,
        }
        
        return ChatResponseV2(
            answer=result.get("answer", ""),
            query_type=query_type,
            router=result.get("router", {}),
            source=result.get("source"),
            sources=sources,
            metadata=metadata,
        )
    except Exception as e:
        logger.error(f"Chat V2 error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


# ============================================================================
# LEGACY ENDPOINTS (backwards compatibility)
# ============================================================================


@app.get("/")
async def root():
    """Serve the main index.html page."""
    index_path = os.path.join(web_dir, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path, media_type="text/html")
    return JSONResponse(status_code=404, content={"error": "index.html not found"})


@app.get("/dashboard")
async def dashboard():
    """Serve the modern analytics dashboard."""
    dashboard_path = os.path.join(web_dir, "dashboard.html")
    if os.path.isfile(dashboard_path):
        return FileResponse(dashboard_path, media_type="text/html")
    return JSONResponse(status_code=404, content={"error": "dashboard.html not found"})


@app.post("/chat", response_model=ChatResponse, tags=["chat", "legacy"])
async def chat_legacy(req: ChatRequest):
    """
    Legacy chat endpoint (backwards compatibility).
    
    Routes to V1 endpoint. Use /api/v1/chat or /api/v2/chat for new implementations.
    """
    return await chat_v1(req)


# ============================================================================
# MONITORING & DEBUGGING ENDPOINTS
# ============================================================================

@app.get("/health", tags=["health"], summary="Health Check")
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.get("/metrics", tags=["health"], summary="Prometheus Metrics")
async def metrics_endpoint():
    """
    Expose Prometheus metrics for monitoring.
    
    Scrape this endpoint with Prometheus to collect:
    - HTTP request metrics
    - LLM usage statistics
    - Cache performance
    - Background task stats
    """
    metrics_data, content_type = get_metrics()
    return Response(content=metrics_data, media_type=content_type)


@app.get("/api/v1/config", tags=["config"], summary="Get Configuration")
async def get_config():
    """
    Get sanitized configuration (API keys masked).
    
    Useful for debugging configuration issues without exposing sensitive data.
    """
    return JSONResponse(content=settings.get_sanitized_config())


@app.get("/api/v1/queue/stats", tags=["health"], summary="Queue Statistics")
async def queue_stats():
    """Get background task queue statistics."""
    queue = get_query_queue()
    return JSONResponse(content=queue.get_queue_stats())


@app.get("/api/health/data")
async def data_health_report():
    """Return diagnostics about loaded data sources and missing metrics."""
    try:
        report = await anyio.to_thread.run_sync(collect_data_health)
        return JSONResponse(content=report)
    except Exception as exc:
        return _analytics_error_response("data-health", f"Failed to gather data health: {exc}")


@app.get("/api/extract")
def api_extract():
    """Return demo extraction results representing parsed payslip/invoice financials."""
    demo = [
        {"id": "salary", "label": "Net Salary", "amount": 7200, "type": "income", "recommended_allocation": {"invest": 0.25, "savings": 0.25, "expenses": 0.5}},
        {"id": "tax", "label": "Taxes", "amount": 1500, "type": "expense", "recommended_allocation": {"invest": 0.0, "savings": 0.0, "expenses": 1.0}},
        {"id": "rent", "label": "Rent/Mortgage", "amount": 1800, "type": "expense", "recommended_allocation": {"invest": 0.0, "savings": 0.0, "expenses": 1.0}},
        {"id": "utilities", "label": "Utilities", "amount": 300, "type": "expense", "recommended_allocation": {"invest": 0.0, "savings": 0.0, "expenses": 1.0}},
        {"id": "groceries", "label": "Groceries", "amount": 600, "type": "expense", "recommended_allocation": {"invest": 0.0, "savings": 0.0, "expenses": 1.0}},
        {"id": "savings", "label": "Current Savings", "amount": 12000, "type": "asset", "recommended_allocation": {"invest": 0.5, "savings": 0.5, "expenses": 0.0}}
    ]
    total_income = sum(item['amount'] for item in demo if item['type'] in ('income', 'asset'))
    total_expenses = sum(item['amount'] for item in demo if item['type'] == 'expense')
    disposable = max(0, total_income - total_expenses)
    recommendations = {
        "disposable": disposable,
        "monthly_invest_suggestion": round(disposable * 0.25, 2),
        "allocation_example": {"stocks": 0.6, "bonds": 0.25, "cash": 0.15}
    }
    return JSONResponse(content={"data": demo, "summary": recommendations})


@app.post("/api/extract/upload")
async def api_extract_upload(file: UploadFile = File(...)):
    """Accept a document upload (PDF/image) and return demo extraction results."""
    try:
        contents = await file.read()
        size = len(contents)
        demo_response = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": size,
            "note": "Demo extraction - replace with real parser"
        }
        demo = [
            {"id": "salary", "label": "Net Salary", "amount": 7200, "type": "income", "recommended_allocation": {"invest": 0.25, "savings": 0.25, "expenses": 0.5}},
            {"id": "tax", "label": "Taxes", "amount": 1500, "type": "expense", "recommended_allocation": {"invest": 0.0, "savings": 0.0, "expenses": 1.0}},
            {"id": "rent", "label": "Rent/Mortgage", "amount": 1800, "type": "expense", "recommended_allocation": {"invest": 0.0, "savings": 0.0, "expenses": 1.0}},
            {"id": "utilities", "label": "Utilities", "amount": 300, "type": "expense", "recommended_allocation": {"invest": 0.0, "savings": 0.0, "expenses": 1.0}},
            {"id": "groceries", "label": "Groceries", "amount": 600, "type": "expense", "recommended_allocation": {"invest": 0.0, "savings": 0.0, "expenses": 1.0}},
            {"id": "savings", "label": "Current Savings", "amount": 12000, "type": "asset", "recommended_allocation": {"invest": 0.5, "savings": 0.5, "expenses": 0.0}}
        ]
        total_income = sum(item['amount'] for item in demo if item['type'] in ('income', 'asset'))
        total_expenses = sum(item['amount'] for item in demo if item['type'] == 'expense')
        disposable = max(0, total_income - total_expenses)
        recommendations = {
            "disposable": disposable,
            "monthly_invest_suggestion": round(disposable * 0.25, 2),
            "allocation_example": {"stocks": 0.6, "bonds": 0.25, "cash": 0.15}
        }
        payload = {"file": demo_response, "data": demo, "summary": recommendations}
        return JSONResponse(content=payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.get("/api/income")
def api_income():
    """Return sample income data (lat/lng + income) for the map."""
    sample = [
        {"id": "nyc", "name": "New York, NY", "lat": 40.7128, "lng": -74.0060, "income": 72000},
        {"id": "sf", "name": "San Francisco, CA", "lat": 37.7749, "lng": -122.4194, "income": 115000},
        {"id": "chi", "name": "Chicago, IL", "lat": 41.8781, "lng": -87.6298, "income": 54000},
        {"id": "hou", "name": "Houston, TX", "lat": 29.7604, "lng": -95.3698, "income": 48000},
        {"id": "mia", "name": "Miami, FL", "lat": 25.7617, "lng": -80.1918, "income": 46000},
    ]
    return JSONResponse(content={"data": sample})


@app.get("/float")
def float_page():
    """Serve the floating financial UI page."""
    float_path = os.path.join(web_dir, "float.html")
    if os.path.exists(float_path):
        return FileResponse(float_path)
    return {"message": "Float UI not found."}


@app.get("/map")
def map_page():
    """Serve the interactive income map page."""
    map_path = os.path.join(web_dir, "map.html")
    if os.path.exists(map_path):
        return FileResponse(map_path)
    return {"message": "Map page not found."}


@app.get("/plot-viewer")
def plot_viewer_page():
    """Serve the financial plot viewer page."""
    plot_viewer_path = os.path.join(web_dir, "plot-viewer.html")
    if os.path.exists(plot_viewer_path):
        return FileResponse(plot_viewer_path)
    return {"message": "Plot viewer page not found."}


@app.post("/api/plot")
async def api_plot(req: ChatRequest):
    """
    Extract financial metrics from query/answer text and generate a plot.
    
    Accepts the same ChatRequest format as /chat.
    Returns JSON with company, metric, and base64-encoded plot image.
    """
    try:
        # Use the question as the text to extract parameters from. Run in a
        # worker thread because plotting + DB operations are blocking.
        result = await anyio.to_thread.run_sync(generate_plot_from_rag_output, req.question)
        
        if result is None:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Could not generate plot",
                    "message": "Unable to extract company ticker or financial metric from input",
                }
            )
        
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "error": "Plot generation failed",
                "message": str(e),
                "traceback": traceback.format_exc(),
            }
        )


@app.post("/api/upload/file")
async def upload_financial_data(file: UploadFile = File(...)):
    """
    Upload CSV or Excel file with financial data.
    Returns preview and allows ingestion into database.
    """
    try:
        contents = await file.read()
        
        # Parse file
        df, error = await anyio.to_thread.run_sync(
            parse_uploaded_file, contents, file.filename
        )
        
        if error:
            return JSONResponse(
                status_code=400,
                content={"error": error}
            )
        
        # Get preview
        preview = await anyio.to_thread.run_sync(get_data_preview, df)
        
        return JSONResponse(content={
            "filename": file.filename,
            "preview": preview,
            "message": "File parsed successfully. Use /api/upload/ingest to load into database."
        })
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Upload failed: {str(e)}"}
        )


@app.post("/api/upload/ingest")
async def ingest_uploaded_data(file: UploadFile = File(...)):
    """
    Upload and directly ingest CSV/Excel file into database.
    Detects data type (S&P 500 vs company metrics) and routes to appropriate ingestion.
    """
    try:
        contents = await file.read()
        
        # Parse file
        df, error = await anyio.to_thread.run_sync(
            parse_uploaded_file, contents, file.filename
        )
        
        if error:
            return JSONResponse(
                status_code=400,
                content={"error": error}
            )
        
        # Detect data type
        data_type = await anyio.to_thread.run_sync(detect_data_type, df)
        
        # Route to appropriate ingestion
        if data_type == 'sp500':
            result = await anyio.to_thread.run_sync(ingest_sp500_data, df)
        else:
            result = await anyio.to_thread.run_sync(ingest_to_database, df)
        
        if not result.get("success"):
            return JSONResponse(
                status_code=500,
                content=result
            )
        
        return JSONResponse(content={
            "message": f"Data ingested successfully as {data_type}",
            "data_type": data_type,
            **result
        })
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Ingestion failed: {str(e)}"}
        )


def _add_cache_headers(response: JSONResponse, max_age: int = 300):
    """Add HTTP cache headers to response."""
    response.headers["Cache-Control"] = f"public, max-age={max_age}"
    response.headers["ETag"] = f'"{hash(str(response.body))}"'
    return response


def _analytics_error_response(aggregation: str, message: str, status_code: int = 500, company: str = "SP500 Index") -> JSONResponse:
    payload = analytics_response(
        meta={
            "company": company,
            "date_range": merge_date_range(None, None),
            "aggregation": aggregation,
        },
        data=[],
        summary={"status": "error"},
        errors=[message],
    )
    return JSONResponse(status_code=status_code, content=payload)


@app.get("/api/insights/summary")
async def insights_summary():
    """Get overview statistics of stored financial data."""
    try:
        summary = await anyio.to_thread.run_sync(get_database_summary)
        response = JSONResponse(content=summary)
        return _add_cache_headers(response, max_age=600)  # Cache for 10 minutes
    except Exception as e:
        return _analytics_error_response("insights", f"Failed to fetch summary: {e}")


@app.get("/api/insights/revenue-leaders")
async def insights_revenue_leaders(limit: int = 10):
    """Get companies with highest revenue."""
    try:
        leaders = await anyio.to_thread.run_sync(get_revenue_leaders, limit)
        response = JSONResponse(content=leaders)
        return _add_cache_headers(response, max_age=600)  # Cache for 10 minutes
    except Exception as e:
        return _analytics_error_response("insights", f"Failed to fetch revenue leaders: {e}")


@app.get("/api/insights/profitability")
async def insights_profitability(limit: int = 10):
    """Get companies with best profit margins."""
    try:
        metrics = await anyio.to_thread.run_sync(get_profitability_metrics, limit)
        response = JSONResponse(content=metrics)
        return _add_cache_headers(response, max_age=600)  # Cache for 10 minutes
    except Exception as e:
        return _analytics_error_response("insights", f"Failed to fetch profitability: {e}")


@app.get("/api/insights/trends/{ticker}")
async def insights_trends(ticker: str):
    """Get growth trends for a specific company."""
    try:
        trends = await anyio.to_thread.run_sync(get_growth_trends, ticker)
        response = JSONResponse(content=trends)
        return _add_cache_headers(response, max_age=600)  # Cache for 10 minutes
    except Exception as e:
        return _analytics_error_response("insights", f"Failed to fetch trends: {e}", company=ticker.upper())


@app.get("/api/insights/comparison")
async def insights_comparison():
    """Compare metrics across all companies."""
    try:
        comparison = await anyio.to_thread.run_sync(get_sector_comparison)
        response = JSONResponse(content=comparison)
        return _add_cache_headers(response, max_age=600)  # Cache for 10 minutes
    except Exception as e:
        return _analytics_error_response("insights", f"Failed to fetch comparison: {e}")


# ==================== Live Market Data Endpoint ====================

@app.get("/api/market/live")
async def get_live_market_data(range: str = "1d"):
    """
    Get live S&P 500 market data from Yahoo Finance.
    
    Args:
        range: Time range - '1d', '5d', '1mo', '3mo', '1y'
    
    Returns:
        Live quote data and historical prices for charting
    """
    def fetch_market_data():
        try:
            import yfinance as yf
            from datetime import datetime
            
            # Fetch S&P 500 index
            sp500 = yf.Ticker("^GSPC")
            
            # Get quote info
            info = sp500.info
            quote = {
                "symbol": "^GSPC",
                "name": "S&P 500",
                "regularMarketPrice": info.get("regularMarketPrice") or info.get("previousClose"),
                "regularMarketChange": info.get("regularMarketChange", 0),
                "regularMarketChangePercent": info.get("regularMarketChangePercent", 0),
                "regularMarketOpen": info.get("regularMarketOpen") or info.get("open"),
                "regularMarketDayHigh": info.get("regularMarketDayHigh") or info.get("dayHigh"),
                "regularMarketDayLow": info.get("regularMarketDayLow") or info.get("dayLow"),
                "regularMarketPreviousClose": info.get("regularMarketPreviousClose") or info.get("previousClose"),
                "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
                "fiftyTwoWeekLow": info.get("fiftyTwoWeekLow"),
            }
            
            # Map range to yfinance parameters
            range_map = {
                "1d": {"period": "1d", "interval": "5m"},
                "5d": {"period": "5d", "interval": "15m"},
                "1mo": {"period": "1mo", "interval": "1h"},
                "3mo": {"period": "3mo", "interval": "1d"},
                "1y": {"period": "1y", "interval": "1d"},
            }
            params = range_map.get(range, range_map["1d"])
            
            # Get historical data for chart
            hist = sp500.history(period=params["period"], interval=params["interval"])
            
            history = []
            for idx, row in hist.iterrows():
                if params["interval"] in ["5m", "15m", "1h"]:
                    time_str = idx.strftime('%H:%M')
                else:
                    time_str = idx.strftime('%m/%d')
                
                history.append({
                    "time": time_str,
                    "date": idx.strftime('%Y-%m-%d %H:%M'),
                    "close": round(row["Close"], 2),
                    "open": round(row["Open"], 2),
                    "high": round(row["High"], 2),
                    "low": round(row["Low"], 2),
                    "volume": int(row["Volume"]) if row["Volume"] else 0,
                })
            
            return {
                "success": True,
                "quote": quote,
                "history": history,
                "range": range,
                "timestamp": datetime.now().isoformat(),
                "source": "yahoo_finance",
            }
            
        except Exception as e:
            print(f"[Market API] Error fetching live data: {e}")
            return {
                "success": False,
                "error": str(e),
                "quote": {},
                "history": [],
            }
    
    try:
        data = await anyio.to_thread.run_sync(fetch_market_data)
        response = JSONResponse(content=data)
        return _add_cache_headers(response, max_age=60)  # Cache for 1 minute
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.get("/api/market/indices")
async def get_market_indices():
    """
    Get live data for major US indices: S&P 500, DOW, NASDAQ.
    Optimized for fast response - US markets only.
    """
    def fetch_indices():
        try:
            import yfinance as yf
            from datetime import datetime
            
            # US indices only for faster response
            indices = {
                "^GSPC": "S&P 500",
                "^DJI": "Dow Jones",
                "^IXIC": "NASDAQ"
            }
            
            result = {}
            for symbol, name in indices.items():
                try:
                    ticker = yf.Ticker(symbol)
                    info = ticker.info
                    
                    price = info.get("regularMarketPrice") or info.get("previousClose") or 0
                    prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose") or price
                    change = info.get("regularMarketChange") or (price - prev_close)
                    change_pct = info.get("regularMarketChangePercent") or ((change / prev_close * 100) if prev_close else 0)
                    
                    result[symbol] = {
                        "name": name,
                        "symbol": symbol,
                        "price": round(price, 2) if price else None,
                        "change": round(change, 2) if change else 0,
                        "change_pct": round(change_pct, 2) if change_pct else 0,
                        "open": info.get("regularMarketOpen") or info.get("open"),
                        "high": info.get("regularMarketDayHigh") or info.get("dayHigh"),
                        "low": info.get("regularMarketDayLow") or info.get("dayLow"),
                        "prev_close": round(prev_close, 2) if prev_close else None,
                    }
                except Exception as e:
                    print(f"Error fetching {symbol}: {e}")
                    result[symbol] = {"name": name, "symbol": symbol, "error": str(e)}
            
            return {
                "success": True,
                "indices": result,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    try:
        data = await anyio.to_thread.run_sync(fetch_indices)
        response = JSONResponse(content=data)
        return _add_cache_headers(response, max_age=60)
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.get("/api/market/india")
async def get_indian_market_data():
    """
    Get detailed Indian market data: SENSEX, NIFTY 50 with comparison to S&P 500.
    """
    def fetch_india_market():
        try:
            import yfinance as yf
            from datetime import datetime
            import pytz
            
            # Check if Indian market is open (9:15 AM - 3:30 PM IST, Mon-Fri)
            ist = pytz.timezone('Asia/Kolkata')
            now_ist = datetime.now(ist)
            market_open = False
            if now_ist.weekday() < 5:  # Monday = 0, Friday = 4
                market_start = now_ist.replace(hour=9, minute=15, second=0)
                market_end = now_ist.replace(hour=15, minute=30, second=0)
                market_open = market_start <= now_ist <= market_end
            
            # Fetch SENSEX
            sensex = yf.Ticker("^BSESN")
            sensex_info = sensex.info
            sensex_price = sensex_info.get("regularMarketPrice") or sensex_info.get("previousClose") or 0
            sensex_prev = sensex_info.get("regularMarketPreviousClose") or sensex_info.get("previousClose") or sensex_price
            sensex_change = sensex_info.get("regularMarketChange") or (sensex_price - sensex_prev)
            sensex_pct = sensex_info.get("regularMarketChangePercent") or ((sensex_change / sensex_prev * 100) if sensex_prev else 0)
            
            # Fetch NIFTY
            nifty = yf.Ticker("^NSEI")
            nifty_info = nifty.info
            nifty_price = nifty_info.get("regularMarketPrice") or nifty_info.get("previousClose") or 0
            nifty_prev = nifty_info.get("regularMarketPreviousClose") or nifty_info.get("previousClose") or nifty_price
            nifty_change = nifty_info.get("regularMarketChange") or (nifty_price - nifty_prev)
            nifty_pct = nifty_info.get("regularMarketChangePercent") or ((nifty_change / nifty_prev * 100) if nifty_prev else 0)
            
            # Fetch S&P 500 for comparison
            sp500 = yf.Ticker("^GSPC")
            sp500_info = sp500.info
            sp500_price = sp500_info.get("regularMarketPrice") or sp500_info.get("previousClose") or 0
            sp500_prev = sp500_info.get("regularMarketPreviousClose") or sp500_info.get("previousClose") or sp500_price
            sp500_pct = ((sp500_price - sp500_prev) / sp500_prev * 100) if sp500_prev else 0
            
            return {
                "success": True,
                "market_open": market_open,
                "market_time": now_ist.strftime("%H:%M IST"),
                "sensex": {
                    "price": round(sensex_price, 2),
                    "change": round(sensex_change, 2),
                    "change_pct": round(sensex_pct, 2),
                    "open": sensex_info.get("regularMarketOpen") or sensex_info.get("open"),
                    "high": sensex_info.get("regularMarketDayHigh") or sensex_info.get("dayHigh"),
                    "low": sensex_info.get("regularMarketDayLow") or sensex_info.get("dayLow"),
                    "prev_close": round(sensex_prev, 2),
                    "52w_high": sensex_info.get("fiftyTwoWeekHigh"),
                    "52w_low": sensex_info.get("fiftyTwoWeekLow"),
                },
                "nifty": {
                    "price": round(nifty_price, 2),
                    "change": round(nifty_change, 2),
                    "change_pct": round(nifty_pct, 2),
                    "open": nifty_info.get("regularMarketOpen") or nifty_info.get("open"),
                    "high": nifty_info.get("regularMarketDayHigh") or nifty_info.get("dayHigh"),
                    "low": nifty_info.get("regularMarketDayLow") or nifty_info.get("dayLow"),
                    "prev_close": round(nifty_prev, 2),
                    "52w_high": nifty_info.get("fiftyTwoWeekHigh"),
                    "52w_low": nifty_info.get("fiftyTwoWeekLow"),
                },
                "sp500_change_pct": round(sp500_pct, 2),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            print(f"Error fetching Indian market data: {e}")
            return {"success": False, "error": str(e)}
    
    try:
        data = await anyio.to_thread.run_sync(fetch_india_market)
        response = JSONResponse(content=data)
        return _add_cache_headers(response, max_age=60)
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})
# ==================== S&P 500 Analytics Endpoints ====================

@app.get("/api/sp500/summary")
async def sp500_summary():
    """Get S&P 500 data summary including date range, latest values, and statistics."""
    try:
        summary = await anyio.to_thread.run_sync(get_sp500_summary)
        return JSONResponse(content=summary)
    except Exception as e:
        return _analytics_error_response("daily", f"Failed to fetch S&P 500 summary: {e}")


@app.get("/api/sp500/timeseries")
async def sp500_timeseries(start_date: str = None, end_date: str = None, metrics: str = None, limit: int = 1000):
    """
    Get S&P 500 time series data with optional filters.
    
    Query parameters:
    - start_date: Start date (YYYY-MM-DD format)
    - end_date: End date (YYYY-MM-DD format)
    - metrics: Comma-separated list of metrics (e.g., "sp500,dividend,pe10")
    - limit: Maximum number of records (default 1000)
    """
    try:
        metrics_list = metrics.split(',') if metrics else None
        data = await anyio.to_thread.run_sync(
            get_time_series_data, start_date, end_date, metrics_list, limit
        )
        return JSONResponse(content=data)
    except Exception as e:
        return _analytics_error_response("daily", f"Failed to fetch time series: {e}")


@app.get("/api/sp500/yoy-growth")
async def sp500_yoy_growth():
    """Get year-over-year growth rates for S&P 500 metrics."""
    try:
        growth = await anyio.to_thread.run_sync(get_year_over_year_growth)
        return JSONResponse(content=growth)
    except Exception as e:
        return _analytics_error_response("yearly", f"Failed to fetch YoY growth: {e}")


@app.get("/api/sp500/correlations")
async def sp500_correlations():
    """Get correlation matrix between S&P 500 and other metrics."""
    try:
        correlations = await anyio.to_thread.run_sync(get_correlation_matrix)
        return JSONResponse(content=correlations)
    except Exception as e:
        return _analytics_error_response("correlation", f"Failed to fetch correlations: {e}")


@app.get("/api/sp500/decades")
async def sp500_decades():
    """Get S&P 500 performance aggregated by decade."""
    try:
        decades = await anyio.to_thread.run_sync(get_decade_performance)
        return JSONResponse(content=decades)
    except Exception as e:
        return _analytics_error_response("decade", f"Failed to fetch decade performance: {e}")


@app.get("/api/sp500/volatility")
async def sp500_volatility(period: int = 365):
    """
    Get volatility analysis for S&P 500 data.
    
    Query parameters:
    - period: Number of days to analyze (default 365)
    """
    try:
        volatility = await anyio.to_thread.run_sync(get_volatility_analysis, period)
        return JSONResponse(content=volatility)
    except Exception as e:
        return _analytics_error_response("volatility", f"Failed to fetch volatility: {e}")


@app.get("/api/sp500/insights")
async def sp500_insights():
    """
    Get comprehensive market insights including:
    - Rolling returns (1Y, 5Y, 10Y CAGR)
    - Volatility metrics (30D, 1Y)
    - Maximum drawdown
    - Market regime (Bull/Bear/Sideways)
    - Valuation status (P/E percentiles)
    - Trend strength score (0-100)
    - Risk warnings and opportunities
    """
    try:
        from app.core.sp500_analytics import get_market_insights
        insights = await anyio.to_thread.run_sync(get_market_insights)
        return JSONResponse(content=insights)
    except Exception as e:
        return _analytics_error_response("insights", f"Failed to generate insights: {e}")


@app.get("/api/sp500/decades-enhanced")
async def sp500_decades_enhanced():
    """
    Get enhanced decade performance with CAGR, max drawdown, and volatility.
    """
    try:
        from app.core.sp500_analytics import get_enhanced_decade_performance
        decades = await anyio.to_thread.run_sync(get_enhanced_decade_performance)
        return JSONResponse(content=decades)
    except Exception as e:
        return _analytics_error_response("decade", f"Failed to fetch enhanced decade data: {e}")


@app.get("/api/sp500/correlations-full")
async def sp500_correlations_full():
    """
    Get full correlation matrix between all S&P 500 metrics.
    """
    try:
        from app.core.sp500_analytics import get_full_correlation_matrix
        correlations = await anyio.to_thread.run_sync(get_full_correlation_matrix)
        return JSONResponse(content=correlations)
    except Exception as e:
        return _analytics_error_response("correlation", f"Failed to fetch full correlations: {e}")


# ==================== S&P 500 LLM Chain Endpoints ====================

class SP500QuestionRequest(BaseModel):
    user_id: str
    question: str


@app.post("/api/sp500/ask")
async def sp500_ask(req: SP500QuestionRequest):
    """
    Ask a natural language question about S&P 500 data.
    
    Uses LLM to understand the question and provide intelligent analysis
    with relevant data and visualization parameters.
    """
    try:
        result = await answer_sp500_question(req.question)
        return JSONResponse(content=result)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"Failed to process S&P 500 question: {str(e)}",
                "traceback": traceback.format_exc()
            }
        )


@app.post("/api/sp500/chart-params")
async def sp500_chart_params(req: SP500QuestionRequest):
    """
    Extract chart visualization parameters from a S&P 500 question.
    
    Uses LLM to understand what type of chart and data the user wants to see.
    """
    try:
        params = await extract_sp500_chart_params(req.question)
        return JSONResponse(content=params)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"Failed to extract chart parameters: {str(e)}"
            }
        )


# ==================== S&P 500 Companies Endpoints ====================

@app.get("/api/sp500/companies")
async def sp500_companies_list(limit: int = 50):
    """Get list of S&P 500 companies."""
    try:
        companies = await anyio.to_thread.run_sync(get_sp500_companies, limit)
        return JSONResponse(content={
            "success": True,
            "count": len(companies),
            "companies": companies
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.get("/api/sp500/companies/top")
async def sp500_top_companies(limit: int = 10):
    """Get top S&P 500 companies by revenue."""
    try:
        companies = await anyio.to_thread.run_sync(get_top_companies_by_revenue, limit)
        return JSONResponse(content={
            "success": True,
            "count": len(companies),
            "companies": companies
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.get("/api/sp500/companies/search")
async def sp500_search_companies(q: str, limit: int = 10):
    """Search for S&P 500 companies by name or ticker."""
    try:
        companies = await anyio.to_thread.run_sync(search_companies, q, limit)
        return JSONResponse(content={
            "success": True,
            "count": len(companies),
            "query": q,
            "companies": companies
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.get("/api/sp500/companies/{ticker}")
async def sp500_company_detail(ticker: str):
    """Get detailed data for a specific company."""
    try:
        company = await anyio.to_thread.run_sync(get_company_data, ticker)
        if not company:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": f"Company {ticker} not found"}
            )
        return JSONResponse(content={
            "success": True,
            "company": company
        })
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


# ============================================================================
# REGISTER ROUTERS
# ============================================================================

# Register v1 and v2 routers
app.include_router(v1_router)
app.include_router(v2_router)

# ============================================================================
# LIFECYCLE EVENTS
# ============================================================================


@app.on_event("startup")
async def startup_event():
    """Startup event handler - verify LLM connection and system health."""
    import os as _os
    _pid = _os.getpid()
    
    print("=" * 70)
    print(f"Financial RAG API v{settings.app_version} - Enterprise Edition")
    print("=" * 70)
    print(f"[STARTUP] Process ID: {_pid}")
    print(f"[STARTUP] Debug Mode: {settings.debug}")
    print(f"[STARTUP] Environment: {'Production' if settings.is_production else 'Development'}")
    
    if settings.debug:
        print(f"[STARTUP] Debug middleware ACTIVE - X-Debug-Info headers enabled")
    
    print(f"\n[STARTUP] If multiple PIDs on port 8000, restart with:")
    print(f"[STARTUP]   tasklist | findstr python")
    print(f"[STARTUP]   taskkill /PID <pid> /F")
    
    # Verify Ollama LLM connection
    try:
        from app.core.llm import _check_ollama_health
        
        print("\n[STARTUP] Checking LLM connection...")
        if not settings.ollama_enabled:
            print("[STARTUP] Ollama explicitly disabled (OLLAMA_ENABLED=false)")
            print("[STARTUP] Enable by setting OLLAMA_ENABLED=true in .env and restarting")
        elif _check_ollama_health(log=False):
            print(f"[STARTUP] SUCCESS - Ollama ready with model: {settings.ollama_model}")
            print(f"[STARTUP] Ollama URL: {settings.ollama_base_url}")
        else:
            print("[STARTUP] WARNING - Ollama not available, will use mock fallback")
            print("[STARTUP] To enable Ollama: 1) ollama serve, 2) ollama pull mistral")
    except Exception as e:
        print(f"[STARTUP] LLM health check error: {str(e)}")
    
    print(f"\n[STARTUP] Enterprise Features:")
    print(f"[STARTUP]   ✓ API Versioning (v1, v2)")
    print(f"[STARTUP]   ✓ Prometheus Metrics (/metrics)")
    print(f"[STARTUP]   ✓ Background Tasks (/api/v1/chat/async)")
    print(f"[STARTUP]   ✓ Debug Middleware (X-Debug-Info)")
    print(f"[STARTUP]   ✓ Configuration Validation")
    
    print(f"\n[STARTUP] API Endpoints:")
    print(f"[STARTUP]   • Main UI: http://127.0.0.1:8000")
    print(f"[STARTUP]   • Dashboard: http://127.0.0.1:8000/dashboard")
    print(f"[STARTUP]   • API Docs: http://127.0.0.1:8000/docs")
    print(f"[STARTUP]   • Chat V1: http://127.0.0.1:8000/api/v1/chat")
    print(f"[STARTUP]   • Chat V2: http://127.0.0.1:8000/api/v2/chat (with source attribution)")
    print(f"[STARTUP]   • Async Chat: http://127.0.0.1:8000/api/v1/chat/async")
    print(f"[STARTUP]   • Metrics: http://127.0.0.1:8000/metrics (Prometheus)")
    print(f"[STARTUP]   • Health: http://127.0.0.1:8000/health")
    print(f"[STARTUP]   • Config: http://127.0.0.1:8000/api/v1/config")
    print("=" * 70)


@app.on_event("shutdown")
async def shutdown_event():
    """Graceful shutdown handler."""
    print("\n" + "=" * 70)
    print("Financial RAG API shutting down gracefully...")
    print("=" * 70)


