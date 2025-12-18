"""
Financial Metrics Plot Generator

Generates matplotlib plots from S&P 500 historical data (CSV-based).
No external database required - uses local CSV fallback with sample data.
"""

import re
import json
import base64
from io import BytesIO
from typing import Dict, Any, Optional, Tuple, List
import matplotlib
matplotlib.use('Agg')  # Use non-GUI backend to avoid threading issues in async context
import matplotlib.pyplot as plt
from app.config import settings
from app.core.llm import get_llm
import os

# Import S&P 500 analytics to get historical data
try:
    from app.core.sp500_analytics import (
        get_sp500_summary,
        get_time_series_data,
        get_sp500_growth_analysis,
        get_sp500_data,
        get_volatility_analysis,
        get_decade_performance,
        get_year_over_year_growth,
    )
    SP500_ANALYTICS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import all sp500_analytics functions: {e}")
    SP500_ANALYTICS_AVAILABLE = False


# ============================================================================
# Constants for Entity Extraction
# ============================================================================

COMPANY_TICKERS = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN", "META", "NVDA"]
COMPANY_MAP = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL": "Google",
    "TSLA": "Tesla",
    "AMZN": "Amazon",
    "META": "Meta",
    "NVDA": "NVIDIA",
}
NAME_TO_TICKER = {v.lower(): k for k, v in COMPANY_MAP.items()}
FINANCIAL_METRICS = [
    "revenue",
    "net_income",
    "operating_income",
    "eps",
    "total_assets",
    "total_liabilities",
    "equity",
]


