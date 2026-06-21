"""Transcript-specific extraction agent.

Splits a :class:`Transcript` into prepared remarks and Q&A turns, then
extracts the kinds of forward-looking signals (demand, margin, supply
bottlenecks, capex plans) that show up most reliably in earnings calls.
Analyst questions are kept only when management provides an answer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.agents.base import Agent
from src.agents.extraction_agent import (
    ExtractionResult,
    TextChunk,
    chunk_text,
)
from src.agents.state import AgentState
from src.schemas.evidence import Evidence
from src.schemas.transcripts import Transcript, TranscriptTurn

TRANSCRIPT_PROMPT_TEMPLATE = """\
You are a financial analyst extracting structured information from an
earnings-call transcript segment of kind "{section_kind}". Focus on the
following claim types:

  - demand signal (changes in order book, end-market demand)
  - margin pressure (cost inflation, mix, pricing)
  - supply bottleneck (lead times, capacity constraints)
  - capex plan (capital expenditure commitments, capacity additions)
  - sentiment (evasive, hedged, or emphatic tone)

Only extract facts supported by the text. Include at least one short
verbatim quote as evidence. Analyst questions may be treated as facts
only when a management answer immediately confirms them.

Return JSON matching:
{{"entities": [...], "relations": [...], "claims": [...],
  "evidence": [...], "warnings": [...]}}

Text:
\"\"\"{chunk}\"\"\"
"""

QA_QUESTION_LABEL = "__qa_question__"


def _is_analyst(turn: TranscriptTurn) -> bool:
    return turn.role == "analyst"


def _is_management(turn: TranscriptTurn) -> bool:
    return turn.role in {"ceo", "cfo", "executive"}


def _pair_qa_turns(turns: list[TranscriptTurn]) -> list[tuple[TranscriptTurn, list[TranscriptTurn]]]:
    """Pair analyst questions with the management turns that answer them.

    A pair is (analyst_turn, [management_turns]) where the management
    turns are the consecutive non-analyst turns that follow the question
    until the next analyst question or the end of the transcript.
    """
    pairs: list[tuple[TranscriptTurn, list[TranscriptTurn]]] = []
    i = 0
    while i < len(turns):
        turn = turns[i]
        if _is_analyst(turn):
            answers: list[TranscriptTurn] = []
            j = i + 1
            while j < len(turns) and not _is_analyst(turns[j]):
                if _is_management(turns[j]) and turns[j].text.strip():
                    answers.append(turns[j])
                j += 1
            pairs.append((turn, answers))
            i = j
        else:
            i += 1
    return pairs


def _format_turns(turns: list[TranscriptTurn]) -> str:
    return "\n".join(f"{t.speaker} ({t.role}): {t.text}" for t in turns)


def _build_transcript_prompt(section_kind: str, chunk: TextChunk) -> str:
    return TRANSCRIPT_PROMPT_TEMPLATE.format(
        section_kind=section_kind, chunk=chunk.text
    )


def _evidence_for_turn(
    transcript: Transcript, turn: TranscriptTurn, text: str
) -> Evidence:
    return Evidence(
        evidence_id=f"{transcript.transcript_id}:turn:{turn.turn_index}",
        source_type="transcript",
        source_id=transcript.transcript_id,
        title=transcript.title or f"{transcript.ticker} Q{transcript.quarter}",
        url=transcript.url,
        section=turn.section,
        speaker=turn.speaker,
        quote=text,
        retrieved_at=datetime.now(tz=timezone.utc),
        published_at=transcript.published_at,
        confidence=0.85,
        metadata={
            "ticker": transcript.ticker,
            "year": transcript.year,
            "quarter": transcript.quarter,
            "role": turn.role,
            "turn_index": turn.turn_index,
        },
    )


def _call(llm_client: Any, prompt: str) -> Any:
    parse = getattr(llm_client, "parse", None)
    if callable(parse):
        return parse(prompt, ExtractionResult)
    complete = getattr(llm_client, "complete", None)
    if callable(complete):
        return complete(prompt)
    return None


class TranscriptExtractionAgent:
    """Agent that extracts earnings-call signals from a transcript."""

    name: str = "transcript_extraction"

    def __init__(self, llm_client: object | None = None) -> None:
        self.llm_client = llm_client

    def extract(self, transcript: Transcript) -> ExtractionResult:
        """Run a single transcript through the extraction loop."""
        from src.agents.extraction_agent import _coerce_result, _empty_result

        prepared = [t for t in transcript.turns if t.section == "prepared_remarks"]
        qa_pairs = _pair_qa_turns(
            [t for t in transcript.turns if t.section == "qa"]
        )

        accumulator = _empty_result()

        for section_name, segments in (
            ("prepared_remarks", [_format_turns(prepared)] if prepared else []),
            (
                "qa",
                [
                    _format_turns([q, *answers])
                    for q, answers in qa_pairs
                    if answers
                ],
            ),
        ):
            for segment in segments:
                if not segment.strip():
                    continue
                chunks = chunk_text(
                    text=segment,
                    source_id=transcript.transcript_id,
                    source_type="transcript",
                    section=section_name,
                )
                for chunk in chunks:
                    accumulator.evidence.append(
                        _evidence_for_turn(transcript, transcript.turns[0], chunk.text)
                        if transcript.turns
                        else _stub_evidence(transcript, chunk.text)
                    )
                    if self.llm_client is None:
                        continue
                    prompt = _build_transcript_prompt(section_name, chunk)
                    response = _call(self.llm_client, prompt)
                    result = _coerce_result(response)
                    accumulator.entities.extend(result.entities)
                    accumulator.relations.extend(result.relations)
                    accumulator.claims.extend(result.claims)
                    accumulator.evidence.extend(result.evidence)
                    accumulator.warnings.extend(result.warnings)

        if transcript.turns and not prepared and not qa_pairs:
            accumulator.warnings.append(
                "transcript had turns but no section labels matched"
            )
        return accumulator

    def run(self, state: AgentState) -> AgentState:
        if self.llm_client is None:
            state.notes.append("transcript_extraction: no llm_client provided, skipping")
            return state
        return state


def _stub_evidence(transcript: Transcript, text: str) -> Evidence:
    return Evidence(
        evidence_id=f"{transcript.transcript_id}:chunk:0",
        source_type="transcript",
        source_id=transcript.transcript_id,
        title=transcript.title or f"{transcript.ticker} Q{transcript.quarter}",
        url=transcript.url,
        section="unknown",
        quote=text,
        retrieved_at=datetime.now(tz=timezone.utc),
        published_at=transcript.published_at,
        confidence=0.7,
        metadata={
            "ticker": transcript.ticker,
            "year": transcript.year,
            "quarter": transcript.quarter,
        },
    )


def is_transcript_agent(obj: object) -> bool:
    """Runtime helper for ``isinstance``-free protocol checks."""
    return isinstance(obj, Agent)
