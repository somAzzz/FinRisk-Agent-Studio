"""Step 1: resolve a ticker into a CompanyProfile."""

from __future__ import annotations

import logging
from pathlib import Path

from src.workflows.state import (
    CompanyProfile,
    FinRiskWorkflowState,
    utcnow,
)
from src.workflows.steps._base import WorkflowStep

logger = logging.getLogger(__name__)

DEMO_FIXTURE_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "finrisk" / "aapl_demo_workflow.json"


class CompanyResolverStep(WorkflowStep):
    """Resolve a ticker / company name into a typed CompanyProfile."""

    name = "company_resolver"
    # Critical: the rest of the workflow cannot proceed without a company.
    critical = True

    def __init__(
        self,
        fixture_loader=None,
        ticker_resolver=None,
        fixture_path: Path | None = None,
    ) -> None:
        super().__init__(critical=True)
        # Inject dependencies for testability.
        self._load_fixture = fixture_loader or _default_fixture_loader
        self._resolver_factory = ticker_resolver
        self._fixture_path = fixture_path or DEMO_FIXTURE_PATH

    async def run(self, state: FinRiskWorkflowState) -> FinRiskWorkflowState:
        request = state.request
        ticker = request.ticker

        if request.demo_mode or request.cached_mode:
            data = self._load_fixture(self._fixture_path)
            fixture_company = data["company"]
            # Override the fixture ticker / name with the request so demo
            # works for any user input without re-curating fixtures.
            profile = CompanyProfile(
                company_name=fixture_company["company_name"],
                ticker=ticker,
                cik=fixture_company.get("cik"),
                filing_type=fixture_company.get("filing_type"),
                analysis_year=fixture_company.get("analysis_year"),
                source="fixture",
                resolved_at=utcnow(),
            )
        else:
            from src.data.ticker_resolver import TickerResolver

            resolver_factory = self._resolver_factory or TickerResolver
            ident = resolver_factory().resolve(ticker)
            if ident is None:
                raise RuntimeError(
                    f"unable to resolve ticker {ticker!r} to a CIK"
                )
            profile = CompanyProfile(
                company_name=ident.name or ticker,
                ticker=ticker,
                cik=ident.cik,
                filing_type="10-K",
                analysis_year=request.year,
                source=ident.source,
                resolved_at=ident.resolved_at or utcnow(),
            )

        state.company = profile
        return state


def _default_fixture_loader(path: Path) -> dict:
    """Read a JSON fixture from disk. Kept importable for test stubs."""
    import json

    return json.loads(path.read_text(encoding="utf-8"))


__all__ = ["DEMO_FIXTURE_PATH", "CompanyResolverStep"]