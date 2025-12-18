"""
Financial Insights Module - Generate analytics from S&P 500 data

Provides aggregated metrics, trends, comparisons without database dependency.
Uses S&P 500 CSV data and company information with caching.
"""

from typing import Dict, Any, List, Optional
import time

from app.core.response_utils import (
    analytics_response,
    merge_date_range,
    normalize_records,
    safe_int,
    safe_number,
)

# Cache results for 5 minutes
_insight_cache = {}
_cache_timestamps = {}
CACHE_DURATION = 300  # 5 minutes


def _meta_stub(aggregation: str, start: Optional[Any] = None, end: Optional[Any] = None) -> Dict[str, Any]:
    return {
        "company": "SP500 Index",
        "date_range": merge_date_range(start, end),
        "aggregation": aggregation,
    }

def _is_cache_valid(key: str) -> bool:
    """Check if cached data is still valid."""
    if key not in _cache_timestamps:
        return False
    return (time.time() - _cache_timestamps[key]) < CACHE_DURATION

def _get_cached(key: str) -> Optional[Any]:
    """Get cached data if valid."""
    if _is_cache_valid(key):
        return _insight_cache.get(key)
    return None

def _set_cache(key: str, value: Any):
    """Set cache with timestamp."""
    _insight_cache[key] = value
    _cache_timestamps[key] = time.time()


def get_database_summary() -> Dict[str, Any]:
    """Get overview statistics of S&P 500 data."""
    cached = _get_cached("summary")
    if cached:
        return cached

    try:
        from app.core.sp500_analytics import get_sp500_summary
        from app.core.sp500_companies import get_sp500_companies

        sp500_summary = get_sp500_summary()
        companies = get_sp500_companies(limit=50)

        meta = sp500_summary.get("meta") or _meta_stub("daily")
        summary = {
            **sp500_summary.get("summary", {}),
            "total_companies": safe_int(len(companies), 0),
            "status": "ok",
        }

        company_rows = [
            {
                "ticker": c.get("ticker"),
                "name": c.get("name"),
                "sector": c.get("sector", "Unknown"),
                "revenue": c.get("revenue"),
                "market_cap": c.get("market_cap"),
            }
            for c in (companies or [])
        ]

        payload = analytics_response(
            meta=meta,
            data=normalize_records(company_rows, numeric_fields=("revenue", "market_cap")),
            summary=summary,
        )
        _set_cache("summary", payload)
        return payload
    except Exception as exc:
        return analytics_response(
            meta=_meta_stub("daily"),
            data=[],
            summary={"status": "error"},
            errors=[str(exc)],
        )


def get_revenue_leaders(limit: int = 10) -> Dict[str, Any]:
    """Get S&P 500 companies by market cap (top companies)."""
    cache_key = f"revenue_leaders_{limit}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        from app.core.sp500_companies import get_top_companies_by_revenue

        top_companies = get_top_companies_by_revenue(limit=min(limit, 20))
        rows = normalize_records(
            [
                {
                    "ticker": c.get("ticker"),
                    "name": c.get("name"),
                    "sector": c.get("sector", "Technology"),
                    "revenue": c.get("revenue"),
                    "market_cap": c.get("market_cap"),
                }
                for c in (top_companies or [])
            ],
            numeric_fields=("revenue", "market_cap"),
        )
        status = "ok" if rows else "no-data"
        payload = analytics_response(
            meta=_meta_stub("companies"),
            data=rows,
            summary={"record_count": safe_int(len(rows), 0), "status": status},
        )
        _set_cache(cache_key, payload)
        return payload
    except Exception as exc:
        return analytics_response(
            meta=_meta_stub("companies"),
            data=[],
            summary={"status": "error"},
            errors=[str(exc)],
        )


def get_profitability_metrics(limit: int = 10) -> Dict[str, Any]:
    """Get companies with best performance metrics."""
    cache_key = f"profitability_{limit}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        from app.core.sp500_analytics import get_sp500_growth_analysis

        growth_data = get_sp500_growth_analysis()
        analysis_rows = growth_data.get("data", []) if isinstance(growth_data, dict) else []

        rows = []
        for idx, item in enumerate(analysis_rows[: min(limit, 15)]):
            return_pct = safe_number(item.get("return_pct"))
            rows.append(
                {
                    "rank": idx + 1,
                    "period": item.get("period"),
                    "return_pct": return_pct,
                    "growth": "Strong" if (return_pct or 0) > 0 else "Weak",
                }
            )

        status = "ok" if rows else "no-data"
        payload = analytics_response(
            meta=growth_data.get("meta") if isinstance(growth_data, dict) else _meta_stub("yearly"),
            data=rows,
            summary={"record_count": safe_int(len(rows), 0), "status": status},
            errors=growth_data.get("summary", {}).get("errors") if isinstance(growth_data, dict) else None,
        )
        _set_cache(cache_key, payload)
        return payload
    except Exception as exc:
        return analytics_response(
            meta=_meta_stub("yearly"),
            data=[],
            summary={"status": "error"},
            errors=[str(exc)],
        )


def get_growth_trends(ticker: str) -> Dict[str, Any]:
    """Get growth trends for S&P 500."""
    cache_key = f"growth_trends_{ticker}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        from app.core.sp500_analytics import get_sp500_growth_analysis

        growth_data = get_sp500_growth_analysis()
        rows = growth_data.get("data", [])[:12] if isinstance(growth_data, dict) else []
        payload = analytics_response(
            meta=growth_data.get("meta") if isinstance(growth_data, dict) else _meta_stub("yearly"),
            data=rows,
            summary={
                "status": "ok" if rows else "no-data",
                "record_count": safe_int(len(rows), 0),
                "ticker": ticker.upper(),
            },
            errors=growth_data.get("summary", {}).get("errors") if isinstance(growth_data, dict) else None,
        )
        _set_cache(cache_key, payload)
        return payload
    except Exception as exc:
        return analytics_response(
            meta=_meta_stub("yearly"),
            data=[],
            summary={"status": "error", "ticker": ticker.upper()},
            errors=[str(exc)],
        )


def get_sector_comparison() -> Dict[str, Any]:
    """Compare performance across top S&P 500 companies."""
    cached = _get_cached("sector_comparison")
    if cached:
        return cached

    try:
        from app.core.sp500_companies import get_sp500_companies

        top_companies = get_sp500_companies(limit=20)
        rows = []
        for idx, company in enumerate(top_companies[:10] if top_companies else []):
            rows.append(
                {
                    "rank": idx + 1,
                    "ticker": company.get("ticker"),
                    "name": company.get("name"),
                    "sector": company.get("sector", "N/A"),
                    "performance": "Strong" if idx < 5 else "Stable",
                }
            )

        payload = analytics_response(
            meta=_meta_stub("sector"),
            data=rows,
            summary={"record_count": safe_int(len(rows), 0), "status": "ok" if rows else "no-data"},
        )
        _set_cache("sector_comparison", payload)
        return payload
    except Exception as exc:
        return analytics_response(
            meta=_meta_stub("sector"),
            data=[],
            summary={"status": "error"},
            errors=[str(exc)],
        )

