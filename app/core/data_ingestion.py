"""
Data Ingestion Module - Parse CSV/Excel and populate PostgreSQL

Supports uploading financial data from CSV/Excel files and automatically
creating/populating database tables with the data.
"""

import io
import csv
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple
import psycopg2
from psycopg2.extras import execute_batch
from app.config import settings


def detect_data_type(df: pd.DataFrame) -> str:
    """
    Detect whether the data is S&P 500 time-series or company financial metrics.
    
    Returns: 'sp500' or 'company_metrics'
    """
    cols_lower = [col.lower() for col in df.columns]
    
    # Check for S&P 500 specific columns
    sp500_indicators = ['sp500', 'consumer price index', 'long interest rate', 'real price', 'pe10']
    if any(indicator in cols_lower for indicator in sp500_indicators):
        return 'sp500'
    
    # Check for company metrics columns
    company_indicators = ['company', 'ticker', 'revenue', 'net_income']
    if any(indicator in cols_lower for indicator in company_indicators):
        return 'company_metrics'
    
    return 'unknown'


def parse_uploaded_file(file_content: bytes, filename: str) -> Tuple[pd.DataFrame, str]:
    """
    Parse uploaded CSV or Excel file into a pandas DataFrame.
    
    Args:
        file_content: Raw bytes of the uploaded file
        filename: Original filename (used to determine format)
        
    Returns:
        Tuple of (DataFrame, error_message)
        error_message is empty string if successful
    """
    try:
        if filename.endswith('.csv'):
            # Parse CSV
            df = pd.read_csv(io.BytesIO(file_content))
        elif filename.endswith(('.xlsx', '.xls')):
            # Parse Excel
            df = pd.read_excel(io.BytesIO(file_content))
        else:
            return None, f"Unsupported file format: {filename}. Use CSV or Excel files."
        
        if df.empty:
            return None, "File is empty"
            
        return df, ""
    except Exception as e:
        return None, f"Failed to parse file: {str(e)}"


def detect_financial_schema(df: pd.DataFrame) -> Dict[str, str]:
    """
    Analyze DataFrame columns and detect likely financial data schema.
    
    Returns mapping of standardized column names to actual column names.
    """
    column_mapping = {}
    
    # Common column name patterns (case-insensitive)
    patterns = {
        'company': ['company', 'ticker', 'symbol', 'stock', 'name', 'company_name'],
        'period': ['period', 'date', 'quarter', 'year', 'time', 'fiscal_period'],
        'revenue': ['revenue', 'sales', 'total_revenue', 'total_sales'],
        'net_income': ['net_income', 'profit', 'net_profit', 'earnings', 'income'],
        'operating_income': ['operating_income', 'operating_profit', 'ebit'],
        'eps': ['eps', 'earnings_per_share', 'earning_per_share'],
        'total_assets': ['total_assets', 'assets'],
        'total_liabilities': ['total_liabilities', 'liabilities'],
        'equity': ['equity', 'shareholders_equity', 'stockholders_equity'],
    }
    
    cols_lower = {col.lower(): col for col in df.columns}
    
    for standard_name, possible_names in patterns.items():
        for possible in possible_names:
            if possible in cols_lower:
                column_mapping[standard_name] = cols_lower[possible]
                break
    
    return column_mapping


def create_companies_if_missing(conn, companies: List[str]) -> Dict[str, int]:
    """
    Ensure companies exist in the companies table and return mapping of ticker -> id.
    """
    cursor = conn.cursor()
    company_ids = {}
    
    for company in companies:
        # Check if company exists
        cursor.execute("SELECT id FROM companies WHERE ticker = %s", (company.upper(),))
        result = cursor.fetchone()
        
        if result:
            company_ids[company] = result[0]
        else:
            # Insert new company
            cursor.execute(
                "INSERT INTO companies (ticker, name) VALUES (%s, %s) RETURNING id",
                (company.upper(), company.upper())
            )
            company_ids[company] = cursor.fetchone()[0]
    
    conn.commit()
    cursor.close()
    return company_ids


