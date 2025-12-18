"""
S&P 500 Analytics Module - Advanced time-series analysis and visualization

Provides comprehensive analytics for S&P 500 historical data including:
- Time-series analysis
- Statistical metrics
- Correlation analysis
- Trend detection
- Comparative analysis
"""

from typing import Dict, Any, List, Optional
import pandas as pd
from datetime import datetime, timedelta
from app.config import settings
import os

from app.core.response_utils import (
    analytics_response,
    merge_date_range,
    safe_int,
    safe_number,
)

# In-memory cache for S&P 500 data
_sp500_cache = None


def _ensure_datetime(df: pd.DataFrame) -> pd.DataFrame:
    if 'date' in df.columns and df['date'].dtype == 'object':
        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])
    return df


def _meta_for_df(df: pd.DataFrame, aggregation: str) -> Dict[str, Any]:
    df = _ensure_datetime(df)
    start = df['date'].min() if 'date' in df.columns and not df.empty else None
    end = df['date'].max() if 'date' in df.columns and not df.empty else None
    return {
        "company": "SP500 Index",
        "date_range": merge_date_range(start, end),
        "aggregation": aggregation,
    }


def _load_sp500_from_csv() -> Optional[pd.DataFrame]:
    """Try to load S&P 500 data from local CSV file."""
    try:
        csv_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "sample_financial_data.csv")
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            df = df.rename(columns={
                'Date': 'date',
                'SP500': 'sp500',
                'Dividend': 'dividend',
                'Earnings': 'earnings',
                'Consumer Price Index': 'consumer_price_index',
                'Long Interest Rate': 'long_interest_rate',
                'Real Price': 'real_price',
                'Real Dividend': 'real_dividend',
                'Real Earnings': 'real_earnings',
                'PE10': 'pe10'
            })
            df.columns = df.columns.str.lower()
            # Handle mixed date formats (with/without time component)
            df['date'] = pd.to_datetime(df['date'], format='mixed')
            return df
    except Exception as e:
        print(f"Error loading CSV: {e}")
    return None


def get_sp500_data() -> pd.DataFrame:
    """Get S&P 500 data from cache or CSV."""
    global _sp500_cache
    
    if _sp500_cache is not None and not _sp500_cache.empty:
        return _sp500_cache
    
    # Try loading from CSV first
    df = _load_sp500_from_csv()
    if df is not None and not df.empty:
        _sp500_cache = df
        return df
    
    # Return empty DataFrame as fallback
    return pd.DataFrame()


