"""FastAPI server for Financial RAG application.

WINDOWS SAFETY NOTE:
- This server should start exactly ONE time
- If multiple processes bind to port 8000, restart with: taskkill /F /IM python.exe
- serve.py includes guards to detect and prevent multiple instances
"""
# Fix OpenMP duplicate runtime warning (common with ML libraries like numpy+mkl)
import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("OMP_NUM_THREADS", "4")

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from typing import Any, Dict
import traceback
from functools import lru_cache
from datetime import datetime, timedelta

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

# CORS middleware for browser requests
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Financial RAG API")

# RECOVERY FIX: Add CORS middleware to allow browser requests from any origin
# This fixes "Failed to fetch" errors when dashboard.html calls the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve a minimal web UI from the repository `web/` directory.
web_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "web"))
if os.path.isdir(web_dir):
    app.mount("/static", StaticFiles(directory=web_dir), name="static")


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


class ChatRequest(BaseModel):
    user_id: str
    question: str


class ChatResponse(BaseModel):
    answer: str
    query_type: str
    router: Dict[str, Any]


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """Async endpoint that runs the (potentially blocking) chain in a worker thread.

    Running the whole orchestration in a worker thread prevents blocking the
    event loop and avoids issues with uvicorn's reload and asyncio cancellations.
    """
    try:
        result = await anyio.to_thread.run_sync(answer_financial_question, req.question)
        return ChatResponse(
            answer=result.get("answer", ""),
            query_type=result.get("query_type", "UNKNOWN"),
            router=result.get("router", {}),
        )
    except Exception as e:
        error_msg = f"Server error: {str(e)}"
        return ChatResponse(
            answer=error_msg,
            query_type="ERROR",
            router={"error": str(e), "traceback": traceback.format_exc()},
        )


@app.get("/health")
def health_check():
    return {"status": "ok"}


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


@app.on_event("startup")
async def startup_event():
    """Startup event handler - verify LLM connection and system health."""
    import os as _os
    _pid = _os.getpid()
    
    print("=" * 70)
    print(f"Financial RAG API starting up (PID: {_pid})")
    print("=" * 70)
    print(f"[STARTUP] Process ID: {_pid} - THIS IS THE ONLY PROCESS THAT SHOULD EXIST")
    print(f"[STARTUP] If you see multiple PIDs on port 8000, restart with:")
    print(f"[STARTUP]   tasklist | findstr python")
    print(f"[STARTUP]   taskkill /PID <pid> /F")
    
    # Verify Ollama LLM connection
    try:
        from app.core.llm import _check_ollama_health
        from app.config import settings
        
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
    
    print(f"\n[STARTUP] API ready at http://127.0.0.1:8000")
    print("=" * 70)
    print("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    # Placeholder for graceful shutdown tasks
    print("Financial RAG API shutting down")


