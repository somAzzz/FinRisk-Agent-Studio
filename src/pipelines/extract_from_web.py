"""End-to-end extraction pipeline for a batch of web evidence."""

from __future__ import annotations

from src.agents.extraction_agent import ExtractionResult
from src.agents.web_agent import WebExtractionAgent
from src.schemas.evidence import Evidence


def _drop_orphan_relations(result: ExtractionResult) -> ExtractionResult:
    """Drop relations that have no evidence attached."""
    kept = [r for r in result.relations if r.evidence]
    dropped = len(result.relations) - len(kept)
    warnings = list(result.warnings)
    if dropped:
        warnings.append(f"dropped {dropped} relations with no evidence")
    return result.model_copy(update={"relations": kept, "warnings": warnings})


def extract_from_web(
    web_evidence: list[Evidence],
    extraction_agent: WebExtractionAgent | None = None,
) -> ExtractionResult:
    """Run a batch of web :class:`Evidence` rows through the web agent."""
    agent = extraction_agent or WebExtractionAgent()
    result = agent.extract(web_evidence)
    return _drop_orphan_relations(result)