def ingest_to_database(df: pd.DataFrame, table_name: str = "financial_metrics") -> Dict[str, Any]:
    """
    Ingest DataFrame into PostgreSQL database.
    
    Creates companies and populates financial_metrics table.
    
    Returns:
        Dict with status, row_count, and any errors
    """
    if not settings.database_url:
        return {
            "success": False,
            "error": "DATABASE_URL not configured. Set it in .env file.",
            "rows_inserted": 0
        }
    
    try:
        conn = psycopg2.connect(settings.database_url)
        
        # Detect schema
        col_map = detect_financial_schema(df)
        
        if 'company' not in col_map:
            return {
                "success": False,
                "error": "Could not find company/ticker column in file",
                "rows_inserted": 0
            }
        
        # Get unique companies and ensure they exist
        companies = df[col_map['company']].unique().tolist()
        company_ids = create_companies_if_missing(conn, companies)
        
        # Prepare data for insertion
        cursor = conn.cursor()
        rows_to_insert = []
        
        for _, row in df.iterrows():
            company_ticker = row[col_map['company']]
            company_id = company_ids.get(company_ticker)
            
            if not company_id:
                continue
            
            # Build row data
            row_data = {
                'company_id': company_id,
                'period': row.get(col_map.get('period'), 'Unknown'),
                'revenue': float(row.get(col_map.get('revenue'), 0)) if col_map.get('revenue') else None,
                'net_income': float(row.get(col_map.get('net_income'), 0)) if col_map.get('net_income') else None,
                'operating_income': float(row.get(col_map.get('operating_income'), 0)) if col_map.get('operating_income') else None,
                'eps': float(row.get(col_map.get('eps'), 0)) if col_map.get('eps') else None,
                'total_assets': float(row.get(col_map.get('total_assets'), 0)) if col_map.get('total_assets') else None,
                'total_liabilities': float(row.get(col_map.get('total_liabilities'), 0)) if col_map.get('total_liabilities') else None,
                'equity': float(row.get(col_map.get('equity'), 0)) if col_map.get('equity') else None,
            }
            
            rows_to_insert.append(row_data)
        
        # Insert data using execute_batch for efficiency
        if rows_to_insert:
            insert_query = """
                INSERT INTO financial_metrics 
                (company_id, period, revenue, net_income, operating_income, eps, total_assets, total_liabilities, equity)
                VALUES (%(company_id)s, %(period)s, %(revenue)s, %(net_income)s, %(operating_income)s, 
                        %(eps)s, %(total_assets)s, %(total_liabilities)s, %(equity)s)
                ON CONFLICT (company_id, period) DO UPDATE SET
                    revenue = EXCLUDED.revenue,
                    net_income = EXCLUDED.net_income,
                    operating_income = EXCLUDED.operating_income,
                    eps = EXCLUDED.eps,
                    total_assets = EXCLUDED.total_assets,
                    total_liabilities = EXCLUDED.total_liabilities,
                    equity = EXCLUDED.equity
            """
            
            execute_batch(cursor, insert_query, rows_to_insert)
            conn.commit()
        
        cursor.close()
        conn.close()
        
        return {
            "success": True,
            "rows_inserted": len(rows_to_insert),
            "companies": list(company_ids.keys()),
            "columns_mapped": col_map
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Database ingestion failed: {str(e)}",
            "rows_inserted": 0
        }


def get_data_preview(df: pd.DataFrame, max_rows: int = 10) -> Dict[str, Any]:
    """
    Generate a preview of the DataFrame for display.
    
    Returns column info and sample rows.
    """
    preview = {
        "columns": list(df.columns),
        "row_count": len(df),
        "column_types": {col: str(df[col].dtype) for col in df.columns},
        "sample_rows": df.head(max_rows).to_dict(orient='records'),
        "detected_schema": detect_financial_schema(df)
    }
    return preview
