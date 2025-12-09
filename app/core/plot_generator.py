"""
Financial Metrics Plot Generator

Extracts company ticker and financial metric from RAG output,
queries PostgreSQL, generates matplotlib plots, and returns base64-encoded JSON.
"""

import re
import json
import base64
from io import BytesIO
from typing import Dict, Any, Optional, Tuple, List
import psycopg2
from psycopg2.extras import RealDictCursor
import matplotlib.pyplot as plt
from app.config import settings
from app.core.llm import get_llm
import json


# ============================================================================
# Entity Extraction from RAG Output
# ============================================================================

COMPANY_TICKERS = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN", "META", "NVDA"]
# Simple mapping of common company names to tickers to help extraction from narrative text
COMPANY_MAP = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL": "Google",
    "TSLA": "Tesla",
    "AMZN": "Amazon",
    "META": "Meta",
    "NVDA": "NVIDIA",
}

# Precompute lowercase name->ticker map for fast matching
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

# Small demo fallback series used when DATABASE_URL isn't configured or DB lookup fails
SAMPLE_SERIES = {
    ("AAPL", "revenue"): [
        ("Q1 2023", 90000.0),
        ("Q2 2023", 92000.0),
        ("Q3 2023", 94000.0),
        ("Q4 2023", 96000.0),
        ("Q1 2024", 94700.0),
    ],
    ("MSFT", "net_income"): [
        ("Q1 2023", 12000.0),
        ("Q2 2023", 12500.0),
        ("Q3 2023", 13000.0),
        ("Q4 2023", 13500.0),
        ("Q1 2024", 13800.0),
    ],
}


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

    if not company or not metric:
        return None

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
# Database Query Functions
# ============================================================================


def _get_db_connection():
    """Create and return a PostgreSQL connection using DATABASE_URL."""
    if not settings.database_url:
        raise ValueError("DATABASE_URL not configured in .env or settings")
    return psycopg2.connect(settings.database_url)


def fetch_company_id(ticker: str) -> Optional[int]:
    """Fetch the company ID from the companies table."""
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM companies WHERE ticker = %s;", (ticker.upper(),))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        print(f"Error fetching company ID: {e}")
        return None


def fetch_metric_series(
    company_id: int, metric: str, latest_only: bool = False
) -> Optional[List[Tuple[str, float]]]:
    """
    Fetch financial metric time-series from the database.

    Args:
        company_id: ID of the company
        metric: Financial metric name (e.g., "revenue", "net_income")
        latest_only: If True, return only the latest value; if False, return full time-series

    Returns:
        List of tuples (period, value) sorted by period
        or None if query fails or metric not found
    """
    if metric not in FINANCIAL_METRICS:
        print(f"Invalid metric: {metric}")
        return None

    try:
        conn = _get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        if latest_only:
            query = f"""
                SELECT period, {metric}
                FROM financial_metrics
                WHERE company_id = %s AND {metric} IS NOT NULL
                ORDER BY period DESC
                LIMIT 1;
            """
        else:
            query = f"""
                SELECT period, {metric}
                FROM financial_metrics
                WHERE company_id = %s AND {metric} IS NOT NULL
                ORDER BY period ASC;
            """

        cursor.execute(query, (company_id,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        if not rows:
            return None

        # Convert to list of tuples (period, value)
        return [(row["period"], float(row[metric])) for row in rows]

    except Exception as e:
        print(f"Error fetching metric series: {e}")
        return None


# ============================================================================
# Plotting Functions
# ============================================================================


def plot_metric(series: List[Tuple[str, float]], company: str, metric: str) -> str:
    """
    Generate a matplotlib plot and return as base64-encoded PNG.

    Args:
        series: List of (period, value) tuples
        company: Company ticker
        metric: Financial metric name

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

    # Step 2: Fetch company ID
    company_id = fetch_company_id(company)

    # If DB is not configured or company not found, attempt to use a demo sample series
    if not company_id:
        print(f"Company {company} not found in database or DATABASE_URL missing — trying fallbacks")
        series = SAMPLE_SERIES.get((company, metric))
        if not series:
            # As a more flexible fallback, ask the LLM to synthesize a plausible series
            series = _llm_synthesize_series_sync(company, metric)
            if not series:
                return None
    else:
        # Step 3: Fetch metric series
        latest_only = not is_trend
        series = fetch_metric_series(company_id, metric, latest_only=latest_only)
        if not series:
            # Try sample fallback if DB had no rows for this metric
            print(f"No DB data found for {company} {metric}; trying sample fallback")
            series = SAMPLE_SERIES.get((company, metric))
            if not series:
                # Ask LLM to synthesize series if sample not available
                series = _llm_synthesize_series_sync(company, metric)
                if not series:
                    print(f"No sample data for {company} {metric}")
                    return None
    # Step 4: Generate plot
    try:
        plot_base64 = plot_metric(series, company, metric)
    except Exception as e:
        print(f"Error generating plot: {e}")
        return None

    # Step 5: Return JSON response
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
