"""End-to-end extraction pipeline for a single transcript."""

from __future__ import annotations

from src.agents.extraction_agent import ExtractionResult
from src.agents.transcript_agent import TranscriptExtractionAgent
from src.schemas.llm_config import LLMRunConfig
from src.schemas.transcripts import Transcript


def _drop_orphan_relations(result: ExtractionResult) -> ExtractionResult:
    """Drop relations that have no evidence attached."""
    kept = [r for r in result.relations if r.evidence]
    dropped = len(result.relations) - len(kept)
    warnings = list(result.warnings)
    if dropped:
        warnings.append(f"dropped {dropped} relations with no evidence")
    return result.model_copy(update={"relations": kept, "warnings": warnings})


def extract_from_transcript(
    transcript: Transcript,
    extraction_agent: TranscriptExtractionAgent | None = None,
    llm_config: LLMRunConfig | None = None,
) -> ExtractionResult:
    """Run a :class:`Transcript` through the transcript extraction agent."""
    agent = extraction_agent
    if agent is None:
        client = None
        if llm_config is not None:
            from src.ai.structured_clients import build_generic_extraction_client

            client = build_generic_extraction_client(llm_config)
        agent = TranscriptExtractionAgent(llm_client=client)
    result = agent.extract(transcript)
    return _drop_orphan_relations(result)
