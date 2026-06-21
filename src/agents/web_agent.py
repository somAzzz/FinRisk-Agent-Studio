"""Web-evidence extraction agent.

News and other web pages are noisier than SEC filings or company
transcripts, so this agent uses a lower default confidence (0.6) and
focuses on extracting contracts, partnerships, suppliers, customers,
and recent events with explicit URLs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.agents.base import Agent
from src.agents.extraction_agent import (
    ExtractionResult,
    TextChunk,
    chunk_text,
)
from src.agents.state import AgentState
from src.schemas.evidence import Evidence

WEB_PROMPT_TEMPLATE = """\
You are a financial analyst extracting structured information from a
web news article or press release. Focus on:

  - contracts and partnership announcements
  - suppliers and customers named in the article
  - recent material events (M&A, layoffs, plant openings, recalls)
  - policy / regulatory / geopolitical impact

Treat the article with caution. News is often paraphrased, secondary,
or speculative. Only extract facts the article directly states. Each
item must include at least one short verbatim quote as evidence. Use
the article URL in the metadata.

Return JSON matching:
{{"entities": [...], "relations": [...], "claims": [...],
  "evidence": [...], "warnings": [...]}}

URL: {url}
Title: {title}

Text:
\"\"\"{chunk}\"\"\"
"""

WEB_SECTION_KIND = "web_article"
WEB_DEFAULT_CONFIDENCE = 0.6


def _build_web_prompt(url: str | None, title: str | None, chunk: TextChunk) -> str:
    return WEB_PROMPT_TEMPLATE.format(
        url=url or "(none)",
        title=title or "(untitled)",
        chunk=chunk.text,
    )


def _evidence_for_chunk(evidence: Evidence, chunk: TextChunk) -> Evidence:
    return Evidence(
        evidence_id=f"{evidence.evidence_id}:{chunk.char_start}",
        source_type=evidence.source_type,
        source_id=evidence.source_id,
        title=evidence.title,
        url=evidence.url,
        section=evidence.section or WEB_SECTION_KIND,
        speaker=evidence.speaker,
        quote=chunk.text,
        retrieved_at=datetime.now(tz=UTC),
        published_at=evidence.published_at,
        char_start=chunk.char_start,
        char_end=chunk.char_end,
        confidence=WEB_DEFAULT_CONFIDENCE,
        metadata={
            **evidence.metadata,
            "origin_evidence_id": evidence.evidence_id,
        },
    )


def _is_web_evidence(evidence: Evidence) -> bool:
    return evidence.source_type in {"web", "browser"}


def _call(llm_client: Any, prompt: str) -> Any:
    parse = getattr(llm_client, "parse", None)
    if callable(parse):
        return parse(prompt, ExtractionResult)
    complete = getattr(llm_client, "complete", None)
    if callable(complete):
        return complete(prompt)
    return None


class WebExtractionAgent:
    """Agent that extracts contracts/events/partnerships from web evidence."""

    name: str = "web_extraction"

    def __init__(self, llm_client: object | None = None) -> None:
        self.llm_client = llm_client

    def extract(self, web_evidence: list[Evidence]) -> ExtractionResult:
        """Run a batch of web evidence through the extraction loop."""
        from src.agents.extraction_agent import _coerce_result, _empty_result

        accumulator = _empty_result()
        for evidence in web_evidence:
            if not _is_web_evidence(evidence):
                accumulator.warnings.append(
                    f"web_extraction: skipped non-web evidence {evidence.evidence_id}"
                )
                continue
            chunks = chunk_text(
                text=evidence.quote,
                source_id=evidence.source_id,
                source_type=evidence.source_type,
                section=evidence.section or WEB_SECTION_KIND,
            )
            for chunk in chunks:
                accumulator.evidence.append(_evidence_for_chunk(evidence, chunk))
                if self.llm_client is None:
                    continue
                prompt = _build_web_prompt(evidence.url, evidence.title, chunk)
                response = _call(self.llm_client, prompt)
                result = _coerce_result(response)
                accumulator.entities.extend(result.entities)
                accumulator.relations.extend(result.relations)
                accumulator.claims.extend(result.claims)
                accumulator.evidence.extend(result.evidence)
                accumulator.warnings.extend(result.warnings)
        return accumulator

    def run(self, state: AgentState) -> AgentState:
        if self.llm_client is None:
            state.notes.append("web_extraction: no llm_client provided, skipping")
            return state
        web = [e for e in state.evidence if _is_web_evidence(e)]
        result = self.extract(web)
        state.entities.extend(result.entities)
        state.relations.extend(result.relations)
        state.claims.extend(result.claims)
        state.evidence.extend(result.evidence)
        for warning in result.warnings:
            state.notes.append(f"web_extraction: {warning}")
        return state


def is_web_agent(obj: object) -> bool:
    """Runtime helper for ``isinstance``-free protocol checks."""
    return isinstance(obj, Agent)
