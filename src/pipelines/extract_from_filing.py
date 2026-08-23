"""End-to-end extraction pipeline for a single filing."""

from __future__ import annotations

from src.agents.extraction_agent import ExtractionResult
from src.agents.filing_agent import FilingExtractionAgent
from src.schemas.filings import FilingRecord
from src.schemas.llm_config import LLMRunConfig


def _drop_orphan_relations(result: ExtractionResult) -> ExtractionResult:
    """Drop relations that have no evidence attached."""
    kept = [r for r in result.relations if r.evidence]
    dropped = len(result.relations) - len(kept)
    warnings = list(result.warnings)
    if dropped:
        warnings.append(f"dropped {dropped} relations with no evidence")
    return result.model_copy(update={"relations": kept, "warnings": warnings})


def extract_from_filing(
    filing: FilingRecord,
    extraction_agent: FilingExtractionAgent | None = None,
    llm_config: LLMRunConfig | None = None,
) -> ExtractionResult:
    """Run a :class:`FilingRecord` through the filing extraction agent.

    Passing ``llm_config`` builds the typed Pydantic AI extraction client.
    Omitting it preserves the explicit offline extraction mode.
    """
    agent = extraction_agent
    if agent is None:
        client = None
        if llm_config is not None:
            from src.ai.structured_clients import build_generic_extraction_client

            client = build_generic_extraction_client(llm_config)
        agent = FilingExtractionAgent(llm_client=client)
    result = agent.extract(filing)
    return _drop_orphan_relations(result)
