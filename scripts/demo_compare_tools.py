#!/usr/bin/env python3
"""Demo script for tool comparison."""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.compare_tools.main import run_batch


def main():
    print("Running demo comparison...")

    batch_path = Path(__file__).parent / "compare_tools_sample_batch.json"
    output_dir = Path("demo_output")
    output_dir.mkdir(exist_ok=True)

    run_batch(batch_path, output_dir)
    print(f"\nDemo complete! Reports saved in: {output_dir}/")


if __name__ == "__main__":
    main()