def ingest_sp500_data(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Ingest S&P 500 CSV data into cache (and optionally PostgreSQL).
    """
    global _sp500_cache
    
    try:
        # Standardize column names
        df.columns = df.columns.str.lower()
        _sp500_cache = df.copy()
        
        return {
            "success": True,
            "rows_inserted": len(df),
            "message": f"Loaded {len(df)} S&P 500 records into cache"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Ingestion failed: {str(e)}"
        }


def get_sp500_summary() -> Dict[str, Any]:
    """Get S&P 500 data summary."""
    df = get_sp500_data()
    
    if df is None or df.empty:
        return analytics_response(
            meta=_meta_for_df(pd.DataFrame(columns=['date']), "daily"),
            data=[],
            summary={"status": "no-data"},
            errors=["No S&P 500 data available. Please upload the CSV file first."],
        )
    
    try:
        df = _ensure_datetime(df)
        latest_idx = -1 if len(df) > 0 else None
        latest_values = {}
        for metric in ("sp500", "dividend", "pe10"):
            if metric in df.columns and latest_idx is not None:
                latest_values[metric] = safe_number(df[metric].iloc[latest_idx])
            else:
                latest_values[metric] = None

        numeric_cols = [
            "sp500",
            "dividend",
            "earnings",
            "consumer_price_index",
            "long_interest_rate",
            "real_price",
            "real_dividend",
            "real_earnings",
            "pe10",
        ]
        stats_rows: List[Dict[str, Any]] = []
        for col in numeric_cols:
            if col not in df.columns:
                continue
            col_series = pd.to_numeric(df[col], errors='coerce')
            stats_rows.append(
                {
                    "metric": col,
                    "avg": safe_number(col_series.mean()),
                    "min": safe_number(col_series.min()),
                    "max": safe_number(col_series.max()),
                    "stddev": safe_number(col_series.std()),
                }
            )

        summary = {
            "latest_values": latest_values,
            "record_count": safe_int(len(df), 0),
            "status": "ok",
        }

        return analytics_response(meta=_meta_for_df(df, "daily"), data=stats_rows, summary=summary)
    except Exception as e:
        return analytics_response(
            meta=_meta_for_df(df, "daily"),
            data=[],
            summary={"status": "error"},
            errors=[f"Failed to calculate summary: {e}"],
        )


def get_time_series_data(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    metrics: Optional[List[str]] = None,
    limit: int = 1000
) -> Dict[str, Any]:
    """Get time-series data with optional filtering."""
    df = get_sp500_data()
    
    if df is None or df.empty:
        return analytics_response(
            meta=_meta_for_df(pd.DataFrame(columns=['date']), "daily"),
            data=[],
            summary={"status": "no-data"},
            errors=["No S&P 500 data available"],
        )
    
    try:
        df = _ensure_datetime(df.copy())
        
        if start_date:
            df = df[df['date'] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df['date'] <= pd.to_datetime(end_date)]
        
        metrics = metrics or ['date', 'sp500', 'dividend', 'earnings', 'pe10']
        if 'date' not in metrics:
            metrics = ['date'] + metrics
        available_metrics = [m for m in metrics if m in df.columns]
        df_filtered = df[available_metrics].tail(limit).reset_index(drop=True)
        
        records: List[Dict[str, Any]] = []
        for _, row in df_filtered.iterrows():
            record: Dict[str, Any] = {}
            for col in available_metrics:
                val = row[col]
                if isinstance(val, pd.Timestamp):
                    record[col] = val.strftime("%Y-%m-%d")
                elif pd.isna(val):
                    record[col] = None
                elif isinstance(val, (int, float)):
                    record[col] = safe_number(val)
                else:
                    try:
                        record[col] = safe_number(float(val))
                    except Exception:
                        record[col] = str(val)
            records.append(record)

        summary = {
            "record_count": safe_int(len(records), 0),
            "metrics": available_metrics,
            "status": "ok",
        }

        return analytics_response(meta=_meta_for_df(df_filtered, "daily"), data=records, summary=summary)
    except Exception as e:
        return analytics_response(
            meta=_meta_for_df(df, "daily"),
            data=[],
            summary={"status": "error"},
            errors=[f"Failed to fetch time series: {e}"],
        )


def get_year_over_year_growth() -> Dict[str, Any]:
    """Calculate year-over-year growth rates for S&P 500."""
    df = get_sp500_data()
    
    if df is None or df.empty:
        return analytics_response(
            meta=_meta_for_df(pd.DataFrame(columns=['date']), "yearly"),
            data=[],
            summary={"status": "no-data"},
            errors=["No S&P 500 data available"],
        )
    
    try:
        df = _ensure_datetime(df.copy())
        df['year'] = df['date'].dt.year
        yearly = df.groupby('year').agg({'sp500': 'mean'}).reset_index()
        yearly['yoy_growth'] = yearly['sp500'].pct_change() * 100
        yearly = yearly[yearly['year'] >= 1950].tail(50)

        growth_rows: List[Dict[str, Any]] = []
        for _, row in yearly.iterrows():
            growth_rows.append(
                {
                    "year": int(row['year']),
                    "sp500": safe_number(row['sp500']),
                    "yoy_growth": safe_number(row['yoy_growth']),
                }
            )

        summary = {
            "record_count": safe_int(len(growth_rows), 0),
            "status": "ok",
        }

        # meta date range uses min/max year boundaries
        start_year = growth_rows[0]['year'] if growth_rows else None
        end_year = growth_rows[-1]['year'] if growth_rows else None
        meta = {
            "company": "SP500 Index",
            "date_range": merge_date_range(f"{start_year}-01-01" if start_year else None, f"{end_year}-12-31" if end_year else None),
            "aggregation": "yearly",
        }

        return analytics_response(meta=meta, data=growth_rows, summary=summary)
    except Exception as e:
        return analytics_response(
            meta=_meta_for_df(df, "yearly"),
            data=[],
            summary={"status": "error"},
            errors=[f"Failed to calculate YoY growth: {e}"],
        )


def get_sp500_growth_analysis() -> Dict[str, Any]:
    """Compute annual growth percentages over the last 25 years."""
    df = get_sp500_data()

    if df is None or df.empty:
        return analytics_response(
            meta=_meta_for_df(pd.DataFrame(columns=['date']), "yearly"),
            data=[],
            summary={"status": "no-data"},
            errors=["No S&P 500 data available"],
        )

    try:
        df = _ensure_datetime(df.copy())
        df['year'] = df['date'].dt.year
        yearly = (
            df.groupby('year')['sp500']
            .mean()
            .dropna()
            .reset_index()
            .sort_values('year')
        )
        yearly['return_pct'] = yearly['sp500'].pct_change() * 100

        rows: List[Dict[str, Any]] = []
        for _, row in yearly.tail(25).iterrows():
            rows.append(
                {
                    "period": int(row['year']),
                    "return_pct": safe_number(row['return_pct']) or 0.0,
                }
            )

        summary = {
            "record_count": safe_int(len(rows), 0),
            "status": "ok",
        }
        meta = {
            "company": "SP500 Index",
            "date_range": merge_date_range(
                f"{rows[0]['period']}-01-01" if rows else None,
                f"{rows[-1]['period']}-12-31" if rows else None,
            ),
            "aggregation": "yearly",
        }

        return analytics_response(meta=meta, data=rows, summary=summary)
    except Exception as e:
        return analytics_response(
            meta=_meta_for_df(df, "yearly"),
            data=[],
            summary={"status": "error"},
            errors=[f"Failed to calculate growth analysis: {e}"],
        )


def get_correlation_matrix() -> Dict[str, Any]:
    """Calculate correlation matrix for key metrics."""
    df = get_sp500_data()
    
    if df is None or df.empty:
        return analytics_response(
            meta=_meta_for_df(pd.DataFrame(columns=['date']), "correlation"),
            data=[],
            summary={"status": "no-data"},
            errors=["No S&P 500 data available"],
        )
    
    try:
        df_numeric = df.copy()
        metrics = ['sp500', 'dividend', 'earnings', 'consumer_price_index', 'long_interest_rate', 'pe10']
        df_numeric = df_numeric[[m for m in metrics if m in df_numeric.columns]].apply(pd.to_numeric, errors='coerce')

        rows: List[Dict[str, Any]] = []
        for col in df_numeric.columns:
            if col == 'sp500':
                continue
            corr = df_numeric['sp500'].corr(df_numeric[col])
            if pd.isna(corr):
                continue
            rows.append({"metric": col, "correlation": safe_number(corr)})

        summary = {
            "record_count": safe_int(len(rows), 0),
            "status": "ok",
        }

        return analytics_response(meta=_meta_for_df(df_numeric, "correlation"), data=rows, summary=summary)
    except Exception as e:
        return analytics_response(
            meta=_meta_for_df(df, "correlation"),
            data=[],
            summary={"status": "error"},
            errors=[f"Failed to calculate correlations: {e}"],
        )


def get_decade_performance() -> Dict[str, Any]:
    """Get performance summary by decade."""
    df = get_sp500_data()
    
    if df is None or df.empty:
        return analytics_response(
            meta=_meta_for_df(pd.DataFrame(columns=['date']), "decade"),
            data=[],
            summary={"status": "no-data"},
            errors=["No S&P 500 data available"],
        )
    
    try:
        df = _ensure_datetime(df.copy())
        df['decade'] = (df['date'].dt.year // 10) * 10
        decade_stats = df.groupby('decade').agg({
            'sp500': ['count', 'mean', 'min', 'max'],
            'pe10': 'mean',
            'dividend': 'mean',
            'long_interest_rate': 'mean'
        }).reset_index()
        
        rows: List[Dict[str, Any]] = []
        for _, row in decade_stats.iterrows():
            # Use .iloc[0] to properly extract scalar values from Series
            decade_val = row['decade']
            if hasattr(decade_val, 'iloc'):
                decade_val = decade_val.iloc[0]
            rows.append(
                {
                    "decade": int(decade_val),
                    "data_points": safe_int(row[('sp500', 'count')], 0),
                    "avg_sp500": safe_number(row[('sp500', 'mean')]),
                    "min_sp500": safe_number(row[('sp500', 'min')]),
                    "max_sp500": safe_number(row[('sp500', 'max')]),
                    "avg_pe10": safe_number(row[('pe10', 'mean')]),
                    "avg_dividend": safe_number(row[('dividend', 'mean')]),
                }
            )

        rows = list(reversed(rows))
        summary = {"record_count": safe_int(len(rows), 0), "status": "ok"}
        meta = _meta_for_df(df, "decade")
        return analytics_response(meta=meta, data=rows, summary=summary)
    except Exception as e:
        return analytics_response(
            meta=_meta_for_df(df, "decade"),
            data=[],
            summary={"status": "error"},
            errors=[f"Failed to fetch decade performance: {e}"],
        )


def get_volatility_analysis(period_days: int = 365) -> Dict[str, Any]:
    """Calculate volatility metrics for specified period."""
    df = get_sp500_data()
    
    if df is None or df.empty:
        return analytics_response(
            meta=_meta_for_df(pd.DataFrame(columns=['date']), "volatility"),
            data=[],
            summary={"status": "no-data"},
            errors=["No S&P 500 data available"],
        )
    
    try:
        df = _ensure_datetime(df.copy())
        start_date = df['date'].max() - timedelta(days=period_days)
        df_period = df[df['date'] >= start_date].copy()
        df_period = df_period.sort_values('date')
        df_period['sp500_numeric'] = pd.to_numeric(df_period['sp500'], errors='coerce')
        df_period['daily_return'] = df_period['sp500_numeric'].pct_change() * 100

        volatility = safe_number(df_period['daily_return'].std())
        avg_return = safe_number(df_period['daily_return'].mean())
        min_return = safe_number(df_period['daily_return'].min())
        max_return = safe_number(df_period['daily_return'].max())

        rows: List[Dict[str, Any]] = []
        for _, row in df_period.tail(120).iterrows():
            rows.append(
                {
                    "date": row['date'].strftime('%Y-%m-%d') if isinstance(row['date'], pd.Timestamp) else str(row['date']),
                    "daily_return": safe_number(row['daily_return']),
                }
            )

        summary = {
            "period_days": period_days,
            "volatility": volatility,
            "avg_daily_return": avg_return,
            "min_return": min_return,
            "max_return": max_return,
            "status": "ok",
        }

        meta = {
            "company": "SP500 Index",
            "date_range": merge_date_range(df_period['date'].min(), df_period['date'].max()),
            "aggregation": "daily",
        }

        return analytics_response(meta=meta, data=rows, summary=summary)
    except Exception as e:
        return analytics_response(
            meta=_meta_for_df(df, "volatility"),
            data=[],
            summary={"status": "error"},
            errors=[f"Failed to calculate volatility: {e}"],
        )


def get_sp500_timeseries(metric: str = "sp500", start_year: Optional[int] = None) -> Dict[str, Any]:
    """Get time series data for a specific metric."""
    df = get_sp500_data()
    
    if df is None or df.empty:
        return analytics_response(
            meta=_meta_for_df(pd.DataFrame(columns=['date']), "daily"),
            data=[],
            summary={"status": "no-data"},
            errors=["No data available"],
        )
    
    try:
        df = _ensure_datetime(df.copy())
        if metric not in df.columns:
            return analytics_response(
                meta=_meta_for_df(df, "daily"),
                data=[],
                summary={"status": "error"},
                errors=[f"Metric '{metric}' not found in data"],
            )
        if start_year and 'date' in df.columns:
            df = df[df['date'].dt.year >= start_year]
        
        rows: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            rows.append(
                {
                    "date": row['date'].strftime('%Y-%m-%d') if hasattr(row['date'], 'strftime') else str(row['date']),
                    "value": safe_number(row[metric]),
                }
            )
        
        summary = {
            "metric": metric,
            "record_count": safe_int(len(rows), 0),
            "status": "ok",
        }
        return analytics_response(meta=_meta_for_df(df, "daily"), data=rows, summary=summary)
    except Exception as e:
        return analytics_response(
            meta=_meta_for_df(df, "daily"),
            data=[],
            summary={"status": "error"},
            errors=[f"Failed to get time series: {e}"],
        )
