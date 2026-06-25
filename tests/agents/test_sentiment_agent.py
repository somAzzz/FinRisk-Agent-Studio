"""Tests for the heuristic ``SentimentAgent``."""

from __future__ import annotations

from datetime import datetime, timezone

from src.agents.sentiment_agent import SentimentAgent
from src.agents.state import AgentState
from src.pipelines.analyze_sentiment import analyze_management_sentiment
from src.schemas.analysis import ManagementSentimentResult
from src.schemas.evidence import Evidence
from src.schemas.transcripts import Transcript, TranscriptTurn


def _evidence(
    eid: str,
    quote: str,
    *,
    source_type: str = "transcript",
    section: str = "prepared_remarks",
    role: str = "ceo",
) -> Evidence:
    return Evidence(
        evidence_id=eid,
        source_type=source_type,
        source_id="src",
        quote=quote,
        section=section,
        retrieved_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
        confidence=0.8,
        metadata={"role": role},
    )


def _transcript(
    ticker: str = "ACME",
    *,
    prepared: str = "We delivered strong growth this quarter.",
    qa: str = "We are cautious on near-term demand given headwinds.",
) -> Transcript:
    return Transcript(
        ticker=ticker,
        year=2026,
        quarter=1,
        provider="test",
        transcript_id="t1",
        title=f"{ticker} Q1 2026",
        turns=[
            TranscriptTurn(
                speaker="CEO",
                role="ceo",
                text=prepared,
                section="prepared_remarks",
                turn_index=0,
            ),
            TranscriptTurn(
                speaker="Analyst",
                role="analyst",
                text="Can you comment on margins?",
                section="qa",
                turn_index=1,
            ),
            TranscriptTurn(
                speaker="CFO",
                role="cfo",
                text=qa,
                section="qa",
                turn_index=2,
            ),
        ],
    )


def test_sentiment_agent_name() -> None:
    assert SentimentAgent().name == "sentiment"


def test_sentiment_agent_returns_management_sentiment_result() -> None:
    state = AgentState(
        goal="x",
        ticker="ACME",
        evidence=[_evidence("e1", "We delivered strong growth and record demand.")],
    )
    out = SentimentAgent().run(state)
    assert isinstance(out, AgentState)
    assert out.claims, "agent should append at least one sentiment claim"
    for claim in out.claims:
        assert claim.claim_type == "sentiment"
        assert 0.0 <= claim.confidence <= 1.0


def test_prepared_vs_qa_are_handled_separately() -> None:
    state = AgentState(
        goal="x",
        ticker="ACME",
        evidence=[
            _evidence(
                "p1",
                "We delivered strong growth and robust momentum.",
                section="prepared_remarks",
            ),
            _evidence(
                "q1",
                "We see headwinds, weakness, and pricing pressure.",
                section="qa",
                role="cfo",
            ),
        ],
    )
    out = SentimentAgent().run(state)
    statements = " ".join(c.statement for c in out.claims)
    assert "Prepared remarks" in statements
    assert "Q&A" in statements


def test_analyst_only_turns_are_excluded() -> None:
    state = AgentState(
        goal="x",
        ticker="ACME",
        evidence=[
            _evidence(
                "a1",
                "I am concerned about the weak outlook.",
                section="qa",
                role="analyst",
            ),
            _evidence(
                "a2",
                "What about the recession?",
                section="qa",
                role="analyst",
            ),
        ],
    )
    out = SentimentAgent().run(state)
    # With no management evidence, the agent must not invent sentiment
    # claims from analyst questions.
    assert all(c.claim_type != "sentiment" for c in out.claims)
    assert any("no management evidence" in n for n in out.notes)


def test_pipeline_returns_management_sentiment_result() -> None:
    transcript = _transcript()
    mda = ["Margins improved on pricing actions despite cost inflation."]
    result = analyze_management_sentiment(
        ticker="ACME",
        transcripts=[transcript],
        mda_sections=mda,
    )
    assert isinstance(result, ManagementSentimentResult)
    assert result.overall_tone in {"positive", "neutral", "negative", "mixed"}
    assert 0.0 <= result.uncertainty <= 1.0
    assert 0.0 <= result.defensiveness <= 1.0
    assert result.guidance_signal in {
        "raised",
        "lowered",
        "maintained",
        "unclear",
    }


def test_mixed_when_prepared_positive_and_qa_negative() -> None:
    state = AgentState(
        goal="x",
        ticker="ACME",
        evidence=[
            _evidence(
                "p1",
                "We delivered strong growth and record demand.",
                section="prepared_remarks",
                role="ceo",
            ),
            _evidence(
                "q1",
                "Headwinds and weakness in our end markets remain challenging.",
                section="qa",
                role="cfo",
            ),
        ],
    )
    out = SentimentAgent().run(state)
    assert any("overall_tone=mixed" in n for n in out.notes)
