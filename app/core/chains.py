from typing import Dict, Any
from app.config import settings
from app.core.router import classify_query
from app.core.llm import get_llm

# Do NOT instantiate LLMs at import time. Use get_llm() inside functions
# so startup / uvicorn --reload doesn't trigger heavy network I/O.

# =============================================================================
# PROFESSIONAL FINANCIAL ANALYST SYSTEM PROMPT
# =============================================================================
_FINANCIAL_ANALYST_SYSTEM_PROMPT = """You are a financial analysis assistant for stakeholders and investors.

You must STRICTLY follow these rules:
- Use ONLY the provided retrieved context
- NEVER invent numbers, dates, or performance metrics
- NEVER state "no data available" without providing a useful summary
- NEVER hallucinate market-wide statistics

WHEN DATA IS PARTIAL:
- Summarize what IS available clearly
- Explicitly scope conclusions (company-level vs market-level)
- Explain limitations briefly and professionally
- Provide cautious, real-world insights based on known financial principles
- Suggest realistic next steps without assuming missing data

RESPONSE STRUCTURE (MANDATORY):
1. **Summary** - Key findings based only on retrieved data
2. **Context & Data Scope** - What data was analyzed, time period, limitations
3. **Practical Insights** - Actionable observations for stakeholders
4. **Data-Grounded Suggestions** - Next steps without predictions or financial advice

TONE:
- Professional and analyst-style
- Neutral and factual
- Helpful, not defensive

DO NOT:
- Ask the user to fetch external sources
- Claim lack of usefulness
- Use phrases like "cannot answer" or "insufficient data" alone
- Provide investment advice or predictions

Your goal is to sound like a real financial analyst explaining insights from available data."""

_GUARDRAIL_DIRECTIVE = (
    "You must never invent or guess financial numbers. If specific data is not in the context, "
    "clearly state what IS available and provide analysis based on that. "
    "Always maintain professional analyst tone and structure your response clearly."
)


def _llm_invoke(messages: list, use_mock: bool = False) -> str:
    """
    Invoke the configured LLM (Ollama, OpenAI, or mock).
    
    For LLM chains, we convert messages to string prompt format.
    """
    if use_mock:
        from app.core.mock_llm import get_mock_llm
        mock_llm = get_mock_llm()
        user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
        return mock_llm.invoke(user_msg).get("content", "No response")
    
    try:
        llm = get_llm()
        # Try using common LLM interface
        if hasattr(llm, "invoke"):
            prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
            result = llm.invoke(prompt)
            if hasattr(result, "content"):
                return result.content
            return str(result)

        if hasattr(llm, "get_response"):
            return llm.get_response(messages)

        if hasattr(llm, "__call__"):
            # Some LangChain wrappers are callable
            prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
            result = llm(prompt)
            if isinstance(result, dict):
                return result.get("content", str(result))
            if hasattr(result, "content"):
                return result.content
            return str(result)

        # Last-resort fallback to mock
        from app.core.mock_llm import get_mock_llm
        mock_llm = get_mock_llm()
        user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
        return mock_llm.invoke(user_msg).get("content", "No response")
    except Exception as e:
        print(f"LLM error: {e}, using mock fallback")
        from app.core.mock_llm import get_mock_llm
        mock_llm = get_mock_llm()
        user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
        return mock_llm.invoke(user_msg).get("content", "No response")



# ------------------------------------------------------
# Document RAG Chain
# ------------------------------------------------------
def run_doc_rag(question: str) -> Dict[str, Any]:
    try:
        from app.core.vectorstore import get_doc_retriever
        retriever = get_doc_retriever()
        docs = retriever.invoke(question)
        context = "\n\n---\n\n".join([d.page_content for d in docs])
    except Exception as e:
        docs = []
        context = f"(Vectorstore unavailable: {str(e)[:80]})"

    # If no docs found, try to build a small company context so answers aren't generic
    if not docs:
        try:
            from app.core.sp500_companies import search_companies
            hits = search_companies(question, 1)
            if hits:
                c = hits[0]
                context = (
                    f"Company: {c.get('name','N/A')} ({c.get('ticker','')})\n"
                    f"Sector: {c.get('sector','N/A')}\n"
                    f"Revenue: {c.get('revenue','N/A')}\n"
                    f"Period: {c.get('period','N/A')}"
                )
        except Exception:
            pass

    system = (
        f"{_FINANCIAL_ANALYST_SYSTEM_PROMPT}\n\n"
        f"ADDITIONAL DIRECTIVE: {_GUARDRAIL_DIRECTIVE}"
    )

    user = f"""RETRIEVED CONTEXT:
{context}

USER QUESTION: {question}

Provide a structured, professional financial analysis response following the mandatory format:
1. Summary
2. Context & Data Scope  
3. Practical Insights
4. Data-Grounded Suggestions"""

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    answer = _llm_invoke(messages)
    return {"answer": answer, "source_count": len(docs), "query_type": "DOC"}


