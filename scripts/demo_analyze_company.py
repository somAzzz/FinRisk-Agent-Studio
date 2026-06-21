"""Demo: run the MVP ``analyze_company`` pipeline in offline mode.

This script is the canonical ``python scripts/demo_analyze_company.py``
entry point referenced by the Step 11 plan. It uses the JSON fixtures
under ``tests/fixtures/`` so no API keys or network access are required.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make sure the package root is importable when run as a plain script.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.pipelines.analyze_company import (  # noqa: E402
    AnalyzeCompanyArgs,
    analyze_company,
)


def main() -> int:
    """Run the offline demo and print the Markdown report."""
    args = AnalyzeCompanyArgs(
        ticker="DEMO",
        offline_fixtures=True,
    )
    report = analyze_company(args)
    sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
