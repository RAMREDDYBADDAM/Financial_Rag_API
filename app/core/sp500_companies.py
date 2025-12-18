"""
S&P 500 Companies Data Module

Provides data for top S&P 500 companies from the ingested financial database
or sample data if database is not configured
"""

from typing import Dict, Any, List, Optional
from app.config import settings
import psycopg2
from psycopg2.extras import RealDictCursor

from app.core.response_utils import safe_number

# Cache for S&P 500 companies
_sp500_companies_cache = None

_NUMERIC_FIELDS = {"revenue", "market_cap", "net_income", "operating_income", "equity"}


def _sanitize_company_record(record: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = dict(record)
    for field in _NUMERIC_FIELDS:
        if field in sanitized:
            sanitized[field] = safe_number(sanitized[field])
    return sanitized


def _get_sample_sp500_companies() -> List[Dict[str, Any]]:
    """Return sample S&P 500 companies for demo/fallback."""
    return [
        {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology", "revenue": 394328000000, "market_cap": 3200000000000, "period": "2024"},
        {"ticker": "MSFT", "name": "Microsoft Corporation", "sector": "Technology", "revenue": 245122000000, "market_cap": 3000000000000, "period": "2024"},
        {"ticker": "GOOGL", "name": "Alphabet Inc.", "sector": "Technology", "revenue": 307394000000, "market_cap": 1800000000000, "period": "2024"},
        {"ticker": "AMZN", "name": "Amazon.com Inc.", "sector": "Consumer Discretionary", "revenue": 574785000000, "market_cap": 1700000000000, "period": "2024"},
        {"ticker": "NVDA", "name": "NVIDIA Corporation", "sector": "Technology", "revenue": 79774000000, "market_cap": 1500000000000, "period": "2024"},
        {"ticker": "TSLA", "name": "Tesla Inc.", "sector": "Consumer Discretionary", "revenue": 96773000000, "market_cap": 800000000000, "period": "2024"},
        {"ticker": "META", "name": "Meta Platforms Inc.", "sector": "Technology", "revenue": 134902000000, "market_cap": 950000000000, "period": "2024"},
        {"ticker": "BERKB", "name": "Berkshire Hathaway Inc.", "sector": "Financials", "revenue": 364482000000, "market_cap": 900000000000, "period": "2024"},
        {"ticker": "JNJ", "name": "Johnson & Johnson", "sector": "Healthcare", "revenue": 85159000000, "market_cap": 400000000000, "period": "2024"},
        {"ticker": "V", "name": "Visa Inc.", "sector": "Financials", "revenue": 32653000000, "market_cap": 550000000000, "period": "2024"},
        {"ticker": "WMT", "name": "Walmart Inc.", "sector": "Consumer Staples", "revenue": 648125000000, "market_cap": 520000000000, "period": "2024"},
        {"ticker": "JPM", "name": "JPMorgan Chase & Co.", "sector": "Financials", "revenue": 158096000000, "market_cap": 600000000000, "period": "2024"},
        {"ticker": "PG", "name": "Procter & Gamble", "sector": "Consumer Staples", "revenue": 82006000000, "market_cap": 380000000000, "period": "2024"},
        {"ticker": "USGX", "name": "US Gas", "sector": "Energy", "revenue": 45000000000, "market_cap": 120000000000, "period": "2024"},
        {"ticker": "HD", "name": "The Home Depot Inc.", "sector": "Consumer Discretionary", "revenue": 157403000000, "market_cap": 350000000000, "period": "2024"},
        {"ticker": "MA", "name": "Mastercard Incorporated", "sector": "Financials", "revenue": 25098000000, "market_cap": 420000000000, "period": "2024"},
        {"ticker": "DIS", "name": "The Walt Disney Company", "sector": "Communication Services", "revenue": 88898000000, "market_cap": 180000000000, "period": "2024"},
        {"ticker": "MRK", "name": "Merck & Co. Inc.", "sector": "Healthcare", "revenue": 60115000000, "market_cap": 260000000000, "period": "2024"},
        {"ticker": "KO", "name": "The Coca-Cola Company", "sector": "Consumer Staples", "revenue": 45754000000, "market_cap": 280000000000, "period": "2024"},
        {"ticker": "INTC", "name": "Intel Corporation", "sector": "Technology", "revenue": 54228000000, "market_cap": 200000000000, "period": "2024"},
    ]


def get_sp500_companies(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Get list of S&P 500 companies from database or sample data.
    
    Args:
        limit: Number of companies to return (default 50)
        
    Returns:
        List of company dictionaries with ticker, name, sector
    """
    global _sp500_companies_cache
    
    # Return cached data if available
    if _sp500_companies_cache is not None and len(_sp500_companies_cache) > 0:
        return _sp500_companies_cache[:limit]
    
    # Try to fetch from database
    if settings.database_url:
        try:
            conn = psycopg2.connect(settings.database_url)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Query companies table
            cursor.execute("""
                SELECT id, ticker, name, sector
                FROM companies
                LIMIT %s
            """, (limit,))
            
            companies = [dict(row) for row in cursor.fetchall()]
            cursor.close()
            conn.close()
            
            if companies:
                sanitized = [_sanitize_company_record(row) for row in companies]
                _sp500_companies_cache = sanitized
                return sanitized[:limit]
        except Exception as e:
            print(f"Error fetching companies from database: {e}")
    
    # Return sample data
    sample = [_sanitize_company_record(row) for row in _get_sample_sp500_companies()]
    _sp500_companies_cache = sample
    return sample[:limit]


def get_company_data(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Get detailed data for a specific company.
    
    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")
        
    Returns:
        Dictionary with company data including latest metrics
    """
    if not settings.database_url:
        # Return sample data for demo
        sample = _get_sample_sp500_companies()
        for company in sample:
            if company['ticker'].lower() == ticker.lower():
                return _sanitize_company_record(company)
        return None
    
    try:
        conn = psycopg2.connect(settings.database_url)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get company info
        cursor.execute("""
            SELECT id, ticker, name, sector
            FROM companies
            WHERE ticker = %s
        """, (ticker.upper(),))
        
        company = cursor.fetchone()
        
        if company:
            company_dict = dict(company)
            
            # Get latest financial metrics
            cursor.execute("""
                SELECT revenue, net_income, operating_income, equity
                FROM financial_metrics
                WHERE company_id = %s
                ORDER BY period_end DESC
                LIMIT 1
            """, (company_dict['id'],))
            
            latest_metrics = cursor.fetchone()
            if latest_metrics:
                company_dict.update({k: safe_number(v) for k, v in dict(latest_metrics).items()})
            
            cursor.close()
            conn.close()
            
            return _sanitize_company_record(company_dict)
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error fetching company data: {e}")
    
    # Fallback to sample
    sample = _get_sample_sp500_companies()
    for company in sample:
        if company['ticker'].lower() == ticker.lower():
            return _sanitize_company_record(company)
    
    return None


def get_top_companies_by_revenue(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Get top companies by revenue.
    
    Args:
        limit: Number of companies to return
        
    Returns:
        List of top companies with revenue data
    """
    if not settings.database_url:
        # Return sample data
        return [_sanitize_company_record(row) for row in _get_sample_sp500_companies()[:limit]]
    
    try:
        conn = psycopg2.connect(settings.database_url)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("""
            SELECT 
                c.ticker, c.name, c.sector,
                fm.revenue, fm.net_income,
                fm.period_end
            FROM companies c
            LEFT JOIN financial_metrics fm ON c.id = fm.company_id
            WHERE fm.period_end = (
                SELECT MAX(period_end) 
                FROM financial_metrics 
                WHERE company_id = c.id
            )
            ORDER BY fm.revenue DESC NULLS LAST
            LIMIT %s
        """, (limit,))
        
        companies = [_sanitize_company_record(dict(row)) for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        
        return companies
        
    except Exception as e:
        print(f"Error fetching top companies: {e}")
        return _get_sample_sp500_companies()[:limit]


def search_companies(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search for companies by name or ticker.
    
    Args:
        query: Search query (name or ticker)
        limit: Number of results to return
        
    Returns:
        List of matching companies
    """
    if not settings.database_url:
        # Search in sample data
        sample = _get_sample_sp500_companies()
        query_lower = query.lower()
        results = [
            c for c in sample
            if query_lower in c['ticker'].lower() or query_lower in c['name'].lower()
        ]
        return results[:limit]
    
    try:
        conn = psycopg2.connect(settings.database_url)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        search_term = f"%{query}%"
        cursor.execute("""
            SELECT id, ticker, name, sector
            FROM companies
            WHERE ticker ILIKE %s OR name ILIKE %s
            LIMIT %s
        """, (search_term, search_term, limit))
        
        companies = [dict(row) for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        
        return companies if companies else [_sanitize_company_record(row) for row in _get_sample_sp500_companies()[:limit]]
        
    except Exception as e:
        print(f"Error searching companies: {e}")
        return _get_sample_sp500_companies()[:limit]
