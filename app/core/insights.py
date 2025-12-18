"""
Financial Insights Module - Generate analytics and visualizations from stored data

Provides aggregated metrics, trends, comparisons, and key insights.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, Any, List, Optional
from app.config import settings


def get_database_summary() -> Dict[str, Any]:
    """Get overview statistics of stored financial data."""
    if not settings.database_url:
        return {"error": "DATABASE_URL not configured"}
    
    try:
        conn = psycopg2.connect(settings.database_url)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Count companies
        cursor.execute("SELECT COUNT(*) as count FROM companies")
        company_count = cursor.fetchone()['count']
        
        # Count metrics records
        cursor.execute("SELECT COUNT(*) as count FROM financial_metrics")
        metrics_count = cursor.fetchone()['count']
        
        # Get date range
        cursor.execute("""
            SELECT MIN(period) as earliest, MAX(period) as latest 
            FROM financial_metrics
        """)
        date_range = cursor.fetchone()
        
        # Get companies with most data
        cursor.execute("""
            SELECT c.ticker, c.name, COUNT(fm.id) as record_count
            FROM companies c
            LEFT JOIN financial_metrics fm ON c.id = fm.company_id
            GROUP BY c.id, c.ticker, c.name
            ORDER BY record_count DESC
            LIMIT 10
        """)
        top_companies = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return {
            "company_count": company_count,
            "metrics_count": metrics_count,
            "date_range": date_range,
            "top_companies": list(top_companies)
        }
    except Exception as e:
        return {"error": f"Failed to fetch summary: {str(e)}"}


def get_revenue_leaders(limit: int = 10) -> List[Dict[str, Any]]:
    """Get companies with highest recent revenue."""
    if not settings.database_url:
        return []
    
    try:
        conn = psycopg2.connect(settings.database_url)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT DISTINCT ON (c.ticker)
                c.ticker,
                c.name,
                fm.period,
                fm.revenue
            FROM companies c
            INNER JOIN financial_metrics fm ON c.id = fm.company_id
            WHERE fm.revenue IS NOT NULL
            ORDER BY c.ticker, fm.period DESC
        """)
        
        latest_revenues = cursor.fetchall()
        
        # Sort by revenue descending
        sorted_revenues = sorted(
            [r for r in latest_revenues if r['revenue']],
            key=lambda x: x['revenue'],
            reverse=True
        )[:limit]
        
        cursor.close()
        conn.close()
        
        return list(sorted_revenues)
    except Exception as e:
        print(f"Error fetching revenue leaders: {e}")
        return []


def get_profitability_metrics(limit: int = 10) -> List[Dict[str, Any]]:
    """Get companies with best profit margins."""
    if not settings.database_url:
        return []
    
    try:
        conn = psycopg2.connect(settings.database_url)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT DISTINCT ON (c.ticker)
                c.ticker,
                c.name,
                fm.period,
                fm.revenue,
                fm.net_income,
                CASE 
                    WHEN fm.revenue > 0 THEN (fm.net_income / fm.revenue * 100)
                    ELSE 0
                END as profit_margin
            FROM companies c
            INNER JOIN financial_metrics fm ON c.id = fm.company_id
            WHERE fm.revenue IS NOT NULL AND fm.net_income IS NOT NULL
            ORDER BY c.ticker, fm.period DESC
        """)
        
        margins = cursor.fetchall()
        
        # Sort by margin
        sorted_margins = sorted(
            [m for m in margins if m['profit_margin']],
            key=lambda x: x['profit_margin'],
            reverse=True
        )[:limit]
        
        cursor.close()
        conn.close()
        
        return list(sorted_margins)
    except Exception as e:
        print(f"Error fetching profitability: {e}")
        return []


def get_growth_trends(ticker: str) -> Dict[str, Any]:
    """Calculate growth trends for a specific company."""
    if not settings.database_url:
        return {"error": "DATABASE_URL not configured"}
    
    try:
        conn = psycopg2.connect(settings.database_url)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT fm.period, fm.revenue, fm.net_income, fm.eps
            FROM financial_metrics fm
            INNER JOIN companies c ON fm.company_id = c.id
            WHERE c.ticker = %s
            ORDER BY fm.period ASC
        """, (ticker.upper(),))
        
        data = cursor.fetchall()
        
        if len(data) < 2:
            cursor.close()
            conn.close()
            return {"error": "Insufficient data for trend analysis"}
        
        # Calculate growth rates
        revenue_growth = []
        income_growth = []
        
        for i in range(1, len(data)):
            prev = data[i-1]
            curr = data[i]
            
            if prev['revenue'] and curr['revenue'] and prev['revenue'] > 0:
                growth = ((curr['revenue'] - prev['revenue']) / prev['revenue']) * 100
                revenue_growth.append(growth)
            
            if prev['net_income'] and curr['net_income'] and prev['net_income'] > 0:
                growth = ((curr['net_income'] - prev['net_income']) / prev['net_income']) * 100
                income_growth.append(growth)
        
        cursor.close()
        conn.close()
        
        return {
            "ticker": ticker.upper(),
            "periods": [d['period'] for d in data],
            "revenue_data": [d['revenue'] for d in data],
            "income_data": [d['net_income'] for d in data],
            "avg_revenue_growth": sum(revenue_growth) / len(revenue_growth) if revenue_growth else 0,
            "avg_income_growth": sum(income_growth) / len(income_growth) if income_growth else 0
        }
    except Exception as e:
        return {"error": f"Failed to calculate trends: {str(e)}"}


def get_sector_comparison() -> List[Dict[str, Any]]:
    """Compare key metrics across all companies."""
    if not settings.database_url:
        return []
    
    try:
        conn = psycopg2.connect(settings.database_url)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT 
                c.ticker,
                c.name,
                AVG(fm.revenue) as avg_revenue,
                AVG(fm.net_income) as avg_net_income,
                AVG(CASE WHEN fm.revenue > 0 THEN (fm.net_income / fm.revenue * 100) ELSE 0 END) as avg_margin,
                COUNT(fm.id) as data_points
            FROM companies c
            LEFT JOIN financial_metrics fm ON c.id = fm.company_id
            GROUP BY c.id, c.ticker, c.name
            HAVING COUNT(fm.id) > 0
            ORDER BY avg_revenue DESC
        """)
        
        comparison = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return list(comparison)
    except Exception as e:
        print(f"Error fetching sector comparison: {e}")
        return []
