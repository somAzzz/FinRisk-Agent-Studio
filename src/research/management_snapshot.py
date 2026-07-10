"""Evidence-backed management signal snapshots and quarter comparisons."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.pipelines.analyze_sentiment import analyze_management_sentiment
from src.schemas.analysis import GuidanceSignal, OverallTone, SentimentLabel, Topic
from src.schemas.transcripts import Transcript

ChangeDirection = Literal["strengthened", "weakened", "increased", "decreased", "changed"]


class ManagementTopicSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: Topic
    sentiment: SentimentLabel
    confidence: float
    evidence_ids: list[str] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)


class ManagementPeriodSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    year: int
    quarter: int
    transcript_id: str
    provider: str
    source_url: str | None = None
    published_at: datetime | None = None
    overall_tone: OverallTone
    prepared_remarks_tone: SentimentLabel = "unclear"
    qa_tone: SentimentLabel = "unclear"
    uncertainty: float
    defensiveness: float
    guidance_signal: GuidanceSignal
    topic_signals: list[ManagementTopicSignal] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class ManagementSignalChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str
    previous_value: str | float
    current_value: str | float
    direction: ChangeDirection
    previous_period: str
    current_period: str
    evidence_ids: list[str] = Field(default_factory=list)


class ManagementComparisonResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current: ManagementPeriodSnapshot
    previous: ManagementPeriodSnapshot | None = None
    changes: list[ManagementSignalChange] = Field(default_factory=list)


def build_management_snapshot(transcript: Transcript) -> ManagementPeriodSnapshot:
    """Analyze one transcript without detaching signals from source turns."""
    result = analyze_management_sentiment(
        ticker=transcript.ticker,
        transcripts=[transcript],
        mda_sections=[],
    )
    topic_signals = [
        ManagementTopicSignal(
            topic=topic.topic,
            sentiment=topic.sentiment,
            confidence=topic.confidence,
            evidence_ids=[item.evidence_id for item in topic.evidence],
            quotes=[item.quote for item in topic.evidence if item.quote],
        )
        for topic in result.topic_sentiment
    ]
    prepared_tone: SentimentLabel = "unclear"
    qa_tone: SentimentLabel = "unclear"
    evidence_ids: set[str] = set()
    for claim in result.claims:
        evidence_ids.update(item.evidence_id for item in claim.evidence)
        if claim.statement.startswith("Prepared remarks tone:"):
            prepared_tone = _claim_tone(claim.statement)
        elif claim.statement.startswith("Q&A tone:"):
            qa_tone = _claim_tone(claim.statement)
    return ManagementPeriodSnapshot(
        ticker=transcript.ticker.upper(),
        year=transcript.year,
        quarter=transcript.quarter,
        transcript_id=transcript.transcript_id,
        provider=transcript.provider,
        source_url=transcript.url,
        published_at=transcript.published_at,
        overall_tone=result.overall_tone,
        prepared_remarks_tone=prepared_tone,
        qa_tone=qa_tone,
        uncertainty=result.uncertainty,
        defensiveness=result.defensiveness,
        guidance_signal=result.guidance_signal,
        topic_signals=topic_signals,
        evidence_ids=sorted(evidence_ids),
    )


def compare_management_snapshots(
    previous: ManagementPeriodSnapshot,
    current: ManagementPeriodSnapshot,
) -> list[ManagementSignalChange]:
    """Describe only observable signal changes between two calls."""
    if previous.ticker != current.ticker:
        raise ValueError("management snapshots must belong to the same ticker")
    changes: list[ManagementSignalChange] = []
    previous_period = f"{previous.year}Q{previous.quarter}"
    current_period = f"{current.year}Q{current.quarter}"
    evidence = sorted(set(previous.evidence_ids + current.evidence_ids))

    for dimension in (
        "overall_tone",
        "prepared_remarks_tone",
        "qa_tone",
        "guidance_signal",
    ):
        before = getattr(previous, dimension)
        after = getattr(current, dimension)
        if before != after:
            changes.append(
                ManagementSignalChange(
                    dimension=dimension,
                    previous_value=before,
                    current_value=after,
                    direction=_tone_direction(before, after),
                    previous_period=previous_period,
                    current_period=current_period,
                    evidence_ids=evidence,
                )
            )

    for dimension in ("uncertainty", "defensiveness"):
        before = getattr(previous, dimension)
        after = getattr(current, dimension)
        if abs(after - before) >= 0.05:
            changes.append(
                ManagementSignalChange(
                    dimension=dimension,
                    previous_value=before,
                    current_value=after,
                    direction="increased" if after > before else "decreased",
                    previous_period=previous_period,
                    current_period=current_period,
                    evidence_ids=evidence,
                )
            )

    previous_topics = {item.topic: item for item in previous.topic_signals}
    current_topics = {item.topic: item for item in current.topic_signals}
    for topic in sorted(previous_topics.keys() & current_topics.keys()):
        before = previous_topics[topic]
        after = current_topics[topic]
        if before.sentiment == after.sentiment:
            continue
        changes.append(
            ManagementSignalChange(
                dimension=f"topic:{topic}",
                previous_value=before.sentiment,
                current_value=after.sentiment,
                direction=_tone_direction(before.sentiment, after.sentiment),
                previous_period=previous_period,
                current_period=current_period,
                evidence_ids=sorted(set(before.evidence_ids + after.evidence_ids)),
            )
        )
    return changes


def _claim_tone(statement: str) -> SentimentLabel:
    value = statement.rsplit(":", maxsplit=1)[-1].strip().rstrip(".")
    if value in {"positive", "neutral", "negative", "mixed", "unclear"}:
        return value  # type: ignore[return-value]
    return "unclear"


def _tone_direction(before: str, after: str) -> ChangeDirection:
    scores = {"negative": -1, "neutral": 0, "positive": 1}
    if before in scores and after in scores:
        if scores[after] > scores[before]:
            return "strengthened"
        if scores[after] < scores[before]:
            return "weakened"
    return "changed"
