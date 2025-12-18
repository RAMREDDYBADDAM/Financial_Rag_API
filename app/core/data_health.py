"""Data availability and quality diagnostics exposed via /api/health/data."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor

from app.config import settings
from app.core.response_utils import (
    analytics_response,
    merge_date_range,
    safe_int,
    summarize_missing_counts,
)
from app.core.sp500_analytics import get_sp500_data


def _sp500_source_report() -> Optional[Dict[str, Any]]:
    df = get_sp500_data()
    if df is None or df.empty:
        return None

    date_start = df["date"].min() if "date" in df.columns else None
    date_end = df["date"].max() if "date" in df.columns else None
    numeric_cols = [col for col in df.columns if col != "date"]
    missing_counts = {col: int(df[col].isna().sum()) for col in numeric_cols}

    return {
        "source": "sp500_csv",
        "tables": ["sample_financial_data.csv"],
        "rows": safe_int(len(df), 0),
        "date_range": merge_date_range(date_start, date_end),
        "missing_metrics": summarize_missing_counts(missing_counts),
        "loaded": True,
    }


def _detect_financial_metrics_date_column(cursor) -> Optional[str]:
    cursor.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'financial_metrics'
        """
    )
    available = {row[0] for row in cursor.fetchall()}
    for candidate in ("period_end", "period", "date", "period_start"):
        if candidate in available:
            return candidate
    return None


def _database_source_report() -> Dict[str, Any]:
    if not settings.database_url:
        return {
            "source": "postgres",
            "tables": [],
            "loaded": False,
            "error": "DATABASE_URL not configured",
        }

    try:
        conn = psycopg2.connect(settings.database_url)
        cursor = conn.cursor()
    except Exception as exc:
        return {
            "source": "postgres",
            "tables": [],
            "loaded": False,
            "error": f"Connection failed: {exc}",
        }

    tables_of_interest = [
        "companies",
        "financial_metrics",
        "quarterly_reports",
        "products",
        "analyst_ratings",
        "market_trends",
    ]

    table_reports: List[Dict[str, Any]] = []
    global_start = None
    global_end = None

    for table in tables_of_interest:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            report: Dict[str, Any] = {
                "name": table,
                "rows": safe_int(count, 0),
            }

            if table == "financial_metrics":
                date_column = _detect_financial_metrics_date_column(cursor)
                if date_column:
                    cursor.execute(
                        f"SELECT MIN({date_column}), MAX({date_column}) FROM {table}"
                    )
                    min_val, max_val = cursor.fetchone()
                    report["date_range"] = merge_date_range(min_val, max_val)
                    if min_val is not None:
                        if global_start is None or min_val < global_start:
                            global_start = min_val
                    if max_val is not None:
                        if global_end is None or max_val > global_end:
                            global_end = max_val
            table_reports.append(report)
        except Exception as exc:  # pragma: no cover - defensive
            table_reports.append({
                "name": table,
                "rows": 0,
                "error": str(exc),
            })

    cursor.close()
    conn.close()

    return {
        "source": "postgres",
        "tables": table_reports,
        "loaded": True,
        "date_range": merge_date_range(global_start, global_end),
    }


def collect_data_health() -> Dict[str, Any]:
    """Gather diagnostics for CSV + database sources."""
    sources: List[Dict[str, Any]] = []
    issues: List[str] = []
    global_start = None
    global_end = None

    sp500_report = _sp500_source_report()
    if sp500_report:
        sources.append(sp500_report)
        dr = sp500_report.get("date_range") or {}
        global_start = dr.get("start") if global_start is None else global_start
        global_end = dr.get("end") if global_end is None else global_end
    else:
        issues.append("S&P 500 CSV not loaded")

    db_report = _database_source_report()
    sources.append(db_report)
    db_range = db_report.get("date_range")
    if db_range:
        global_start = global_start or db_range.get("start")
        global_end = global_end or db_range.get("end")

    summary = {
        "sources_checked": len(sources),
        "issues": issues,
        "database_loaded": db_report.get("loaded", False),
    }

    meta = {
        "company": None,
        "date_range": merge_date_range(global_start, global_end),
        "aggregation": "data-health",
    }

    return analytics_response(meta=meta, data=sources, summary=summary, errors=issues if issues else None)
