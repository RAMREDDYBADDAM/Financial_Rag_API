"""
S&P 500 LLM Chain - Natural language interface for S&P 500 analytics

Allows users to ask questions about S&P 500 data in natural language
and get intelligent responses with relevant visualizations
"""

from typing import Dict, Any, Optional
from app.core.llm import call_llm
from app.core.sp500_analytics import (
    get_sp500_summary,
    get_time_series_data,
    get_year_over_year_growth,
    get_correlation_matrix,
    get_decade_performance,
    get_volatility_analysis
)
import json
import re


def _extract_intent(question: str) -> str:
    """Extract the intent/type of S&P 500 question."""
    question_lower = question.lower()
    
    # Categorize by intent
    if any(word in question_lower for word in ['trend', 'history', 'price', 'movement', 'change']):
        return 'price_trend'
    elif any(word in question_lower for word in ['growth', 'return', 'performance', 'gain']):
        return 'performance'
    elif any(word in question_lower for word in ['correlation', 'related', 'relationship', 'compare']):
        return 'correlation'
    elif any(word in question_lower for word in ['decade', 'century', 'period', 'era', 'year']):
        return 'historical'
    elif any(word in question_lower for word in ['volatile', 'volatility', 'risk', 'fluctuat']):
        return 'volatility'
    elif any(word in question_lower for word in ['summary', 'overview', 'general', 'overall']):
        return 'summary'
    else:
        return 'general'


def _get_relevant_data(intent: str, question: str) -> Dict[str, Any]:
    """Fetch relevant S&P 500 data based on intent."""
    data = {}
    
    try:
        if intent == 'price_trend':
            # Get time series data
            data['timeseries'] = get_time_series_data(limit=100)
            data['summary'] = get_sp500_summary()
            
        elif intent == 'performance':
            # Get growth data
            data['growth'] = get_year_over_year_growth()
            data['summary'] = get_sp500_summary()
            
        elif intent == 'correlation':
            # Get correlation data
            data['correlations'] = get_correlation_matrix()
            data['summary'] = get_sp500_summary()
            
        elif intent == 'historical':
            # Get decade performance
            data['decades'] = get_decade_performance()
            data['summary'] = get_sp500_summary()
            
        elif intent == 'volatility':
            # Get volatility data
            data['volatility'] = get_volatility_analysis()
            data['summary'] = get_sp500_summary()
            
        else:  # summary or general
            # Get comprehensive summary
            data['summary'] = get_sp500_summary()
            data['decades'] = get_decade_performance()
            data['correlations'] = get_correlation_matrix()
    
    except Exception as e:
        data['error'] = str(e)
    
    return data


def _format_data_for_llm(data: Dict[str, Any]) -> str:
    """Format fetched data into readable text for LLM."""
    formatted = []
    
    if 'error' in data:
        return f"Error fetching data: {data['error']}"
    
    if 'summary' in data and data['summary'].get('success'):
        summary = data['summary']
        formatted.append("=== S&P 500 Summary ===")
        if 'date_range' in summary:
            formatted.append(f"Date Range: {summary['date_range']['earliest']} to {summary['date_range']['latest']}")
        if 'latest_values' in summary:
            formatted.append(f"Latest S&P 500: {summary['latest_values'].get('sp500', 'N/A')}")
            formatted.append(f"Latest Dividend: {summary['latest_values'].get('dividend', 'N/A')}")
            formatted.append(f"Latest PE10: {summary['latest_values'].get('pe10', 'N/A')}")
        if 'statistics' in summary:
            stats = summary['statistics']
            if 'sp500' in stats:
                sp500_stats = stats['sp500']
                formatted.append(f"\nS&P 500 Statistics:")
                formatted.append(f"  Average: {sp500_stats.get('avg', 'N/A')}")
                formatted.append(f"  Min: {sp500_stats.get('min', 'N/A')}")
                formatted.append(f"  Max: {sp500_stats.get('max', 'N/A')}")
                formatted.append(f"  StdDev: {sp500_stats.get('stddev', 'N/A')}")
    
    if 'timeseries' in data and data['timeseries'].get('success'):
        ts = data['timeseries']
        formatted.append(f"\n=== Time Series Data ({ts.get('count', 0)} records) ===")
        if ts.get('data'):
            # Show first and last few records
            formatted.append("Recent data:")
            for record in ts['data'][-5:]:
                formatted.append(f"  {record.get('date', 'N/A')}: S&P500={record.get('sp500', 'N/A')}")
    
    if 'growth' in data and data['growth'].get('success'):
        growth = data['growth']
        formatted.append(f"\n=== Year-over-Year Growth ===")
        if growth.get('growth'):
            for record in growth['growth'][-10:]:
                formatted.append(f"  {record.get('year', 'N/A')}: {record.get('yoy_growth', 'N/A')}%")
    
    if 'correlations' in data and data['correlations'].get('success'):
        corr = data['correlations']
        formatted.append(f"\n=== Correlations with S&P 500 ===")
        if corr.get('correlations'):
            for metric, correlation in corr['correlations'].items():
                formatted.append(f"  {metric}: {correlation:.3f}")
    
    if 'decades' in data and data['decades'].get('success'):
        decades = data['decades']
        formatted.append(f"\n=== Decade Performance ===")
        if decades.get('decades'):
            for decade in decades['decades'][:10]:
                formatted.append(f"  {decade.get('decade', 'N/A')}s: Avg={decade.get('avg_sp500', 'N/A')}, Min={decade.get('min_sp500', 'N/A')}, Max={decade.get('max_sp500', 'N/A')}")
    
    if 'volatility' in data and data['volatility'].get('success'):
        vol = data['volatility']
        formatted.append(f"\n=== Volatility Analysis (Period: {vol.get('period_days', 'N/A')} days) ===")
        formatted.append(f"  Volatility: {vol.get('volatility', 'N/A')}")
        formatted.append(f"  Avg Daily Return: {vol.get('avg_daily_return', 'N/A')}%")
        formatted.append(f"  Min Return: {vol.get('min_return', 'N/A')}%")
        formatted.append(f"  Max Return: {vol.get('max_return', 'N/A')}%")
    
    return "\n".join(formatted)


