"""v18 Step 4: evidence normaliser.

Reads the fixture evidence and appends it to ``state.evidence``,
deduplicating by ``evidence_id``. The step also validates that
every edge's ``evidence_ids`` reference rows in the merged
evidence table; edges that miss references are flagged with a
warning so the evaluator can downgrade them.
"""

from __future__ import annotations

from src.supply_chain.models import (
    NormalizedSupplyChainEvidence,
    SupplyChainExploreState,
)
from src.supply_chain.steps._base import SupplyChainStep


class SupplyChainEvidenceNormalizerStep(SupplyChainStep):
    """Merge fixture evidence into the state and cross-check edges."""

    name = "evidence_normalizer"

    async def run(
        self, state: SupplyChainExploreState
    ) -> SupplyChainExploreState:
        existing = {ev.evidence_id for ev in state.evidence}
        from src.supply_chain.fixtures import build_default_fixture

        fixture = build_default_fixture()
        for raw in fixture["evidence"]:
            if raw["evidence_id"] in existing:
                continue
            state.evidence.append(NormalizedSupplyChainEvidence.model_validate(raw))
            existing.add(raw["evidence_id"])

        # Cross-check edges against the evidence table.
        evidence_ids = {ev.evidence_id for ev in state.evidence}
        for edge in state.links:
            if edge.relation_type == "hypothesized":
                continue
            missing = [eid for eid in edge.evidence_ids if eid not in evidence_ids]
            for eid in missing:
                state.warnings.append(
                    f"edge {edge.edge_id} cites missing evidence {eid}"
                )
        return state


__all__ = ["SupplyChainEvidenceNormalizerStep"]
