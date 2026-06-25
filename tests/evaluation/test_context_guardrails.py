"""Tests for v19 ContextPack guardrails."""

from __future__ import annotations

from src.evaluation.context_guardrails import ContextPackGuardrails
from src.memory.models import ContextEvidenceReference, ContextPack


def _ref(
    memory_id: str = "mem-1",
    *,
    source_type: str = "web",
    status: str = "active",
    claim_type: str = "evidence",
) -> ContextEvidenceReference:
    return ContextEvidenceReference(
        memory_id=memory_id,
        quote="Evidence quote",
        summary="Evidence summary",
        source_type=source_type,  # type: ignore[arg-type]
        claim_type=claim_type,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        context_score=0.8,
    )


def test_context_guardrails_pass_for_clean_pack() -> None:
    """A clean context pack passes."""
    pack = ContextPack(
        run_id="run-1",
        step_name="supplier_discovery",
        task="find suppliers",
        objective="find suppliers",
        selected_evidence=[_ref("mem-1", source_type="web"), _ref("mem-2", source_type="company")],
        selected_memory_ids=["mem-1", "mem-2"],
        token_budget=100,
        estimated_tokens=20,
    )

    result = ContextPackGuardrails().evaluate(pack)

    assert result.status == "pass"
    assert result.findings == []


def test_context_guardrails_fail_on_manifest_mismatch() -> None:
    """Selected evidence and selected ids must match exactly."""
    pack = ContextPack(
        run_id="run-1",
        step_name="supplier_discovery",
        task="find suppliers",
        objective="find suppliers",
        selected_evidence=[_ref("mem-1")],
        selected_memory_ids=["mem-2"],
        token_budget=100,
        estimated_tokens=20,
    )

    result = ContextPackGuardrails().evaluate(pack)

    assert result.status == "fail"
    assert "context_manifest_incomplete" in result.findings


def test_context_guardrails_warn_on_stale_and_hypothesis() -> None:
    """Stale and hypothesis memory trigger review warnings."""
    pack = ContextPack(
        run_id="run-1",
        step_name="supplier_discovery",
        task="find suppliers",
        objective="find suppliers",
        selected_evidence=[
            _ref("mem-1", status="stale"),
            _ref("mem-2", claim_type="hypothesis"),
        ],
        selected_memory_ids=["mem-1", "mem-2"],
        token_budget=100,
        estimated_tokens=20,
    )

    result = ContextPackGuardrails().evaluate(pack)

    assert result.status == "warning"
    assert result.stale_memory_count == 1
    assert result.hypothesis_count == 1


def test_context_guardrails_fail_on_rejected_selected_id() -> None:
    """A memory id cannot be both selected and rejected."""
    pack = ContextPack(
        run_id="run-1",
        step_name="supplier_discovery",
        task="find suppliers",
        objective="find suppliers",
        selected_evidence=[_ref("mem-1")],
        selected_memory_ids=["mem-1"],
        rejected_memory_ids=["mem-1"],
        token_budget=100,
        estimated_tokens=20,
    )

    result = ContextPackGuardrails().evaluate(pack)

    assert result.status == "fail"
    assert result.rejected_memory_count == 1
