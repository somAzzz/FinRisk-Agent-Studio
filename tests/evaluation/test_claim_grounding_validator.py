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
    ExtractedRisk,
    FinRiskRequest,
    FinRiskWorkflowState,
    NormalizedEvidence,
    utcnow,
)


def _risk(risk_id: str = "r-1") -> ExtractedRisk:
    return ExtractedRisk(
        risk_id=risk_id,
        risk_type="supply_chain",
        risk_factor="Apple faces Asia supply chain risk",
        severity=4,
        evidence_quote="Apple supply chain partners in Asia face tariff risk",
        source="sec_filing:test",
        filing_section="section_1a",
        confidence=0.8,
    )


def _state(
    *,
    evidence: list[NormalizedEvidence],
    risks: list[ExtractedRisk] | None = None,
) -> FinRiskWorkflowState:
    return FinRiskWorkflowState(
        run_id="r",
        request=FinRiskRequest(ticker="AAPL", analysis_goal="goal", demo_mode=True),
        normalized_evidence=evidence,
        filing_risks=risks or [],
    )


def _evidence(
    eid: str, quote: str, related_risk_ids: list[str] | None = None
) -> NormalizedEvidence:
    return NormalizedEvidence(
        evidence_id=eid,
        source_type="filing",
        source_name="10-K",
        source_url=None,
        quote=quote,
        summary=quote,
        related_risk_ids=related_risk_ids or [],
        credibility_score=0.9,
        collected_at=utcnow(),
    )


def test_lexical_overlap_grounded_for_high_overlap() -> None:
    assert (
        lexical_overlap(
            "Apple faces supply chain risks in Asia",
            "Apple relies on supply chain partners in Asia",
        )
        > 0.25
    )
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
        related_risk_ids=["r-1"],
        supporting_evidence_ids=["ne-1"], confidence=0.8,
    )
    ev = _evidence(
        "ne-1",
        "Apple supply chain partners in Asia face tariff risk",
        related_risk_ids=["r-1"],
    )
    findings = ClaimGroundingValidator().validate(
        "step", [claim], _state(evidence=[ev], risks=[_risk()])
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


def test_claim_grounding_validator_blocks_claim_without_risk_lineage() -> None:
    claim = Claim(
        claim_id="c-1",
        text="Apple faces Asia supply chain risk",
        claim_type="evidence",
        supporting_evidence_ids=["ne-1"],
        confidence=0.8,
    )
    ev = _evidence(
        "ne-1",
        "Apple supply chain partners in Asia face tariff risk",
        related_risk_ids=["r-1"],
    )
    findings = ClaimGroundingValidator().validate(
        "step", [claim], _state(evidence=[ev], risks=[_risk()])
    )
    assert findings
    assert any("no related risk ids" in f.message for f in findings)
    assert any(f.severity == GuardrailSeverity.BLOCKER for f in findings)


def test_claim_grounding_validator_blocks_unknown_related_risk() -> None:
    claim = Claim(
        claim_id="c-1",
        text="Apple faces Asia supply chain risk",
        claim_type="evidence",
        related_risk_ids=["r-missing"],
        supporting_evidence_ids=["ne-1"],
        confidence=0.8,
    )
    ev = _evidence(
        "ne-1",
        "Apple supply chain partners in Asia face tariff risk",
        related_risk_ids=["r-1"],
    )
    findings = ClaimGroundingValidator().validate(
        "step", [claim], _state(evidence=[ev], risks=[_risk()])
    )
    assert findings
    assert any("cites missing risk" in f.message for f in findings)
    assert any(f.severity == GuardrailSeverity.BLOCKER for f in findings)


def test_claim_grounding_validator_warns_when_evidence_does_not_cover_risk() -> None:
    claim = Claim(
        claim_id="c-1",
        text="Apple faces Asia supply chain risk",
        claim_type="evidence",
        related_risk_ids=["r-1"],
        supporting_evidence_ids=["ne-1"],
        confidence=0.8,
    )
    ev = _evidence(
        "ne-1",
        "Apple supply chain partners in Asia face tariff risk",
        related_risk_ids=["r-other"],
    )
    findings = ClaimGroundingValidator().validate(
        "step", [claim], _state(evidence=[ev], risks=[_risk()])
    )
    assert findings
    assert any("not fully backed" in f.message for f in findings)
    assert any(f.severity == GuardrailSeverity.WARNING for f in findings)