def extract_plot_params(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract company ticker, financial metric, and trend preference from RAG output.

    Returns:
        Dict with keys: company, metric, is_trend (bool)
        or None if extraction fails.
    """
    text_lower = text.lower()

    # Extract company ticker (case-insensitive) or company name
    company = None
    # 1) direct ticker mention
    for ticker in COMPANY_TICKERS:
        if ticker.lower() in text_lower:
            company = ticker
            break
    # 2) company name mention (e.g., "Apple", "Microsoft")
    if not company:
        for name_lower, ticker in NAME_TO_TICKER.items():
            # match whole word sequences to avoid false positives
            if re.search(r"\b" + re.escape(name_lower) + r"\b", text_lower):
                company = ticker
                break

    # Extract financial metric
    metric = None
    for m in FINANCIAL_METRICS:
        if m.lower() in text_lower or m.replace("_", " ").lower() in text_lower:
            metric = m
            break

    # Determine if user wants trend (time-series) vs. latest value
    trend_keywords = ["trend", "growth", "over time", "historical", "compare", "change"]
    is_trend = any(kw in text_lower for kw in trend_keywords)

    if not company:
        company = "SP500"
    if not metric:
        metric = "close"

    return {
        "company": company,
        "metric": metric,
        "is_trend": is_trend,
    }


def _llm_infer_params_sync(text: str) -> Optional[Dict[str, Any]]:
    """Ask the configured LLM to extract company ticker and metric from text.

    This is a synchronous helper meant to be run in a worker thread by the
    FastAPI endpoint. It is resilient to different LLM return types.
    """
    try:
        llm = get_llm()
        prompt = (
            "Extract a single JSON object with keys: company (ticker like AAPL),"
            " metric (one of revenue, net_income, eps, etc.), and is_trend (true/false)."
            " Only return JSON. Example: {\"company\":\"AAPL\",\"metric\":\"revenue\",\"is_trend\":true}"
            f"\n\nText:\n{text}"
        )

        # Invoke according to common interfaces
        try:
            if hasattr(llm, "invoke"):
                resp = llm.invoke(prompt)
                content = resp.get("content") if isinstance(resp, dict) else getattr(resp, "content", None)
            else:
                resp = llm(prompt)
                content = resp.get("content") if isinstance(resp, dict) else getattr(resp, "content", None)
        except Exception:
            # Last resort: string conversion
            resp = llm.invoke(prompt) if hasattr(llm, "invoke") else llm(prompt)
            content = resp.get("content") if isinstance(resp, dict) else str(resp)

        if not content:
            content = str(resp)

        # Try to parse JSON directly
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "company" in parsed and "metric" in parsed:
                return {"company": parsed.get("company"), "metric": parsed.get("metric"), "is_trend": parsed.get("is_trend", True)}
        except Exception:
            # Try to find ticker and metric with regex as fallback
            text_lower = content.lower()
            # ticker pattern e.g., AAPL
            import re
            m = re.search(r"\b([A-Z]{2,5})\b", content)
            ticker = m.group(1) if m else None
            metric = None
            for met in FINANCIAL_METRICS:
                if met.lower() in text_lower or met.replace("_", " ") in text_lower:
                    metric = met
                    break
            if ticker and metric:
                return {"company": ticker, "metric": metric, "is_trend": any(k in text_lower for k in ["trend", "growth"]) }

    except Exception as e:
        print(f"LLM param inference failed: {e}")
    return None


def _llm_synthesize_series_sync(company: str, metric: str, points: int = 5) -> Optional[List[Tuple[str, float]]]:
    """Ask the LLM to synthesize a plausible time-series for plotting.

    Returns a list of (period, value) tuples or None.
    """
    try:
        llm = get_llm()
        prompt = (
            f"Provide a JSON array of {points} quarterly periods (period,value) for {company} "
            f"showing plausible {metric} values. Return JSON like: [{'{'}\"period\":\"Q1 2023\",\"value\":90000{'}'}, ...]."
        )
        try:
            if hasattr(llm, "invoke"):
                resp = llm.invoke(prompt)
                content = resp.get("content") if isinstance(resp, dict) else getattr(resp, "content", None)
            else:
                resp = llm(prompt)
                content = resp.get("content") if isinstance(resp, dict) else getattr(resp, "content", None)
        except Exception:
            resp = llm.invoke(prompt) if hasattr(llm, "invoke") else llm(prompt)
            content = resp.get("content") if isinstance(resp, dict) else str(resp)

        if not content:
            content = str(resp)

        # Parse JSON array
        try:
            arr = json.loads(content)
            series = []
            for item in arr:
                if isinstance(item, dict) and "period" in item and "value" in item:
                    series.append((item["period"], float(item["value"])))
            if series:
                return series
        except Exception:
            # Try to parse lines like: Q1 2023: 90000
            lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
            parsed = []
            import re
            for ln in lines:
                m = re.search(r"(Q[1-4]\s*\d{4}|[A-Za-z]{3,}\s*\d{4})[:\-]?\s*([0-9,.]+)", ln)
                if m:
                    period = m.group(1)
                    value = float(m.group(2).replace(",", ""))
                    parsed.append((period, value))
            if parsed:
                return parsed

    except Exception as e:
        print(f"LLM synthesize failed: {e}")
    return None


# ============================================================================
# S&P 500 Data Functions (CSV-based, no DB required)
# ============================================================================

def _get_sp500_plot_data() -> Optional[List[Tuple[str, float]]]:
    """Get S&P 500 historical data as time-series for plotting."""
    if not SP500_ANALYTICS_AVAILABLE:
        return None
    
    try:
        # Get S&P 500 timeseries data using get_time_series_data
        ts_result = get_time_series_data(
            start_date=None,
            end_date=None,
            metrics=["date", "sp500"],
            limit=200
        )
        
        if ts_result.get("success") and "data" in ts_result:
            data_rows = ts_result["data"]
            # Build list of (date_str, sp500_value) tuples
            series = []
            for row in data_rows:
                date_val = row.get("date")
                sp500_val = row.get("sp500")
                if date_val and sp500_val is not None:
                    series.append((str(date_val), float(sp500_val)))
            
            # Return tail of 100-200 points
            return series[-150:] if len(series) > 150 else series
    except Exception as e:
        print(f"Error fetching S&P 500 data: {e}")
    
    return None


# Small fallback sample series if CSV not available
SAMPLE_SERIES = {
    ("SP500", "close"): [
        ("2023-Q1", 3750.0),
        ("2023-Q2", 3850.0),
        ("2023-Q3", 4000.0),
        ("2023-Q4", 4100.0),
        ("2024-Q1", 4200.0),
    ],
}


# ============================================================================
# Plotting Functions
# ============================================================================


def plot_metric(series: List[Tuple[str, float]], company: str, metric: str) -> str:
    """
    Generate a matplotlib plot and return as base64-encoded PNG.

    Args:
        series: List of (period, value) tuples
        company: Company ticker or description
        metric: Metric name

    Returns:
        Base64-encoded PNG string
    """
    if not series:
        raise ValueError("Empty series data")

    periods, values = zip(*series)

    # Create figure and plot
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(periods, values, marker="o", linewidth=2, markersize=8, color="#2563eb")
    ax.grid(True, alpha=0.3)
    ax.set_xlabel("Period", fontsize=12)
    ax.set_ylabel(metric.replace("_", " ").capitalize(), fontsize=12)
    ax.set_title(f"{company} - {metric.replace('_', ' ').capitalize()} Trend", fontsize=14)
    ax.tick_params(axis="x", rotation=45)
    plt.tight_layout()

    # Convert to base64
    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=100)
    buffer.seek(0)
    plt.close(fig)

    plot_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return plot_base64



# ============================================================================
# Main Orchestrator
# ============================================================================


def generate_plot_from_rag_output(rag_text: str) -> Optional[Dict[str, Any]]:
    """
    Complete pipeline: extract params → fetch data → plot → return JSON.
    
    Uses S&P 500 historical data (CSV-based) - no external database required.

    Args:
        rag_text: Natural-language output from RAG model

    Returns:
        JSON dict with company, metric, and plot_base64
        or None if any step fails
    """
    # Step 1: Extract parameters from RAG text
    params = extract_plot_params(rag_text)
    if not params:
        # Try asking the LLM to infer the parameters
        params = _llm_infer_params_sync(rag_text)
        if not params:
            print("Could not extract company or metric from RAG output")
            return None

    company = params["company"]
    metric = params["metric"]
    is_trend = params.get("is_trend", True)

    # Step 2: Try to fetch S&P 500 data
    series = _get_sp500_plot_data()
    if not series:
        # Try sample fallback if S&P 500 data unavailable
        series = SAMPLE_SERIES.get(("SP500", "close"))
        if not series:
            print(f"Could not fetch plot data for {company}")
            return None

    # Step 3: Generate plot
    try:
        plot_base64 = plot_metric(series, f"S&P 500 ({company})", metric)
    except Exception as e:
        print(f"Error generating plot: {e}")
        return None

    # Step 4: Return JSON response
    return {
        "company": company,
        "metric": metric,
        "data_points": len(series),
        "is_trend": is_trend,
        "plot_base64": plot_base64,
    }


# ============================================================================
# Testing / Demo
# ============================================================================

if __name__ == "__main__":
    # Example RAG output
    example_rag_output = """
    Apple Inc. (AAPL) has shown consistent revenue growth over the past quarters.
    In Q1 2024, the company reported strong financial performance with increasing net income.
    The trend shows positive momentum in the Technology sector.
    """

    result = generate_plot_from_rag_output(example_rag_output)
    if result:
        print("Success!")
        print(f"Company: {result['company']}")
        print(f"Metric: {result['metric']}")
        print(f"Data points: {result['data_points']}")
        print(f"Plot base64 length: {len(result['plot_base64'])}")
    else:
        print("Failed to generate plot")
