"""End-to-end extraction pipeline for a single filing."""

from __future__ import annotations

from src.agents.extraction_agent import ExtractionResult
from src.agents.filing_agent import FilingExtractionAgent
from src.schemas.filings import FilingRecord


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
) -> ExtractionResult:
    """Run a :class:`FilingRecord` through the filing extraction agent.

    A default :class:`FilingExtractionAgent` (with no LLM client) is
    instantiated if none is supplied, which still produces the chunk
    evidence row but no entities, relations, or claims.
    """
    agent = extraction_agent or FilingExtractionAgent()
    result = agent.extract(filing)
    return _drop_orphan_relations(result)
