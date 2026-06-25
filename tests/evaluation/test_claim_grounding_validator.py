"""Claim grounding tests."""

from __future__ import annotations

from src.evaluation.claim_grounding import (
    Claim,
    grounding_label,
    lexical_overlap,
)
from src.evaluation.models import GuardrailSeverity
from src.evaluation.validators import ClaimGroundingValidator
from src.schemas.finrisk import (
    FinRiskRequest,
    FinRiskWorkflowState,
    NormalizedEvidence,
    utcnow,
)


def _state(*, evidence: list[NormalizedEvidence]) -> FinRiskWorkflowState:
    return FinRiskWorkflowState(
        run_id="r",
        request=FinRiskRequest(ticker="AAPL", analysis_goal="goal", demo_mode=True),
        normalized_evidence=evidence,
    )


def _evidence(eid: str, quote: str) -> NormalizedEvidence:
    return NormalizedEvidence(
        evidence_id=eid,
        source_type="filing",
        source_name="10-K",
        source_url=None,
        quote=quote,
        summary=quote,
        related_risk_ids=[],
        credibility_score=0.9,
        collected_at=utcnow(),
    )


def test_lexical_overlap_grounded_for_high_overlap() -> None:
    assert lexical_overlap("Apple faces supply chain risks in Asia", "Apple relies on supply chain partners in Asia") > 0.25
    assert grounding_label(0.6) == "grounded"


def test_lexical_overlap_unsupported_for_low_overlap() -> None:
    assert grounding_label(0.05) == "unsupported"


def test_claim_grounding_validator_blocks_claim_without_evidence() -> None:
    claim = Claim(
        claim_id="c-1", text="something", claim_type="inference",
        supporting_evidence_ids=[], confidence=0.5,
    )
    findings = ClaimGroundingValidator().validate("step", [claim], _state(evidence=[]))
    assert findings and findings[0].severity == GuardrailSeverity.BLOCKER


def test_claim_grounding_validator_blocks_missing_evidence_id() -> None:
    claim = Claim(
        claim_id="c-1", text="Apple risk", claim_type="evidence",
        supporting_evidence_ids=["ne-does-not-exist"], confidence=0.5,
    )
    findings = ClaimGroundingValidator().validate(
        "step", [claim], _state(evidence=[_evidence("ne-real", "Apple")])
    )
    assert findings and findings[0].severity == GuardrailSeverity.BLOCKER


def test_claim_grounding_validator_passes_for_grounded_claim() -> None:
    claim = Claim(
        claim_id="c-1", text="Apple faces Asia supply chain risk",
        claim_type="evidence",
        supporting_evidence_ids=["ne-1"], confidence=0.8,
    )
    ev = _evidence(
        "ne-1", "Apple supply chain partners in Asia face tariff risk"
    )
    findings = ClaimGroundingValidator().validate(
        "step", [claim], _state(evidence=[ev])
    )
    assert findings == []


def test_claim_grounding_validator_warns_for_partial_overlap() -> None:
    claim = Claim(
        claim_id="c-1",
        text="Apple supply chain Asia tariff regulatory macroeconomic pressure",
        claim_type="inference",
        supporting_evidence_ids=["ne-1"],
        confidence=0.5,
    )
    ev = _evidence("ne-1", "Apple mentions outsourcing partners")
    findings = ClaimGroundingValidator().validate(
        "step", [claim], _state(evidence=[ev])
    )
    # Overlap is partial; we expect at least a warning or needs_review.
    assert findings
    assert any(f.severity == GuardrailSeverity.WARNING for f in findings)
