"""ContextPack builder for the v19 evidence-first memory layer."""

from __future__ import annotations

from typing import Any

from src.memory.compressors import clamp_text, estimate_tokens
from src.memory.lifecycle import can_enter_context
from src.memory.models import (
    ContextEvidenceReference,
    ContextPack,
    MemoryItem,
)
from src.memory.policies import (
    DEFAULT_CONTEXT_SELECTION_POLICY,
    ContextSelectionPolicy,
)
from src.memory.rankers import extract_terms, rank_memory_item
from src.memory.store import MemoryStore


class ContextManager:
    """Build bounded, auditable ContextPacks from MemoryStore records."""

    def __init__(
        self,
        store: MemoryStore,
        policy: ContextSelectionPolicy = DEFAULT_CONTEXT_SELECTION_POLICY,
    ):
        self.store = store
        self.policy = policy

    def build(
        self,
        *,
        run_id: str,
        step_name: str,
        task: str,
        subject: dict[str, Any] | None = None,
        intent: str = "general",
        token_budget: int = 4000,
        objective: str | None = None,
        freshness_window_days: int | None = None,
    ) -> ContextPack:
        """Build a ContextPack for a workflow step."""
        subject = subject or {}
        items = self.store.search_candidates(
            subject=subject,
            intent=intent,
            limit=self.policy.max_candidates,
            include_rejected=True,
        )
        subject_terms = extract_terms([subject, task, intent])
        ranked = []
        seen_hashes: set[str] = set()
        by_id: dict[str, MemoryItem] = {}
        rejected_memory_ids: list[str] = []
        warnings: list[str] = []

        for item in items:
            by_id[item.memory_id] = item
            candidate = rank_memory_item(
                item,
                subject_terms=subject_terms,
                seen_hashes=seen_hashes,
                policy=self.policy,
            )
            if not can_enter_context(item):
                rejected_memory_ids.append(item.memory_id)
                continue
            if candidate.duplicate_penalty > 0:
                rejected_memory_ids.append(item.memory_id)
                continue
            ranked.append(candidate)
            seen_hashes.add(item.hash)

        ranked.sort(key=lambda c: c.final_context_score, reverse=True)
        selected: list[ContextEvidenceReference] = []
        selected_ids: list[str] = []
        estimated = 0

        for candidate in ranked:
            if len(selected) >= self.policy.max_selected_items:
                rejected_memory_ids.append(candidate.memory_id)
                continue

            item = by_id[candidate.memory_id]
            quote = clamp_text(item.text, self.policy.max_quote_chars) or ""
            summary = clamp_text(item.summary, self.policy.max_summary_chars)
            item_tokens = estimate_tokens(
                " ".join([quote, summary or ""]),
                chars_per_token=self.policy.chars_per_token,
            )
            if estimated + item_tokens > token_budget:
                rejected_memory_ids.append(candidate.memory_id)
                continue

            if item.status == "stale":
                warnings.append(f"stale memory selected: {item.memory_id}")
            if item.claim_type == "hypothesis":
                warnings.append(f"hypothesis memory selected: {item.memory_id}")

            selected.append(
                ContextEvidenceReference(
                    memory_id=item.memory_id,
                    quote=quote,
                    summary=summary,
                    source_type=item.source_type,
                    source_url=item.source_url,
                    source_title=item.source_title,
                    claim_type=item.claim_type,
                    status=item.status,
                    context_score=candidate.final_context_score,
                )
            )
            selected_ids.append(item.memory_id)
            estimated += item_tokens

        negative_memory = [
            item.text
            for item in items
            if item.status == "rejected" and item.memory_type in {"claim", "graph_edge"}
        ]

        return ContextPack(
            run_id=run_id,
            step_name=step_name,
            task=task,
            objective=objective or task,
            selected_evidence=selected,
            prior_findings=[
                ref.summary
                for ref in selected
                if ref.summary and ref.claim_type in {"inference", "policy"}
            ],
            negative_memory=negative_memory,
            token_budget=token_budget,
            estimated_tokens=estimated,
            freshness_window_days=freshness_window_days,
            selection_policy_version=self.policy.version,
            selected_memory_ids=selected_ids,
            rejected_memory_ids=sorted(set(rejected_memory_ids) - set(selected_ids)),
            warnings=warnings,
        )


__all__ = ["ContextManager"]
