#!/usr/bin/env python3
"""Demo: Web search tool with LLM routing for financial research.

This demonstrates a simpler alternative to browser automation:
- Uses DuckDuckGo API for fast RAG-style searches
- LLM routes between web_search and browser tools
- Returns synthesized answers with citations

Run: PYTHONPATH=src .venv/bin/python scripts/demo_web_search.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tools.router import ToolRouter


async def main():
    print("=" * 60)
    print("FinText-LLM Web Search Demo")
    print("Tool: DuckDuckGo API + LLM Routing")
    print("=" * 60)

    router = ToolRouter()

    # Example queries
    queries = [
        "What is the impact of Middle East war on Intel stock price?",
        "Latest Apple earnings and analyst opinions",
        "Federal Reserve interest rate decision impact on markets",
    ]

    for query in queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print("=" * 60)

        result = await router.run(query, max_iterations=3)
        print(f"\nResult: {result[:300]}...")

        # Clear history for next query
        router.search_history.clear()

    print("\n" + "=" * 60)
    print("Demo complete!")


if __name__ == "__main__":
    asyncio.run(main())
