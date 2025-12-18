"""Quick demo runner for core APIs (chat and plot) using mock LLM.

This script sets environment variables to prefer mock behavior (disables Ollama
and clears OpenAI key), then imports and runs the functions directly. Run with:

    py -3 scripts\run_demo.py

"""
import os
import json

# Force mock LLM by disabling Ollama and clearing OpenAI key in-process
os.environ["OLLAMA_ENABLED"] = "false"
os.environ["OPENAI_API_KEY"] = ""

from app.core.chains import answer_financial_question
from app.core.plot_generator import generate_plot_from_rag_output

if __name__ == "__main__":
    q1 = "What are Apple's main products?"
    print("\n=== Chat Demo ===")
    try:
        res = answer_financial_question(q1)
        print(json.dumps(res, indent=2))
    except Exception as e:
        print("Chat failed:", e)

    q2 = "Show me Apple revenue growth trend"
    print("\n=== Plot Demo ===")
    try:
        plot_res = generate_plot_from_rag_output(q2)
        if plot_res is None:
            print("Plot generation returned None")
        else:
            print("Plot result keys:", list(plot_res.keys()))
            print("Company:", plot_res.get("company"))
            print("Metric:", plot_res.get("metric"))
            print("Data points:", plot_res.get("data_points"))
            print("Plot base64 length:", len(plot_res.get("plot_base64", "")))
    except Exception as e:
        import traceback
        print("Plot failed:")
        traceback.print_exc()
