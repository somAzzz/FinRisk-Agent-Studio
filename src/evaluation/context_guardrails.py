"""Guardrails for v19 ContextPack objects."""

from __future__ import annotations

from collections import Counter

from src.memory.audit import context_manifest_complete
from src.memory.models import ContextPack, ContextPackEvaluation


class ContextPackGuardrails:
    """Evaluate a ContextPack before it is consumed by a workflow step."""

    name = "context_pack_guardrails"

    def evaluate(self, pack: ContextPack) -> ContextPackEvaluation:
        """Return a compact evaluation for ``pack``."""
        findings: list[str] = []
        token_budget_used = pack.estimated_tokens / pack.token_budget
        if token_budget_used > 1.0:
            findings.append("context_budget_exceeded")

        if not context_manifest_complete(pack):
            findings.append("context_manifest_incomplete")

        selected = pack.selected_evidence
        if not selected:
            findings.append("evidence_minimum_not_met")

        stale_count = sum(1 for item in selected if item.status == "stale")
        hypothesis_count = sum(1 for item in selected if item.claim_type == "hypothesis")
        rejected_count = len(
            set(pack.selected_memory_ids).intersection(pack.rejected_memory_ids)
        )
        if stale_count:
            findings.append("stale_memory_selected")
        if hypothesis_count:
            findings.append("hypothesis_memory_selected")
        if rejected_count:
            findings.append("rejected_memory_selected")

        source_counts = Counter(item.source_type for item in selected)
        source_diversity = (
            len(source_counts) / len(selected)
            if selected
            else 0.0
        )
        if selected and source_diversity < 0.34:
            findings.append("source_diversity_low")

        if rejected_count or "context_manifest_incomplete" in findings:
            status = "fail"
        elif findings:
            status = "warning"
        else:
            status = "pass"

        return ContextPackEvaluation(
            context_pack_id=pack.context_pack_id,
            status=status,
            token_budget_used=token_budget_used,
            source_diversity_score=min(1.0, source_diversity),
            stale_memory_count=stale_count,
            rejected_memory_count=rejected_count,
            hypothesis_count=hypothesis_count,
            findings=findings,
        )


__all__ = ["ContextPackGuardrails"]
