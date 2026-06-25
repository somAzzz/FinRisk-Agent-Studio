"""Extraction-level evaluation: entity, relation, claim coverage.

The metric set follows the Step 11 implementation plan:

- ``matched_entities`` / ``expected_entities`` — exact-id overlap of
  :class:`Entity` records.
- ``matched_relations`` / ``expected_relations`` — exact-id overlap of
  :class:`Relation` records.
- ``unsupported_claims`` — count of predicted claims with no evidence.
- ``evidence_coverage`` — fraction of expected entities/relations that
  appear in the predicted set.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.claims import Claim
from src.schemas.entities import Entity
from src.schemas.relations import Relation


class ExtractionEvalResult(BaseModel):
    """Aggregate metrics for an extraction run against a golden fixture."""

    model_config = ConfigDict(extra="forbid")

    expected_entities: int
    matched_entities: int
    expected_relations: int
    matched_relations: int
    unsupported_claims: int
    evidence_coverage: float = Field(ge=0.0, le=1.0)
    total_predicted_entities: int = 0
    total_predicted_relations: int = 0
    total_predicted_claims: int = 0


def _entity_ids(items: list[Entity]) -> set[str]:
    return {e.entity_id for e in items}


def _relation_ids(items: list[Relation]) -> set[str]:
    return {r.relation_id for r in items}


def evaluate_extraction(
    predicted_entities: list[Entity],
    predicted_relations: list[Relation],
    predicted_claims: list[Claim],
    expected_entities: list[Entity],
    expected_relations: list[Relation],
    expected_claims: list[Claim],
) -> ExtractionEvalResult:
    """Compute extraction-level metrics between predicted and expected sets.

    The function is deliberately tolerant of inputs from earlier pipeline
    versions: the ``expected_claims`` argument is accepted for API symmetry
    but is not currently included in the metric calculation, since the
    plan does not specify an expected-vs-predicted claim overlap metric.
    """
    del expected_claims  # reserved for future use; see docstring

    expected_e_ids = _entity_ids(expected_entities)
    expected_r_ids = _relation_ids(expected_relations)
    predicted_e_ids = _entity_ids(predicted_entities)
    predicted_r_ids = _relation_ids(predicted_relations)

    matched_entities = len(expected_e_ids & predicted_e_ids)
    matched_relations = len(expected_r_ids & predicted_r_ids)
    unsupported_claims = sum(1 for c in predicted_claims if not c.evidence)

    total_expected = max(1, len(expected_e_ids) + len(expected_r_ids))
    covered = (matched_entities + matched_relations) / total_expected

    return ExtractionEvalResult(
        expected_entities=len(expected_e_ids),
        matched_entities=matched_entities,
        expected_relations=len(expected_r_ids),
        matched_relations=matched_relations,
        unsupported_claims=unsupported_claims,
        evidence_coverage=round(covered, 4),
        total_predicted_entities=len(predicted_e_ids),
        total_predicted_relations=len(predicted_r_ids),
        total_predicted_claims=len(predicted_claims),
    )


__all__ = ["ExtractionEvalResult", "evaluate_extraction"]
