"""Report agent: assemble a Markdown research brief from hypotheses, claims,
and evidence.

The agent performs no LLM calls. It deterministically assembles a Markdown
report using the sections required by the implementation plan, and
enforces the rule that every claim asserted in the report must cite at
least one evidence record.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.schemas.claims import Claim
from src.schemas.evidence import Evidence
from src.schemas.hypotheses import InvestmentHypothesis

# Section order required by the implementation plan. Any report generated
# by this module contains every heading in this order.
REPORT_SECTIONS: tuple[str, ...] = (
    "Executive Summary",
    "Key Evidence",
    "Supply Chain Map",
    "Management Sentiment",
    "Policy and Geopolitical Exposure",
    "Opportunity Hypotheses",
    "Risks and Counter-Evidence",
    "Watchlist Triggers",
    "Sources",
)

DISCLAIMER = (
    "Disclaimer: This report is for research only and is not investment "
    "advice."
)


class ReportAgent:
    """Assemble a Markdown company research brief."""

    name = "report"

    def generate(
        self,
        ticker: str,
        hypotheses: list[InvestmentHypothesis],
        claims: list[Claim],
        evidence: list[Evidence],
    ) -> str:
        """Return a Markdown report string for ``ticker``.

        The report walks the supplied hypotheses, claims, and evidence and
        produces the nine canonical sections plus a disclaimer. Every
        asserted claim is paired with at least one evidence record and
        cited using bracketed markers (e.g. ``[1]``). Claims without
        evidence are not asserted in the body; they are still listed in
        the Sources section so their absence is visible.
        """
        evidence = self._dedupe_evidence(evidence)
        evidence_index, evidence_refs = self._index_evidence(evidence)
        claim_index, claim_refs = self._index_claims(claims, evidence_index)

        parts: list[str] = []
        parts.append(self._heading("Company Research Brief", ticker, level=1))

        parts.append(self._section("Executive Summary", self._executive_summary(
            ticker, hypotheses, claims, evidence
        )))
        parts.append(self._section("Key Evidence", self._key_evidence(
            evidence, evidence_refs
        )))
        parts.append(self._section("Supply Chain Map", self._supply_chain_map(
            claims, evidence_refs
        )))
        parts.append(self._section(
            "Management Sentiment", self._management_sentiment(
                claims, evidence_refs
            )
        ))
        parts.append(self._section(
            "Policy and Geopolitical Exposure",
            self._policy_and_geopolitical(claims, evidence_refs),
        ))
        parts.append(self._section(
            "Opportunity Hypotheses",
            self._opportunity_hypotheses(hypotheses, evidence_refs),
        ))
        parts.append(self._section(
            "Risks and Counter-Evidence",
            self._risks_and_counter_evidence(
                hypotheses, claims, evidence_refs
            ),
        ))
        parts.append(self._section(
            "Watchlist Triggers", self._watchlist_triggers(hypotheses)
        ))
        parts.append(self._section("Sources", self._sources(
            claim_index, claim_refs, evidence_index, evidence_refs
        )))

        parts.append("")
        parts.append(DISCLAIMER)
        return "\n\n".join(parts) + "\n"

    # -- section builders -------------------------------------------------
    def _executive_summary(
        self,
        ticker: str,
        hypotheses: list[InvestmentHypothesis],
        claims: list[Claim],
        evidence: list[Evidence],
    ) -> str:
        lines: list[str] = []
        lines.append(
            f"This research brief summarizes the available evidence and "
            f"research hypotheses for {ticker}. It is not investment advice."
        )
        lines.append("")
        lines.append(
            f"- Hypotheses generated: {len(hypotheses)}"
        )
        lines.append(
            f"- Supporting claims: {sum(1 for c in claims if c.evidence)} "
            f"of {len(claims)}"
        )
        lines.append(
            f"- Evidence records reviewed: {len(evidence)}"
        )
        return "\n".join(lines)

    def _key_evidence(
        self,
        evidence: list[Evidence],
        evidence_refs: dict[str, int],
    ) -> str:
        if not evidence:
            return "No evidence has been collected yet."
        lines: list[str] = []
        for ev in evidence:
            ref = evidence_refs.get(ev.evidence_id, -1)
            lines.append(
                f"- {self._cite([ref])} {ev.source_type}: {ev.quote[:200]}"
            )
        return "\n".join(lines)

    def _supply_chain_map(
        self,
        claims: list[Claim],
        evidence_refs: dict[str, int],
    ) -> str:
        supply_claims = [c for c in claims if c.claim_type == "supply_chain"]
        if not supply_claims:
            return "No supply chain claims were identified."
        lines: list[str] = []
        for claim in supply_claims:
            refs = self._refs_for_claim(claim, evidence_refs)
            if not refs:
                continue
            lines.append(
                f"- {self._cite(refs)} {claim.statement}"
            )
        if not lines:
            return "No supply chain claims were identified."
        return "\n".join(lines)

    def _management_sentiment(
        self,
        claims: list[Claim],
        evidence_refs: dict[str, int],
    ) -> str:
        sentiment_claims = [c for c in claims if c.claim_type == "sentiment"]
        if not sentiment_claims:
            return "No management sentiment claims were identified."
        lines: list[str] = []
        for claim in sentiment_claims:
            refs = self._refs_for_claim(claim, evidence_refs)
            if not refs:
                continue
            lines.append(
                f"- {self._cite(refs)} {claim.statement}"
            )
        if not lines:
            return "No management sentiment claims were identified."
        return "\n".join(lines)

    def _policy_and_geopolitical(
        self,
        claims: list[Claim],
        evidence_refs: dict[str, int],
    ) -> str:
        relevant = [
            c
            for c in claims
            if c.claim_type in {"policy_exposure", "geopolitical_exposure"}
        ]
        if not relevant:
            return "No policy or geopolitical exposure claims were identified."
        lines: list[str] = []
        for claim in relevant:
            refs = self._refs_for_claim(claim, evidence_refs)
            if not refs:
                continue
            lines.append(
                f"- {self._claim_label(claim.claim_type)}: "
                f"{self._cite(refs)} {claim.statement}"
            )
        if not lines:
            return "No policy or geopolitical exposure claims were identified."
        return "\n".join(lines)

    def _opportunity_hypotheses(
        self,
        hypotheses: list[InvestmentHypothesis],
        evidence_refs: dict[str, int],
    ) -> str:
        if not hypotheses:
            return "No research hypotheses were generated."
        lines: list[str] = []
        for hyp in hypotheses:
            refs = [evidence_refs[ev.evidence_id] for ev in hyp.evidence
                    if ev.evidence_id in evidence_refs]
            if not refs:
                # Hypotheses must always carry evidence per the schema; if
                # the indexer missed them, skip to honour the
                # ``evidence-backed assertions only`` invariant.
                continue
            lines.append(
                f"### {hyp.title} ({hyp.hypothesis_type})"
            )
            lines.append("")
            lines.append(
                f"{hyp.statement} {self._cite(refs)}"
            )
        if not lines:
            return "No research hypotheses were generated."
        return "\n".join(lines)

    def _risks_and_counter_evidence(
        self,
        hypotheses: list[InvestmentHypothesis],
        claims: list[Claim],
        evidence_refs: dict[str, int],
    ) -> str:
        lines: list[str] = []
        risk_claims = [c for c in claims if c.claim_type == "risk"]
        for claim in risk_claims:
            refs = self._refs_for_claim(claim, evidence_refs)
            if not refs:
                continue
            lines.append(
                f"- {self._cite(refs)} {claim.statement}"
            )
        for hyp in hypotheses:
            for ev in hyp.counter_evidence:
                ref = evidence_refs.get(ev.evidence_id)
                if ref is None:
                    continue
                lines.append(
                    f"- Counter-evidence for {hyp.title}: {self._cite([ref])} "
                    f"{ev.quote[:200]}"
                )
        if not lines:
            return "No risks or counter-evidence were identified."
        return "\n".join(lines)

    def _watchlist_triggers(
        self, hypotheses: list[InvestmentHypothesis]
    ) -> str:
        seen: set[str] = set()
        lines: list[str] = []
        for hyp in hypotheses:
            for trigger in hyp.watchlist_triggers:
                if trigger in seen:
                    continue
                seen.add(trigger)
                lines.append(f"- {trigger}")
        if not lines:
            return "No watchlist triggers were generated."
        return "\n".join(lines)

    def _sources(
        self,
        claim_index: dict[str, Claim],
        claim_refs: dict[str, int],
        evidence_index: dict[str, Evidence],
        evidence_refs: dict[str, int],
    ) -> str:
        lines: list[str] = []
        # Evidence is the primary citation surface. We sort by the
        # assigned reference number so output matches the in-body markers.
        sorted_evidence = sorted(
            evidence_index.values(),
            key=lambda e: evidence_refs.get(e.evidence_id, 0),
        )
        for ev in sorted_evidence:
            ref = evidence_refs.get(ev.evidence_id, -1)
            label = ev.title or ev.source_id
            url = ev.url or ""
            lines.append(
                f"- [{ref}] {ev.source_type}: {label} {url}".rstrip()
            )
        unsupported = [
            c for c in claim_index.values() if not c.evidence
        ]
        if unsupported:
            lines.append("")
            lines.append(
                "Claims without supporting evidence (not asserted in the "
                "report body):"
            )
            for c in unsupported:
                ref = claim_refs.get(c.claim_id, -1)
                lines.append(
                    f"- [{ref}] {c.claim_type}: {c.statement}"
                )
        if not lines:
            return "No sources are available."
        return "\n".join(lines)

    # -- helpers ----------------------------------------------------------
    def _heading(self, prefix: str, ticker: str, level: int) -> str:
        hashes = "#" * level
        return f"{hashes} {prefix}: {ticker}"

    def _section(self, title: str, body: str) -> str:
        return f"## {title}\n\n{body}"

    def _claim_label(self, claim_type: str) -> str:
        return claim_type.replace("_", " ").title()

    def _cite(self, refs: Iterable[int]) -> str:
        ordered = sorted({r for r in refs if r > 0})
        if not ordered:
            return ""
        return "[" + ", ".join(str(r) for r in ordered) + "]"

    def _refs_for_claim(
        self,
        claim: Claim,
        evidence_refs: dict[str, int],
    ) -> list[int]:
        refs: list[int] = []
        for ev in claim.evidence:
            ref = evidence_refs.get(ev.evidence_id)
            if ref is not None:
                refs.append(ref)
        return sorted(set(refs))

    def _dedupe_evidence(
        self, evidence: list[Evidence]
    ) -> list[Evidence]:
        """Drop duplicate evidence records by ``evidence_id``.

        The offline MVP and live fetchers may both attach evidence for the
        same source (e.g. a transcript turn cited from web and filing).
        Without dedupe, ``Key Evidence`` would list the same record twice
        with different bracketed numbers and the rest of the report would
        no longer align with the evidence index.
        """
        seen: set[str] = set()
        deduped: list[Evidence] = []
        for ev in evidence:
            if ev.evidence_id in seen:
                continue
            seen.add(ev.evidence_id)
            deduped.append(ev)
        return deduped

    def _index_evidence(
        self, evidence: list[Evidence]
    ) -> tuple[dict[str, Evidence], dict[str, int]]:
        index: dict[str, Evidence] = {}
        refs: dict[str, int] = {}
        for idx, ev in enumerate(evidence, start=1):
            if ev.evidence_id in index:
                continue
            index[ev.evidence_id] = ev
            refs[ev.evidence_id] = idx
        return index, refs

    def _index_claims(
        self,
        claims: list[Claim],
        evidence_index: dict[str, Evidence],
    ) -> tuple[dict[str, Claim], dict[str, int]]:
        claim_index: dict[str, Claim] = {}
        claim_refs: dict[str, int] = {}
        # Use the count of indexed evidence as the starting offset so
        # claim reference numbers do not collide with evidence numbers.
        offset = len(evidence_index)
        for i, claim in enumerate(claims, start=1):
            if claim.claim_id in claim_index:
                continue
            claim_index[claim.claim_id] = claim
            claim_refs[claim.claim_id] = offset + i
        return claim_index, claim_refs


def is_report_agent(obj: object) -> bool:
    """Runtime helper for ``isinstance``-free protocol checks."""
    return getattr(obj, "name", None) == "report"
