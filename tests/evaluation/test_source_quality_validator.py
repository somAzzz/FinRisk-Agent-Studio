"""Source quality tests."""

from __future__ import annotations

from src.evaluation.source_quality import (
    DEFAULT_CREDIBILITY,
    build_source_quality,
    classify_source_type,
    freshness_from_age,
)
from src.evaluation.validators import SourceQualityValidator
from src.schemas.finrisk import (
    FinRiskRequest,
    FinRiskWorkflowState,
    NormalizedEvidence,
    utcnow,
)


# Map from v15 NormalizedSourceType values to v16 categories for
# the purposes of the validator tests. ``web`` becomes a generic
# news source (low credibility in the v16 default table); ``graph``
# becomes ``unknown`` so the no-primary-source path triggers.
_V15_TYPE_TO_CREDIBILITY = {
    "filing": 1.0,
    "transcript": 0.8,
    "web": 0.6,
    "graph": 0.4,
    "fixture": 0.4,
}


def _state(*, evidence: list[NormalizedEvidence]) -> FinRiskWorkflowState:
    return FinRiskWorkflowState(
        run_id="r",
        request=FinRiskRequest(ticker="AAPL", analysis_goal="goal", demo_mode=True),
        normalized_evidence=evidence,
    )


def _evidence(
    eid: str,
    source_type: str,
    source_url: str | None = None,
) -> NormalizedEvidence:
    return NormalizedEvidence(
        evidence_id=eid,
        source_type=source_type,
        source_name="name",
        source_url=source_url,
        quote="Apple supply chain",
        summary="summary",
        related_risk_ids=[],
        credibility_score=_V15_TYPE_TO_CREDIBILITY[source_type],
        collected_at=utcnow(),
    )


def test_classify_source_type_passes_through_known_types() -> None:
    assert classify_source_type("filing") == "filing"
    assert classify_source_type("weird") == "unknown"


def test_freshness_from_age_uses_piecewise_scale() -> None:
    assert freshness_from_age(0) == 1.0
    assert freshness_from_age(60) == 0.7
    assert freshness_from_age(200) == 0.5
    assert freshness_from_age(800) == 0.3
    assert freshness_from_age(None) == 0.3


def test_build_source_quality_marks_filing_as_primary() -> None:
    sq = build_source_quality(
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/0000320193-24-000123-index.htm",
        source_type="filing",
    )
    assert sq.is_primary_source is True
    assert sq.credibility_score == 1.0


def test_source_quality_validator_flags_no_primary_source() -> None:
    # ``graph`` is mapped to ``unknown`` so no primary source is
    # present in the v16 view of the v15 evidence.
    evidence = [
        _evidence("ne-graph", "graph", "https://random-blog.example.com/a"),
        _evidence("ne-graph2", "graph", "https://random-blog.example.com/b"),
    ]
    findings = SourceQualityValidator().validate("step", None, _state(evidence=evidence))
    assert any("no primary source" in f.message for f in findings)


def test_source_quality_validator_flags_low_credibility() -> None:
    evidence = [
        _evidence("ne-graph", "graph", "https://random-blog.example.com/a"),
        _evidence("ne-filing", "filing", "https://www.sec.gov/x"),
    ]
    findings = SourceQualityValidator().validate("step", None, _state(evidence=evidence))
    assert any("low credibility" in f.message for f in findings)


def test_source_quality_validator_flags_low_diversity() -> None:
    evidence = [
        _evidence("ne-1", "web", "https://reuters.com/a"),
        _evidence("ne-2", "web", "https://reuters.com/b"),
        _evidence("ne-3", "web", "https://reuters.com/c"),
        _evidence("ne-4", "web", "https://reuters.com/d"),
        _evidence("ne-5", "web", "https://reuters.com/e"),
    ]
    findings = SourceQualityValidator().validate("step", None, _state(evidence=evidence))
    assert any("low source diversity" in f.message for f in findings)


# Reference the v16 default table to keep the import in scope.
_ = DEFAULT_CREDIBILITY