async def answer_sp500_question(question: str) -> Dict[str, Any]:
    """
    Answer S&P 500 questions using LLM with data context.
    
    Args:
        question: User's natural language question about S&P 500
        
    Returns:
        Dict with answer, data_type, and relevant data for visualization
    """
    try:
        # Extract intent
        intent = _extract_intent(question)
        
        # Fetch relevant data
        data = _get_relevant_data(intent, question)
        
        # Format data for LLM
        formatted_data = _format_data_for_llm(data)
        
        # Build prompt for LLM
        system_prompt = """You are a financial analyst expert in S&P 500 data analysis. 
You have access to historical S&P 500 data from 1871 to present including price, dividends, earnings, PE ratios, and economic indicators.
Answer questions about the S&P 500 data accurately and comprehensively.
Provide specific numbers and percentages when discussing data.
Be concise but informative."""
        
        user_prompt = f"""Based on the following S&P 500 data, please answer this question:

QUESTION: {question}

DATA CONTEXT:
{formatted_data}

Please provide a clear, data-backed answer. Include specific numbers and insights from the data provided."""
        
        # Call LLM
        llm_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        response = await call_llm(llm_messages)
        
        answer = response if isinstance(response, str) else response.get('content', response)
        
        return {
            "success": True,
            "answer": answer,
            "intent": intent,
            "data_type": "sp500_analysis",
            "data": data
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "answer": f"I encountered an error analyzing your S&P 500 question: {str(e)}"
        }


async def extract_sp500_chart_params(question: str) -> Dict[str, Any]:
    """
    Extract parameters for chart generation from user question.
    
    Uses LLM to understand what type of chart and data the user wants.
    """
    try:
        system_prompt = """You are a data visualization expert. 
Extract the visualization parameters from user questions about S&P 500 data.
Respond with a JSON object containing:
- chart_type: 'line', 'bar', 'scatter', 'area', 'histogram'
- metrics: list of metrics to display (e.g., ['sp500', 'dividend'])
- time_period: 'all', 'year', 'decade', '50years', etc.
- comparison: null or metric to compare against sp500

Always respond with valid JSON only, no other text."""
        
        user_prompt = f"""Extract chart parameters for this S&P 500 question: "{question}"

Respond with JSON only."""
        
        llm_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        response = await call_llm(llm_messages)
        
        # Extract JSON from response
        response_text = response if isinstance(response, str) else response.get('content', response)
        
        # Try to find JSON in response
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            params = json.loads(json_match.group())
            return {
                "success": True,
                "chart_type": params.get('chart_type', 'line'),
                "metrics": params.get('metrics', ['sp500']),
                "time_period": params.get('time_period', 'all'),
                "comparison": params.get('comparison')
            }
        else:
            # Return defaults if JSON extraction fails
            return {
                "success": True,
                "chart_type": "line",
                "metrics": ["sp500"],
                "time_period": "all",
                "comparison": None
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "chart_type": "line",
            "metrics": ["sp500"]
        }
