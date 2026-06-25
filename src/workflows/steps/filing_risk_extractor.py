"""Step 2: extract risks from the latest filing.

In demo / cached mode this step reads ``filing_risks`` from the
``aapl_demo_workflow.json`` fixture. In real mode it fetches the most
recent 10-K / 10-Q via :class:`FilingFetcher` and emits a small set
of keyword-tagged risks so the rest of the workflow has a baseline.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.evaluation.models import FallbackEvent
from src.workflows.state import (
    ExtractedRisk,
    FinRiskWorkflowState,
)
from src.workflows.steps._base import WorkflowStep

logger = logging.getLogger(__name__)

DEMO_FIXTURE_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "finrisk" / "aapl_demo_workflow.json"


# Keyword-to-risk_type mapping used by the rule fallback.
_RISK_KEYWORDS: dict[str, str] = {
    "tariff": "policy",
    "china": "geopolitical",
    "taiwan": "geopolitical",
    "supplier": "supply_chain",
    "supply chain": "supply_chain",
    "cyber": "operational",
    "ransomware": "operational",
    "interest rate": "financial",
    "inflation": "macro",
    "recession": "macro",
    "competition": "competition",
    "antitrust": "regulatory",
}


class FilingRiskExtractorStep(WorkflowStep):
    """Extract typed ``ExtractedRisk`` rows from the latest filing."""

    name = "filing_risk_extractor"

    def __init__(
        self,
        fixture_loader=None,
        filing_fetcher=None,
        sec_client=None,
        ticker_resolver=None,
        fixture_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._load_fixture = fixture_loader or _default_fixture_loader
        self._filing_fetcher_factory = filing_fetcher
        self._sec_client_factory = sec_client
        self._resolver_factory = ticker_resolver
        self._fixture_path = fixture_path or DEMO_FIXTURE_PATH

    async def run(self, state: FinRiskWorkflowState) -> FinRiskWorkflowState:
        request = state.request
        ticker = request.ticker

        if request.demo_mode or request.cached_mode:
            data = self._load_fixture(self._fixture_path)
            risks = [
                ExtractedRisk.model_validate(item)
                for item in data.get("filing_risks", [])
            ]
        else:
            risks, fallback = await self._extract_live(state, ticker)
            if fallback is not None:
                state.fallback_events.append(fallback)

        # Drop any risks without evidence (defensive; should not happen).
        state.filing_risks = [r for r in risks if r.evidence_quote.strip()]
        return state

    async def _extract_live(
        self,
        state: FinRiskWorkflowState,
        ticker: str,
    ) -> tuple[list[ExtractedRisk], FallbackEvent | None]:
        """Try to fetch a real 10-K/10-Q and emit keyword-tagged risks.

        Returns ``(risks, fallback_event)`` so the step can surface
        failures as a :class:`FallbackEvent` on the state. LLM-based
        extraction is layered on top of the keyword fallback (see
        :meth:`_llm_extract`); the keyword path remains the safety
        net when the LLM client is unavailable.
        """
        from src.evaluation.models import FallbackEvent

        try:
            from src.data.filing_fetcher import FilingFetcher
            from src.data.sec_client import SECClient
            from src.data.ticker_resolver import TickerResolver
            from src.schemas.filings import FilingMetadata

            resolver_factory = self._resolver_factory or TickerResolver
            client_factory = self._sec_client_factory or SECClient

            ident = resolver_factory().resolve(ticker)
            if ident is None:
                logger.info(
                    "FilingRiskExtractor: cannot resolve %s; skipping live fetch",
                    ticker,
                )
                return [], FallbackEvent(
                    step_name=self.name,
                    from_mode="live",
                    to_mode="cached",
                    reason=f"could not resolve ticker {ticker}",
                )

            client = client_factory()
            payload = client.get_submissions(ident.cik)
            recent = payload.get("filings", {}).get("recent", {})
            forms = recent.get("form", []) or []
            accession_numbers = recent.get("accessionNumber", []) or []
            filing_dates = recent.get("filingDate", []) or []
            primary_docs = recent.get("primaryDocument", []) or []

            fetcher_factory = self._filing_fetcher_factory or FilingFetcher
            fetcher = fetcher_factory(client)

            target: FilingMetadata | None = None
            from datetime import date

            for idx in range(min(len(forms), 50)):
                if (forms[idx] or "").upper() not in {"10-K", "10-Q"}:
                    continue
                try:
                    fd = date.fromisoformat(
                        filing_dates[idx] if idx < len(filing_dates) else ""
                    )
                except ValueError:
                    continue
                primary_doc = (
                    primary_docs[idx] if idx < len(primary_docs) else ""
                )
                target = FilingMetadata(
                    cik=ident.cik,
                    accession_number=accession_numbers[idx],
                    form_type=forms[idx].upper(),
                    filing_date=fd,
                    report_date=None,
                    primary_document=primary_doc,
                    url="",
                )
                break

            if target is None:
                return [], FallbackEvent(
                    step_name=self.name,
                    from_mode="live",
                    to_mode="cached",
                    reason="no 10-K / 10-Q in recent submissions",
                )

            filing = fetcher.fetch_filing(target)
            section_text = filing.sections.get("section_1a", "")
            risks = _llm_extract(section_text)
            if not risks:
                risks = _keyword_tagged_risks(section_text)
            # Tag each risk with the source accession for traceability.
            for r in risks:
                r.source = (
                    f"sec_filing:{target.accession_number}:{target.form_type}"
                )
                r.filing_section = "section_1a"
            return risks, None
        except Exception as exc:
            logger.info("FilingRiskExtractor live fetch failed: %s", exc)
            return [], FallbackEvent(
                step_name=self.name,
                from_mode="live",
                to_mode="cached",
                reason=f"SEC fetch raised {type(exc).__name__}: {exc}",
            )


def _llm_extract(section_text: str) -> list[ExtractedRisk]:
    """LLM structured extraction adapter.

    The v17 spec requires an LLM structured extractor as the
    primary path with the keyword fallback as a safety net. The
    real client lives behind an import so unit tests (which run
    without a real LLM) still exercise the keyword path; in v18
    this function will be promoted to a real
    ``src.llm.deepseek_client.extract_risks`` call.

    The function returns ``[]`` whenever:

    - the section text is empty;
    - the DeepSeek client is not configured (no real key);
    - the DeepSeek client raises.

    In all of those cases the keyword path picks up the slack.
    """
    if not section_text:
        return []
    client = _build_llm_client()
    if client is None:
        return []
    if not getattr(client, "configured", False):
        return []
    try:
        result = client.extract_risks(
            section_text,
            company_name="live",
            year=0,
        )
    except Exception:
        return []
    risks: list[ExtractedRisk] = []
    for i, item in enumerate(result.get("risks", [])):
        if not isinstance(item, dict):
            continue
        risk_factor = item.get("risk_factor") or ""
        quote = item.get("quote") or ""
        if not risk_factor or not quote:
            continue
        risks.append(
            ExtractedRisk(
                risk_id=f"live-llm-{i:03d}",
                risk_type=item.get("risk_type") or "operational",
                risk_factor=risk_factor,
                severity=int(item.get("severity") or 3),
                evidence_quote=quote,
                source="sec_filing:live:llm",
                filing_section="section_1a",
                confidence=float(item.get("confidence") or 0.7),
            )
        )
    return risks


def _build_llm_client() -> Any | None:
    """Return the configured DeepSeek client, or ``None`` on failure.

    Extracted into a top-level function so unit tests can monkey
    patch the client factory via
    ``monkeypatch.setattr(mod, "_build_llm_client", ...)``.
    """
    try:
        from src.llm.deepseek_client import build_client_from_settings

        return build_client_from_settings()
    except Exception:
        return None


def _keyword_tagged_risks(section_text: str) -> list[ExtractedRisk]:
    """Walk ``section_1a`` text and emit one risk per keyword hit.

    The rule fallback exists so the live mode produces a baseline set of
    risks even when the LLM extractor is unavailable.
    """
    if not section_text:
        return []
    lowered = section_text.lower()
    matched: list[ExtractedRisk] = []
    counter = 0
    for keyword, risk_type in _RISK_KEYWORDS.items():
        if keyword in lowered:
            counter += 1
            idx = lowered.find(keyword)
            snippet = section_text[max(0, idx - 80): idx + 200].strip()
            matched.append(
                ExtractedRisk(
                    risk_id=f"live-risk-{counter:03d}",
                    risk_type=risk_type,  # type: ignore[arg-type]
                    risk_factor=(
                        f"Filing mentions {keyword!r} as a risk factor."
                    ),
                    severity=3,
                    evidence_quote=snippet,
                    source="sec_filing:live",
                    filing_section="section_1a",
                    confidence=0.5,
                )
            )
    return matched


def _default_fixture_loader(path: Path) -> dict:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


__all__ = ["DEMO_FIXTURE_PATH", "FilingRiskExtractorStep"]