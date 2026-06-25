"""Step 2: extract risks from the latest filing.

In demo / cached mode this step reads ``filing_risks`` from the
``aapl_demo_workflow.json`` fixture. In real mode it:

1. Fetches the most recent 10-K / 10-Q via :class:`FilingFetcher`.
2. Asks :class:`SectionParser` to pick the **substantive** Item 1A match
   (longest match per section name, Forward-Looking-Statements
   disclaimer filtered) — defends against the Apple 10-K trap where
   the legal disclaimer matches the Item 1A regex before the real
   section.
3. Splits the section into overlapping chunks via
   :func:`chunk_text` (default 4000 chars / 400 overlap) so the LLM
   sees the **entire** Item 1A — no 1500-char truncation.
4. Runs the chunked extractor (one LLM call per chunk) and
   Pydantic-validates every returned risk.
5. Emits :class:`SectionLocation`, :class:`ChunkValidation`, and
   :class:`LLMCall` rows onto the state so the frontend
   ``StepOutputInspector`` can render the per-step details.

The keyword fallback remains as a safety net for runs where the LLM
client is unavailable.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.evaluation.models import FallbackEvent
from src.schemas.finrisk import (
    ChunkValidation,
    LLMCall,
    SectionLocation,
)
from src.schemas.llm_config import LLMRunConfig
from src.workflows.state import ExtractedRisk, FinRiskWorkflowState
from src.workflows.steps._base import WorkflowStep

logger = logging.getLogger(__name__)

DEMO_FIXTURE_PATH = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "finrisk"
    / "aapl_demo_workflow.json"
)

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

# Default chunking parameters. 4000 chars ≈ 1000 tokens for English
# text — comfortably inside every supported model's context window.
DEFAULT_CHUNK_SIZE = 4000
DEFAULT_CHUNK_OVERLAP = 400


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
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> None:
        super().__init__()
        self._load_fixture = fixture_loader or _default_fixture_loader
        self._filing_fetcher_factory = filing_fetcher
        self._sec_client_factory = sec_client
        self._resolver_factory = ticker_resolver
        self._fixture_path = fixture_path or DEMO_FIXTURE_PATH
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

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
        """Real-mode extraction: fetch → SectionParser → chunked LLM → emit observability rows."""
        from datetime import date

        from src.data.filing_fetcher import FilingFetcher
        from src.data.sec_client import SECClient
        from src.data.sec_sections import SectionParser
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
        try:
            payload = client.get_submissions(ident.cik)
        except Exception as exc:
            logger.info("SEC submissions fetch failed for %s: %s", ticker, exc)
            return [], FallbackEvent(
                step_name=self.name,
                from_mode="live",
                to_mode="cached",
                reason=f"SEC submissions fetch raised {type(exc).__name__}: {exc}",
            )
        recent = payload.get("filings", {}).get("recent", {})
        forms = recent.get("form", []) or []
        accession_numbers = recent.get("accessionNumber", []) or []
        filing_dates = recent.get("filingDate", []) or []
        primary_docs = recent.get("primaryDocument", []) or []

        fetcher_factory = self._filing_fetcher_factory or FilingFetcher
        fetcher = fetcher_factory(client)
        parser = SectionParser()

        candidates: list[FilingMetadata] = []
        for idx in range(min(len(forms), 50)):
            if (forms[idx] or "").upper() not in {"10-K", "10-Q"}:
                continue
            try:
                fd = date.fromisoformat(
                    filing_dates[idx] if idx < len(filing_dates) else ""
                )
            except ValueError:
                continue
            primary_doc = primary_docs[idx] if idx < len(primary_docs) else ""
            candidates.append(
                FilingMetadata(
                    cik=ident.cik,
                    accession_number=accession_numbers[idx],
                    form_type=forms[idx].upper(),
                    filing_date=fd,
                    report_date=None,
                    primary_document=primary_doc,
                    url="",
                )
            )
            if len(candidates) >= 12:
                break

        if not candidates:
            return [], FallbackEvent(
                step_name=self.name,
                from_mode="live",
                to_mode="cached",
                reason="no 10-K / 10-Q in recent submissions",
            )

        # Build the LLMCall sink once — it appends every audit row to
        # state.llm_log so the inspector can render them.
        def sink(call: LLMCall) -> None:
            state.llm_log.append(call)

        client_obj = _build_llm_client(state.request.llm_config, sink)
        if client_obj is None:
            logger.info(
                "FilingRiskExtractor: no LLM client available; falling back to keyword"
            )

        for target in candidates:
            try:
                filing = fetcher.fetch_filing(target)
            except Exception as exc:
                logger.info(
                    "FilingRiskExtractor: failed to fetch %s: %s",
                    target.accession_number,
                    exc,
                )
                continue

            # Re-parse with the production SectionParser to capture
            # precise char_start/char_end (FilingFetcher already parsed
            # but we want the live per-section coordinates for the
            # SectionLocation audit row).
            try:
                raw_html = client.get_filing_html(
                    target.accession_number, target.cik, target.primary_document
                )
                sections_parsed = parser.parse(
                    raw_html, prefer_substantive_match=True
                )
            except Exception:
                sections_parsed = None

            # SectionLocation rows: one per non-empty section that came
            # back from SectionParser. The frontend inspector renders
            # the first one (section_1a) most prominently.
            self._emit_section_locations(state, sections_parsed, target)

            section_text = _select_section_1a(
                filing.sections, sections_parsed
            )
            if not section_text:
                logger.info(
                    "FilingRiskExtractor: %s %s has no substantive Item 1A",
                    target.form_type,
                    target.accession_number,
                )
                continue

            risks: list[ExtractedRisk] = []
            if client_obj is not None:
                try:
                    risks, validations, _calls = self._chunked_llm_extract(
                        client_obj, section_text, target, sink
                    )
                    state.chunk_validations.extend(validations)
                except Exception as exc:
                    logger.info(
                        "FilingRiskExtractor: chunked LLM extract failed (%s): %s",
                        type(exc).__name__,
                        exc,
                    )

            if not risks:
                risks = _keyword_tagged_risks(section_text)
                # Record that we used the keyword fallback.
                state.chunk_validations.append(
                    ChunkValidation(
                        chunk_id=f"keyword-fallback-{target.accession_number}",
                        pydantic_model="ExtractedRisk",
                        ok=True,
                        errors=[],
                        validated_count=len(risks),
                        dropped_count=0,
                        fallback_used="keyword",
                        section_name="section_1a",
                        char_start=None,
                        char_end=None,
                        validated_at=datetime.now(tz=UTC),
                    )
                )

            if not risks:
                continue

            # Tag each risk with the source accession for traceability.
            for r in risks:
                r.source = (
                    f"sec_filing:{target.accession_number}:{target.form_type}"
                )
                r.filing_section = "section_1a"
            return risks, None

        return [], FallbackEvent(
            step_name=self.name,
            from_mode="live",
            to_mode="cached",
            reason="no substantive risk factors found in recent filings",
        )

    # -- internal helpers ----------------------------------------------

    def _emit_section_locations(
        self,
        state: FinRiskWorkflowState,
        sections_parsed: dict | None,
        target: Any,
    ) -> None:
        """Append one :class:`SectionLocation` per matched section."""
        if not sections_parsed:
            return
        for name, sec in sections_parsed.items():
            if name == "full_text":
                continue
            try:
                char_count = sec.char_end - sec.char_start
            except AttributeError:
                continue
            if char_count <= 0:
                continue
            state.section_locations.append(
                SectionLocation(
                    section_name=name,
                    char_start=sec.char_start,
                    char_end=sec.char_end,
                    char_count=char_count,
                    matched_against_real_section=(name == "section_1a" and char_count >= 500),
                    matched_section_reason=(
                        "regex: longest-match with FLS disclaimer stripped"
                        if name == "section_1a"
                        else "regex: first match"
                    ),
                    is_disclaimer_text=False,
                    filing_accession=target.accession_number,
                    filing_form=target.form_type,
                )
            )

    def _chunked_llm_extract(
        self,
        client_obj: Any,
        section_text: str,
        target: Any,
        sink: Callable[[LLMCall], None],
    ) -> tuple[list[ExtractedRisk], list[ChunkValidation], list[LLMCall]]:
        """Dispatch to the canonical chunked extractor if available.

        Both :class:`EdgarLLMClient` and :class:`DeepSeekClient` now
        expose ``extract_risks_chunked`` (the v18.1 refactor). When the
        client does not implement it, we fall back to the legacy
        single-shot ``extract_risks`` and synthesise a single
        ChunkValidation row from the dict result.
        """
        if hasattr(client_obj, "extract_risks_chunked"):
            return client_obj.extract_risks_chunked(
                section_text,
                company_name="live",
                year=0,
                source_id=f"sec:{target.accession_number}",
                chunk_size=self._chunk_size,
                chunk_overlap=self._chunk_overlap,
                step_name=self.name,
            )
        # Legacy path: single-shot dict response.
        result = client_obj.extract_risks(
            section_text, company_name="live", year=0
        )
        risks: list[ExtractedRisk] = []
        errors: list[str] = []
        for item in result.get("risks", []):
            if not isinstance(item, dict):
                continue
            rf = item.get("risk_factor") or ""
            quote = item.get("quote") or ""
            if not rf or not quote:
                continue
            try:
                risks.append(
                    ExtractedRisk(
                        risk_factor=str(rf),
                        severity=int(item.get("severity") or 3),
                        evidence_quote=str(quote),
                        source="sec_filing:live:llm",
                        filing_section="section_1a",
                        confidence=float(item.get("confidence") or 0.7),
                    )
                )
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
        validation = ChunkValidation(
            chunk_id=f"legacy-{target.accession_number}",
            pydantic_model="ExtractedRisk",
            ok=not errors,
            errors=errors,
            validated_count=len(risks),
            dropped_count=0,
            fallback_used="llm",
            section_name="section_1a",
            char_start=None,
            char_end=None,
            validated_at=datetime.now(tz=UTC),
        )
        return risks, [validation], []


def _select_section_1a(
    filing_sections: dict[str, str],
    parsed: dict | None,
) -> str:
    """Pick the best Item 1A text, preferring the parser's coordinates.

    The parser's output has been FLS-filtered already; the
    :class:`FilingFetcher` legacy fallback (when parser raised) is the
    raw regex extraction, which we use as a last resort.
    """
    if parsed and parsed.get("section_1a"):
        return parsed["section_1a"].text.strip()
    return (filing_sections.get("section_1a") or "").strip()


def _build_llm_client(
    llm_config: LLMRunConfig | None,
    sink: Callable[[LLMCall], None] | None = None,
) -> Any | None:
    """Return a configured LLM client, or ``None`` on failure.

    Extracted into a top-level function so unit tests can monkey patch
    it. ``sink`` is forwarded to both :class:`EdgarLLMClient` and
    :class:`DeepSeekClient` so every chat call emits an
    :class:`LLMCall` row onto the workflow state.
    """
    config = llm_config or LLMRunConfig()
    provider = config.provider
    try:
        if provider == "deepseek":
            from src.llm.deepseek_client import DeepSeekClient

            return DeepSeekClient(
                base_url=config.base_url,
                model=config.model,
                llm_call_sink=sink,
            )
        from src.llm.client import EdgarLLMClient

        defaults: dict[str, tuple[str, str, str]] = {
            "sglang": (
                os.environ.get("SGLANG_BASE_URL", "http://localhost:30000/v1"),
                os.environ.get("SGLANG_API_KEY", "EMPTY"),
                os.environ.get("SGLANG_MODEL", "Qwen/Qwen3.5-35B-A3B"),
            ),
            "vllm": (
                os.environ.get("VLLM_BASE_URL", "http://localhost:8000/v1"),
                os.environ.get("VLLM_API_KEY", "dummy"),
                os.environ.get("VLLM_MODEL", "Qwen/Qwen3.5-35B-A3B"),
            ),
            "openai": (
                os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                os.environ.get("OPENAI_API_KEY", "REPLACE_ME"),
                os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            ),
        }
        if provider in defaults:
            base_url, api_key, model = defaults[provider]
        else:
            base_url, api_key, model = defaults["sglang"]
        return EdgarLLMClient(
            base_url=config.base_url or base_url,
            api_key=api_key,
            model=config.model or model,
            llm_call_sink=sink,
            provider=provider,
        )
    except Exception:
        return None


# Backwards-compat shim: a handful of older tests import the
# ``_risk_section_text`` helper from this module. The new
# ``_select_section_1a`` returns the same value.
def _risk_section_text(sections: dict[str, str]) -> str:
    """Legacy entry point kept for backwards compatibility."""
    text = (sections.get("section_1a") or "").strip()
    if len(text) >= 500:
        return text
    return _keyword_fallback_section(sections)


def _keyword_fallback_section(sections: dict[str, str]) -> str:
    """Last-resort regex extraction when the parser missed Item 1A."""
    full_text = sections.get("full_text") or ""
    heading_re = re.compile(
        r"item\s*1\s*a\s*[\.\:\-–— ]?\s*risk\s*factors",
        re.IGNORECASE,
    )
    boundary_re = re.compile(
        r"item\s*(?:1\s*b|2)\s*[\.\:\-–—]",
        re.IGNORECASE,
    )
    candidates: list[str] = []
    for match in heading_re.finditer(full_text):
        boundary = boundary_re.search(full_text, match.end())
        end = boundary.start() if boundary is not None else len(full_text)
        chunk = full_text[match.start():end].strip()
        if len(chunk) >= 500:
            candidates.append(chunk)
    if not candidates:
        return ""
    return max(candidates, key=len)


def _keyword_tagged_risks(section_text: str) -> list[ExtractedRisk]:
    """Walk ``section_1a`` text and emit one risk per keyword hit."""
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


__all__ = [
    "DEFAULT_CHUNK_OVERLAP",
    "DEFAULT_CHUNK_SIZE",
    "DEMO_FIXTURE_PATH",
    "FilingRiskExtractorStep",
]