# ------------------------------------------------------
# SQL Analytics Chain
# ------------------------------------------------------
def run_sql_analytics(question: str) -> Dict[str, Any]:
    """SQL chain using agent; fallback to S&P 500 demo data."""
    if settings.database_url:
        try:
            from app.core.sql_tools import get_sql_agent
            agent = get_sql_agent()
            result = agent.invoke(question)

            if isinstance(result, dict):
                answer_text = result.get("output", str(result))
            else:
                answer_text = str(result)

            answer_text = answer_text.strip() or "The SQL agent did not return any rows."

            return {"answer": answer_text, "query_type": "SQL"}

        except Exception:
            pass  # fallback to demo

    # Demo SQL responses using S&P 500 companies
    from app.core.sp500_companies import (
        get_sp500_companies,
        get_top_companies_by_revenue,
        search_companies
    )
    
    question_lower = question.lower()
    
    # Get relevant companies based on question
    notice = "Live database unavailable; returning sanitized sample data."

    if any(word in question_lower for word in ['top', 'largest', 'biggest', 'revenue', 'leader']):
        companies = get_top_companies_by_revenue(5)
        if companies:
            company_list = "\n".join([
                f"- {c['name']} ({c['ticker']}): Revenue ${c.get('revenue', 'N/A')}"
                for c in companies
            ])
            return {
                "answer": f"{notice}\n\n📊 Top S&P 500 Companies by Revenue:\n{company_list}",
                "query_type": "SQL"
            }
    
    # Search for specific company
    search_keywords = ['apple', 'microsoft', 'google', 'amazon', 'tesla', 'nvidia', 'meta', 'berkshire']
    for keyword in search_keywords:
        if keyword in question_lower:
            company = search_companies(keyword, 1)
            if company:
                c = company[0]
                return {
                    "answer": f"{notice}\n\n📊 {c['name']} ({c['ticker']}) - Sector: {c.get('sector', 'N/A')}",
                    "query_type": "SQL"
                }
    
    # Default: show some companies
    companies = get_sp500_companies(10)
    if companies:
        company_list = ", ".join([c['ticker'] for c in companies[:10]])
        return {
            "answer": f"{notice}\n\n📊 S&P 500 Companies: {company_list}...\nTry asking about specific companies or metrics.",
            "query_type": "SQL"
        }
    
    return {
        "answer": f"{notice}\n\n📊 [Demo] S&P 500 financial data available. Try asking about top companies or specific tickers.",
        "query_type": "SQL"
    }


# ------------------------------------------------------
# Hybrid Chain (SQL + RAG)
# ------------------------------------------------------
def run_hybrid(question: str) -> Dict[str, Any]:
    sql_result = run_sql_analytics(question)
    doc_result = run_doc_rag(question)

    system = (
        f"{_FINANCIAL_ANALYST_SYSTEM_PROMPT}\n\n"
        "SPECIAL INSTRUCTION: You are combining numeric SQL data with document context. "
        "Synthesize both sources into a unified analysis. Highlight key metrics, trends, and qualitative context. "
        f"{_GUARDRAIL_DIRECTIVE}"
    )

    user = f"""USER QUESTION: {question}

SQL NUMERIC ANALYSIS:
{sql_result['answer']}

DOCUMENT/CONTEXT INSIGHTS:
{doc_result['answer']}

Provide an integrated, expert-level financial analysis following the mandatory structure:
1. Summary - Unified findings from both data sources
2. Context & Data Scope - What numeric and qualitative data was analyzed
3. Practical Insights - Combined actionable observations
4. Data-Grounded Suggestions - Next steps based on the integrated analysis"""

    messages = [
        {"role": "system", "content": system},
        {"role": "user",  "content": user},
    ]

    merged = _llm_invoke(messages)

    return {
        "answer": merged,
        "query_type": "HYBRID",
        "parts": {"sql": sql_result, "doc": doc_result},
    }


# ------------------------------------------------------
# Main Orchestrator for API
# ------------------------------------------------------
def answer_financial_question(question: str) -> Dict[str, Any]:
    classification = classify_query(question)
    qtype = classification.get("query_type", "DOC")

    if qtype == "DOC":
        result = run_doc_rag(question)
    elif qtype == "SQL":
        result = run_sql_analytics(question)
    else:
        result = run_hybrid(question)

    result["router"] = classification
    return result
