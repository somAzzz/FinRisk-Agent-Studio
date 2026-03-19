#!/usr/bin/env python3
"""Demo script for browser exploration using SGLang with Pydantic structured output."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.browser import BrowserWrapper, MarketExplorer
from src.llm.sglang_client import SGLangClient


async def main():
    print("=" * 60)
    print("FinText-LLM Browser Exploration Demo")
    print("Using SGLang + Pydantic Structured Output")
    print("=" * 60)

    # Initialize with SGLang client
    llm_client = SGLangClient()
    wrapper = BrowserWrapper()
    explorer = MarketExplorer(llm_client=llm_client, wrapper=wrapper)

    # Simple checkpoint handler
    def checkpoint_handler(state):
        print(f"\n--- Checkpoint at step {state.current_step} ---")
        print(f"Findings so far: {len(state.findings)}")
        for f in state.findings[-3:]:
            print(f"  [{f.source_type}] {f.summary[:100]}...")

        if len(state.findings) >= 5:
            print("Enough findings, stopping...")
            return False

        # Auto-continue for demo
        print("\nAuto-continuing exploration...")
        return True

    # Run exploration
    print("\nStarting exploration...")
    result = await explorer.explore(
        goal="Explore Apple's latest earnings news and analyst opinions",
        checkpoint_callback=checkpoint_handler,
    )

    # Summary
    print("\n" + "=" * 60)
    print("EXPLORATION COMPLETE")
    print("=" * 60)
    print(f"Goal: {result.goal}")
    print(f"Total steps: {result.current_step}")
    print(f"Unique findings: {len(result.findings)}")
    print(f"Domains visited: {len(result.visited_urls)}")

    print("\n--- All Findings ---")
    for i, f in enumerate(result.findings, 1):
        print(f"\n{i}. [{f.source_type}] {f.url}")
        print(f"   {f.summary}")

    wrapper.close()


if __name__ == "__main__":
    asyncio.run(main())
