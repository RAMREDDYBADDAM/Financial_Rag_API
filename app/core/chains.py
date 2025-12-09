from typing import Dict, Any
from app.config import settings
from app.core.router import classify_query
from app.core.llm import get_llm

# Do NOT instantiate LLMs at import time. Use get_llm() inside functions
# so startup / uvicorn --reload doesn't trigger heavy network I/O.


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
            return llm(prompt)

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

    system = (
        "You are a financial assistant. Use ONLY the provided context to answer the question. "
        "If the context does not clearly contain the answer, say you are not sure."
    )

    user = f"Context:\n{context}\n\nQuestion: {question}\n\nProvide a precise, finance-professional answer."

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
    """SQL chain using agent; fallback to demo."""
    if settings.database_url:
        try:
            from app.core.sql_tools import get_sql_agent
            agent = get_sql_agent()
            result = agent.invoke(question)

            if isinstance(result, dict):
                answer_text = result.get("output", str(result))
            else:
                answer_text = str(result)

            return {"answer": answer_text, "query_type": "SQL"}

        except Exception:
            pass  # fallback to demo

    # Demo SQL responses
    demo = {
        "apple": "📊 Apple Q1 Revenue: $94.7B (+5.2% YoY).",
        "revenue": "📊 Total revenue: $125.3B (+3.8% YoY).",
        "profit": "📊 Operating profit: $35.2B (28.1% margin).",
        "growth": "📊 YoY growth: +4.8%.",
        "default": "📊 [Demo] Simulated SQL result. Connect financial DB for real metrics.",
    }

    q = question.lower()
    for key, resp in demo.items():
        if key in q:
            return {"answer": resp, "query_type": "SQL"}

    return {"answer": demo["default"], "query_type": "SQL"}


# ------------------------------------------------------
# Hybrid Chain (SQL + RAG)
# ------------------------------------------------------
def run_hybrid(question: str) -> Dict[str, Any]:
    sql_result = run_sql_analytics(question)
    doc_result = run_doc_rag(question)

    system = (
        "You are a senior financial analyst. Combine the numeric data and document insights "
        "into a single, coherent answer. Highlight key metrics, trends, and context."
    )

    user = (
        f"User question: {question}\n\n"
        f"SQL numeric analysis:\n{sql_result['answer']}\n\n"
        f"Document/context explanation:\n{doc_result['answer']}\n\n"
        "Provide an integrated, expert-level response."
    )

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
