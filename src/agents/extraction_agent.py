"""Generic extraction agent: chunk text, prompt an LLM, accumulate results.

This module provides a small, opinionated extraction loop. Concrete source
agents (filings, transcripts, web) reuse :func:`chunk_text` and the same
:class:`ExtractionResult` container, so the rest of the pipeline can be
source-agnostic.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from src.agents.base import Agent
from src.agents.state import AgentState
from src.schemas.claims import Claim
from src.schemas.entities import Entity
from src.schemas.evidence import Evidence
from src.schemas.relations import Relation

FILING_PROMPT_TEMPLATE = """\
You are a financial analyst extracting structured information from a
U.S. SEC filing. Only extract facts that are directly supported by the
text below. For each entity, relation, and claim, include at least one
short verbatim quote as evidence. If you are unsure, lower the confidence
score and skip the item entirely.

Return JSON that conforms to the following schema:
{schema}

Text:
\"\"\"{chunk}\"\"\"
"""

DEFAULT_RELATION_CONFIDENCE = 0.7


class TextChunk(BaseModel):
    """A character-windowed slice of a longer source document."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_type: str
    section: str | None = None
    text: str
    char_start: int
    char_end: int


class ExtractionResult(BaseModel):
    """The combined output of a single extraction pass."""

    model_config = ConfigDict(extra="forbid")

    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class StructuredExtractionClient(Protocol):
    """Typed model boundary used by source extraction agents."""

    def extract(self, prompt: str) -> ExtractionResult:
        """Return one Pydantic-validated extraction result."""
        ...


def chunk_text(
    text: str,
    source_id: str,
    source_type: str,
    section: str | None = None,
    chunk_size: int = 6000,
    overlap: int = 400,
) -> list[TextChunk]:
    """Split ``text`` into overlapping character windows.

    Each chunk records its absolute ``char_start`` and ``char_end`` within
    the original text. The last chunk is allowed to be shorter than
    ``chunk_size``. The function never produces an empty list; if the
    input is empty, a single zero-width chunk is returned so downstream
    callers can treat the result uniformly.
    """
    if not text:
        return [
            TextChunk(
                source_id=source_id,
                source_type=source_type,
                section=section,
                text="",
                char_start=0,
                char_end=0,
            )
        ]

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    chunks: list[TextChunk] = []
    step = chunk_size - overlap
    pos = 0
    n = len(text)
    while pos < n:
        end = min(pos + chunk_size, n)
        chunks.append(
            TextChunk(
                source_id=source_id,
                source_type=source_type,
                section=section,
                text=text[pos:end],
                char_start=pos,
                char_end=end,
            )
        )
        if end == n:
            break
        pos += step
    return chunks


def _empty_result() -> ExtractionResult:
    return ExtractionResult()


def _build_prompt(chunk: TextChunk) -> str:
    schema_hint = (
        '{"entities": [...], "relations": [...], "claims": [...], '
        '"evidence": [...], "warnings": [...]}'
    )
    return FILING_PROMPT_TEMPLATE.format(schema=schema_hint, chunk=chunk.text)


def _merge_into_state(state: AgentState, result: ExtractionResult) -> None:
    """Accumulate ``result`` into the relevant lists of ``state``."""
    state.entities.extend(result.entities)
    state.relations.extend(result.relations)
    state.claims.extend(result.claims)
    state.evidence.extend(result.evidence)
    for warning in result.warnings:
        state.notes.append(f"extraction: {warning}")


def _call_llm(
    llm_client: StructuredExtractionClient,
    prompt: str,
) -> ExtractionResult:
    """Call the typed extraction boundary and preserve failure metadata."""
    try:
        result = llm_client.extract(prompt)
    except Exception as exc:
        return _empty_result().model_copy(
            update={"warnings": [f"typed extraction failed: {exc}"]}
        )
    if not isinstance(result, ExtractionResult):
        return _empty_result().model_copy(
            update={"warnings": ["typed extraction returned an invalid result"]}
        )
    return result


class ExtractionAgent:
    """Source-agnostic agent that extracts entities/relations/claims.

    The agent walks the ``evidence`` already attached to the runtime
    :class:`AgentState`, chunks it, prompts the configured LLM client, and
    accumulates the parsed :class:`ExtractionResult` back into the state.

    If no ``llm_client`` is provided the agent is a no-op aside from
    appending a note to ``state.notes``; this keeps the rest of the
    pipeline testable without an actual LLM in the loop.
    """

    name: str = "extraction"

    def __init__(
        self, llm_client: StructuredExtractionClient | None = None
    ) -> None:
        self.llm_client = llm_client

    def run(self, state: AgentState) -> AgentState:
        if self.llm_client is None:
            state.notes.append("extraction: no llm_client provided, skipping")
            return state

        for evidence in list(state.evidence):
            chunks = chunk_text(
                text=evidence.quote,
                source_id=evidence.source_id,
                source_type=evidence.source_type,
                section=evidence.section,
            )
            for chunk in chunks:
                prompt = _build_prompt(chunk)
                result = _call_llm(self.llm_client, prompt)
                _merge_into_state(state, result)

        return state


def is_agent(obj: object) -> bool:
    """Runtime helper: does ``obj`` quack like an :class:`Agent`?"""
    return isinstance(obj, Agent)
