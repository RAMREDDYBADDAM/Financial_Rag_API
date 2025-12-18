"""Response helpers for consistent backend -> frontend contracts.

Provides utilities to sanitize numeric values, enforce analytics payload
structure, and safely represent date ranges.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional
import math

AnalyticsMeta = Dict[str, Any]
AnalyticsPayload = Dict[str, Any]


def safe_number(value: Any, default: Optional[float] = None) -> Optional[float]:
    """Coerce any numeric-ish input into a finite float or return default."""
    if value is None:
        return default

    if isinstance(value, bool):  # treat booleans separately to avoid bool -> int
        return float(value)

    if isinstance(value, (int, float, Decimal)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result

    try:
        result = float(str(value).strip())
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    number = safe_number(value, None)
    if number is None:
        return default
    return int(number)


def iso_date(value: Any) -> Optional[str]:
    """Return ISO 8601 string for datetime/date or passthrough valid strings."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        candidate = value.strip()
        return candidate or None
    return None


def merge_date_range(
    start: Optional[Any], end: Optional[Any]
) -> Dict[str, Optional[str]]:
    """Create a canonical date_range dict."""
    return {"start": iso_date(start), "end": iso_date(end)}


def default_meta() -> AnalyticsMeta:
    return {"company": None, "date_range": {"start": None, "end": None}, "aggregation": None}


def analytics_response(
    *,
    meta: Optional[AnalyticsMeta] = None,
    data: Optional[List[Dict[str, Any]]] = None,
    summary: Optional[Dict[str, Any]] = None,
    errors: Optional[List[str]] = None,
) -> AnalyticsPayload:
    """Return payload with enforced structure."""
    payload = {
        "meta": {**default_meta(), **(meta or {})},
        "data": data or [],
        "summary": summary or {},
    }
    if errors:
        payload["summary"]["errors"] = errors
    return payload


def normalize_records(
    records: Iterable[Dict[str, Any]],
    numeric_fields: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    """Return shallow copies of records with numeric fields sanitized."""
    normalized: List[Dict[str, Any]] = []
    numeric_fields = set(numeric_fields or [])
    for record in records:
        cleaned = {}
        for key, value in record.items():
            if key in numeric_fields:
                cleaned[key] = safe_number(value)
            else:
                cleaned[key] = value
        normalized.append(cleaned)
    return normalized


def summarize_missing_counts(counts: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Convert a map of missing/null counts into safe floats."""
    return {key: safe_number(value, 0.0) for key, value in counts.items()}
