"""End-to-end management sentiment pipeline.

Builds :class:`Evidence` rows from transcript turns and MD&A text blobs,
runs :class:`SentimentAgent`, and returns the resulting
:class:`ManagementSentimentResult`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.agents.sentiment_agent import SentimentAgent
from src.agents.state import AgentState
from src.schemas.analysis import ManagementSentimentResult
from src.schemas.evidence import Evidence
from src.schemas.transcripts import Transcript


def _mda_evidence(
    ticker: str, mda_sections: list[str]
) -> list[Evidence]:
    """Convert raw MD&A strings into :class:`Evidence` rows."""
    now = datetime.now(tz=timezone.utc)
    evidence: list[Evidence] = []
    for index, text in enumerate(mda_sections):
        if text is None or not text.strip():
            continue
        evidence.append(
            Evidence(
                evidence_id=f"mda:{ticker}:{index}",
                source_type="sec_filing",
                source_id=f"mda:{ticker}",
                title=f"{ticker} MD&A",
                section="mda",
                quote=text,
                retrieved_at=now,
                confidence=0.8,
                metadata={"ticker": ticker, "section_index": index},
            )
        )
    return evidence


def _transcript_evidence(
    transcripts: list[Transcript], ticker: str
) -> list[Evidence]:
    """Convert transcript turns into :class:`Evidence` rows."""
    now = datetime.now(tz=timezone.utc)
    evidence: list[Evidence] = []
    for transcript in transcripts:
        for turn in transcript.turns:
            if not turn.text or not turn.text.strip():
                continue
            evidence.append(
                Evidence(
                    evidence_id=(
                        f"{transcript.transcript_id}:turn:{turn.turn_index}"
                    ),
                    source_type="transcript",
                    source_id=transcript.transcript_id,
                    title=transcript.title
                    or f"{transcript.ticker} Q{transcript.quarter}",
                    url=transcript.url,
                    section=turn.section,
                    speaker=turn.speaker,
                    quote=turn.text,
                    retrieved_at=now,
                    published_at=transcript.published_at,
                    confidence=0.8,
                    metadata={
                        "ticker": transcript.ticker or ticker,
                        "year": transcript.year,
                        "quarter": transcript.quarter,
                        "role": turn.role,
                        "turn_index": turn.turn_index,
                    },
                )
            )
    return evidence


def _company_name_from_transcripts(
    transcripts: list[Transcript], ticker: str
) -> str:
    for t in transcripts:
        if t.company_name:
            return t.company_name
    return ticker


def analyze_management_sentiment(
    ticker: str,
    transcripts: list[Transcript],
    mda_sections: list[str],
) -> ManagementSentimentResult:
    """Run :class:`SentimentAgent` and return the result.

    The pipeline:

    1. Builds :class:`Evidence` rows from transcripts and MD&A.
    2. Instantiates a fresh :class:`AgentState`.
    3. Runs :class:`SentimentAgent` and returns its derived
       :class:`ManagementSentimentResult` rebuilt from the resulting
       claims/topics.
    """
    company_name = _company_name_from_transcripts(transcripts, ticker)
    state = AgentState(
        goal=f"analyze management sentiment for {ticker}",
        ticker=ticker,
        company_name=company_name,
    )

    state.evidence.extend(_transcript_evidence(transcripts, ticker))
    state.evidence.extend(_mda_evidence(ticker, mda_sections))

    agent = SentimentAgent()
    agent.run(state)

    sentiment_claims = [
        c for c in state.claims if c.claim_type == "sentiment"
    ]
    if not state.claims and not sentiment_claims:
        return ManagementSentimentResult(
            overall_tone="neutral",
            uncertainty=0.0,
            defensiveness=0.0,
            confidence=0.0,
            guidance_signal="unclear",
            topic_sentiment=[],
            claims=[],
        )

    positive_signals = sum(
        1 for n in state.notes if "overall_tone=positive" in n
    )
    negative_signals = sum(
        1 for n in state.notes if "overall_tone=negative" in n
    )
    mixed_signals = sum(
        1 for n in state.notes if "overall_tone=mixed" in n
    )

    if mixed_signals:
        overall_tone = "mixed"
    elif positive_signals and negative_signals:
        overall_tone = "mixed"
    elif positive_signals:
        overall_tone = "positive"
    elif negative_signals:
        overall_tone = "negative"
    else:
        overall_tone = "neutral"

    guidance_signal = "unclear"
    for n in state.notes:
        if "guidance=raised" in n:
            guidance_signal = "raised"
            break
        if "guidance=lowered" in n:
            guidance_signal = "lowered"
            break
        if "guidance=maintained" in n:
            guidance_signal = "maintained"
            break

    uncertainty = 0.0
    defensiveness = 0.0
    for n in state.notes:
        if "uncertainty=" in n:
            try:
                uncertainty = float(n.split("uncertainty=")[1].split()[0])
            except (IndexError, ValueError):
                uncertainty = 0.0
        if "defensiveness=" in n:
            try:
                defensiveness = float(
                    n.split("defensiveness=")[1].split()[0]
                )
            except (IndexError, ValueError):
                defensiveness = 0.0

    return ManagementSentimentResult(
        overall_tone=overall_tone,
        uncertainty=round(uncertainty, 4),
        defensiveness=round(defensiveness, 4),
        confidence=0.5,
        guidance_signal=guidance_signal,
        topic_sentiment=[],
        claims=sentiment_claims,
    )


__all__ = ["analyze_management_sentiment"]
