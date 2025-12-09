from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from typing import Any, Dict
import os
import traceback

import anyio

from app.core.chains import answer_financial_question
from app.core.plot_generator import generate_plot_from_rag_output

app = FastAPI(title="Financial RAG API")

# Serve a minimal web UI from the repository `web/` directory.
web_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "web"))
if os.path.isdir(web_dir):
    app.mount("/static", StaticFiles(directory=web_dir), name="static")


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


@app.get("/")
def root_index():
    index_path = os.path.join(web_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Financial RAG API is running. No web UI found."}


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
            "note": "Demo extraction — replace with real parser",
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


@app.on_event("startup")
async def startup_event():
    # Placeholder for any async startup tasks (DB connections, metrics, etc.)
    print("⚡ Financial RAG API starting up")


@app.on_event("shutdown")
async def shutdown_event():
    # Placeholder for graceful shutdown tasks
    print("⚡ Financial RAG API shutting down")

