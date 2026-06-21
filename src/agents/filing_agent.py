"""Filing-specific extraction agent.

The filing agent focuses on a small, well-defined set of SEC sections
(``section_1``, ``section_1A``, ``section_7``, ``section_7A``) and falls
back to ``full_text`` if those are missing. It reuses
:func:`chunk_text` and the generic :class:`ExtractionResult` from the
shared :mod:`src.agents.extraction_agent` module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.agents.base import Agent
from src.agents.extraction_agent import (
    ExtractionAgent,
    ExtractionResult,
    TextChunk,
    chunk_text,
)
from src.agents.state import AgentState
from src.schemas.evidence import Evidence
from src.schemas.filings import FilingRecord

FILING_SECTIONS: tuple[str, ...] = (
    "section_1",
    "section_1A",
    "section_7",
    "section_7A",
    "full_text",
)

FILING_PROMPT_TEMPLATE = """\
You are a financial analyst extracting structured information from a
U.S. SEC filing section. The section kind is "{section_kind}" and
favors the following entity and relation kinds:

  - entities: supplier, customer, product, segment, competitor, risk
  - relations: supplies_to, customer_of, sells_product, depends_on,
    mentions_risk
  - claims: risk, supply_chain

Only extract facts that are directly supported by the text. For each
relation and claim, include at least one short verbatim quote as
evidence. If you are unsure, lower the confidence score or skip the
item entirely.

Return JSON matching:
{{"entities": [...], "relations": [...], "claims": [...],
  "evidence": [...], "warnings": [...]}}

Text:
\"\"\"{chunk}\"\"\"
"""


def _build_filing_prompt(section_kind: str, chunk: TextChunk) -> str:
    return FILING_PROMPT_TEMPLATE.format(section_kind=section_kind, chunk=chunk.text)


def _select_filing_sections(filing: FilingRecord) -> list[tuple[str, str]]:
    """Return the (section_name, text) pairs we want to process, in order."""
    selected: list[tuple[str, str]] = []
    for name in FILING_SECTIONS:
        text = filing.sections.get(name)
        if text:
            selected.append((name, text))
    if not selected:
        joined = "\n\n".join(f"{k}: {v}" for k, v in filing.sections.items())
        if joined:
            selected.append(("full_text", joined))
    return selected


def _evidence_from_chunk(
    filing: FilingRecord,
    section_name: str,
    chunk: TextChunk,
) -> Evidence:
    """Build an :class:`Evidence` row that anchors a chunk in the filing."""
    source_id = (
        filing.accession_number
        or f"{filing.cik}-{filing.form_type}-{filing.year or 0}"
    )
    return Evidence(
        evidence_id=f"{source_id}:{section_name}:{chunk.char_start}",
        source_type="sec_filing",
        source_id=source_id,
        title=filing.company_name or filing.cik,
        url=filing.url,
        section=section_name,
        quote=chunk.text,
        retrieved_at=datetime.now(tz=timezone.utc),
        char_start=chunk.char_start,
        char_end=chunk.char_end,
        confidence=0.9,
        metadata={
            "cik": filing.cik,
            "ticker": filing.ticker,
            "form_type": filing.form_type,
            "year": filing.year,
        },
    )


class FilingExtractionAgent:
    """Agent that extracts supply-chain / risk facts from a filing."""

    name: str = "filing_extraction"

    def __init__(self, llm_client: object | None = None) -> None:
        self.llm_client = llm_client
        self._generic = ExtractionAgent(llm_client=llm_client)

    def extract(self, filing: FilingRecord) -> ExtractionResult:
        """Run a single filing through the extraction loop."""
        from src.agents.extraction_agent import _coerce_result, _empty_result

        sections = _select_filing_sections(filing)
        if not sections:
            return _empty_result()
        if self.llm_client is None:
            # Without an LLM there is nothing to extract; emit empty
            # results so the caller can distinguish "skipped" from "ran".
            return _empty_result()

        accumulator = _empty_result()
        for section_name, text in sections:
            chunks = chunk_text(
                text=text,
                source_id=filing.accession_number or filing.cik,
                source_type="sec_filing",
                section=section_name,
            )
            for chunk in chunks:
                accumulator.evidence.append(
                    _evidence_from_chunk(filing, section_name, chunk)
                )
                prompt = _build_filing_prompt(section_name, chunk)
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
            state.notes.append("filing_extraction: no llm_client provided, skipping")
            return state
        return self._generic.run(state)


def _call(llm_client: Any, prompt: str) -> Any:
    """Dispatch to whichever LLM method the client exposes."""
    parse = getattr(llm_client, "parse", None)
    if callable(parse):
        return parse(prompt, ExtractionResult)
    complete = getattr(llm_client, "complete", None)
    if callable(complete):
        return complete(prompt)
    return None


def is_filing_agent(obj: object) -> bool:
    """Runtime helper for ``isinstance``-free protocol checks."""
    return isinstance(obj, Agent)
