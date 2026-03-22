#!/usr/bin/env python3
"""Demo script for tool comparison."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.compare_tools.main import run_comparison
from scripts.compare_tools.models import WebSearchTestCase, WebFetchTestCase


def main():
    print("Running demo comparison...")

    test_cases = [
        WebSearchTestCase(
            query="Python programming language",
            expected_keywords=[" Guido ", "van Rossum", "programming"]
        ),
        WebFetchTestCase(
            url="https://en.wikipedia.org/wiki/Python_(programming_language)",
            expected_keywords=["Python", "programming", "language"]
        ),
    ]

    output_dir = Path("demo_output")
    output_dir.mkdir(exist_ok=True)

    paths = run_comparison(test_cases, output_dir)
    print(f"\nDemo complete! Reports saved to:")
    for p in paths:
        print(f"  - {p}")


if __name__ == "__main__":
    main()