"""Opportunity agent: rule-based generator of investment research hypotheses.

The agent inspects claim types, entities, and evidence and emits 3-5
``InvestmentHypothesis`` records following the patterns described in the
implementation plan. It performs no LLM calls; all reasoning is
deterministic pattern matching over the supplied state.
"""

from __future__ import annotations

import json

from src.agents.base import Agent
from src.agents.state import AgentState
from src.schemas.claims import Claim
from src.schemas.entities import Entity
from src.schemas.evidence import Evidence
from src.schemas.hypotheses import HypothesisType, InvestmentHypothesis

# Hard upper bound on the number of hypotheses the agent will emit.
_MAX_HYPOTHESES = 5
# Lower bound required by the plan.
_MIN_HYPOTHESES = 3


class OpportunityAgent:
    """Generate research hypotheses from claims, entities, and evidence."""

    name = "opportunity"

    def run(self, state: AgentState) -> AgentState:
        """Return a new state with hypotheses recorded in ``state.notes``.

        The :class:`AgentState` model uses ``extra="forbid"`` and has no
        dedicated ``metadata`` field, so the agent cannot attach a new
        attribute directly. To avoid mutating ``state.claims`` (which
        downstream agents consume), the agent stores a serialised summary
        of the generated hypotheses on ``state.notes`` under a single
        ``"opportunity:hypotheses"`` marker, while leaving the caller's
        state instance unchanged.
        """
        hypotheses = self.generate(
            claims=state.claims,
            evidence=state.evidence,
            entities=state.entities,
        )
        serialised = [h.model_dump(mode="json") for h in hypotheses]
        new_notes: list[str] = list(state.notes)
        new_notes.append(f"opportunity:hypotheses_count={len(hypotheses)}")
        new_notes.append("opportunity:hypotheses=" + json.dumps(serialised))
        return state.model_copy(update={"notes": new_notes})

    def generate(
        self,
        claims: list[Claim],
        evidence: list[Evidence],
        entities: list[Entity],
    ) -> list[InvestmentHypothesis]:
        """Generate 3-5 hypotheses from the supplied inputs.

        The generator walks the claim list looking for matches against the
        five rule types defined in the implementation plan. Each rule
        produces at most one hypothesis; if fewer than ``_MIN_HYPOTHESES``
        rules fire, fallback hypotheses are emitted so the contract is
        always honoured.
        """
        hypotheses: list[InvestmentHypothesis] = []
        used_claim_ids: set[str] = set()

        supply_chain = self._first_claim(claims, "supply_chain", used_claim_ids)
        if supply_chain is not None:
            hypotheses.append(
                self._build_supply_chain_hypothesis(supply_chain, evidence)
            )

        policy = self._first_claim(claims, "policy_exposure", used_claim_ids)
        if policy is not None:
            hypotheses.append(
                self._build_policy_hypothesis(policy, evidence)
            )

        sentiment = self._first_claim(claims, "sentiment", used_claim_ids)
        risk = self._first_claim(claims, "risk", used_claim_ids)
        if sentiment is not None and risk is not None:
            hypotheses.append(
                self._build_sentiment_turnaround(sentiment, risk, evidence)
            )

        geopolitical = self._first_claim(
            claims, "geopolitical_exposure", used_claim_ids
        )
        if geopolitical is not None:
            hypotheses.append(
                self._build_geopolitical_hypothesis(geopolitical, evidence)
            )

        if risk is not None:
            hypotheses.append(
                self._build_risk_mispricing(risk, claims, evidence)
            )

        # Ensure at least the minimum number of hypotheses by padding with
        # generic opportunity entries backed by the remaining evidence.
        for claim in claims:
            if len(hypotheses) >= _MAX_HYPOTHESES:
                break
            if claim.claim_id in used_claim_ids:
                continue
            if not claim.evidence:
                continue
            hypotheses.append(
                self._build_demand_acceleration(claim, entities)
            )
            used_claim_ids.add(claim.claim_id)

        # If the rules produced nothing, fall back to a single demand
        # hypothesis using any claim with evidence.
        if not hypotheses:
            for claim in claims:
                if claim.evidence:
                    hypotheses.append(
                        self._build_demand_acceleration(claim, entities)
                    )
                    break

        # Always meet the lower bound by re-using available evidence.
        if len(hypotheses) < _MIN_HYPOTHESES and evidence:
            hypotheses.append(
                self._build_fallback_hypothesis(evidence, entities)
            )

        # Cap at the upper bound.
        return hypotheses[:_MAX_HYPOTHESES]

    # -- rule builders ----------------------------------------------------
    def _build_supply_chain_hypothesis(
        self, claim: Claim, evidence: list[Evidence]
    ) -> InvestmentHypothesis:
        supporting_evidence = self._gather_evidence(claim, evidence)
        return InvestmentHypothesis(
            hypothesis_id=self._make_id("hypo-sc", claim.claim_id),
            title="Supply chain opportunity worth tracking",
            hypothesis_type="supply_chain_opportunity",
            statement=(
                "The company may benefit from upstream supply chain dynamics "
                "described in the supporting claim. This is a research "
                "hypothesis, not an investment recommendation."
            ),
            companies=claim.entities,
            supporting_claims=[claim],
            evidence=supporting_evidence,
            counter_evidence=[],
            confidence=self._confidence(supporting_evidence, claim.confidence),
            watchlist_triggers=[
                "New order or capacity announcement",
                "Supplier pricing update",
            ],
            risks_to_monitor=[
                "Demand softening in downstream segments",
                "Capacity bottlenecks from alternative suppliers",
            ],
        )

    def _build_policy_hypothesis(
        self, claim: Claim, evidence: list[Evidence]
    ) -> InvestmentHypothesis:
        supporting_evidence = self._gather_evidence(claim, evidence)
        return InvestmentHypothesis(
            hypothesis_id=self._make_id("hypo-pol", claim.claim_id),
            title="Policy beneficiary candidate",
            hypothesis_type="policy_beneficiary",
            statement=(
                "Policy exposure flagged in filings may make the company a "
                "potential beneficiary if the policy is implemented as "
                "described."
            ),
            companies=claim.entities,
            supporting_claims=[claim],
            evidence=supporting_evidence,
            counter_evidence=[],
            confidence=self._confidence(supporting_evidence, claim.confidence),
            watchlist_triggers=[
                "Policy implementation guidance",
                "Regulatory update",
            ],
            risks_to_monitor=[
                "Policy reversal or scope reduction",
                "Compliance cost overruns",
            ],
        )

    def _build_sentiment_turnaround(
        self,
        sentiment_claim: Claim,
        risk_claim: Claim,
        evidence: list[Evidence],
    ) -> InvestmentHypothesis:
        supporting_evidence = self._gather_evidence(
            sentiment_claim, evidence, include_risk=True
        )
        return InvestmentHypothesis(
            hypothesis_id=self._make_id("hypo-sent", sentiment_claim.claim_id),
            title="Sentiment turnaround hypothesis",
            hypothesis_type="sentiment_turnaround",
            statement=(
                "Improving management sentiment alongside stable risk "
                "disclosures suggests a possible sentiment turnaround worth "
                "researching further."
            ),
            companies=sentiment_claim.entities,
            supporting_claims=[sentiment_claim],
            evidence=supporting_evidence,
            counter_evidence=risk_claim.evidence[:1],
            confidence=self._confidence(supporting_evidence, sentiment_claim.confidence),
            watchlist_triggers=[
                "Next earnings transcript tone change",
                "Guidance revision",
            ],
            risks_to_monitor=[
                "Risk factors deteriorate",
                "Demand environment weakens",
            ],
        )

    def _build_geopolitical_hypothesis(
        self, claim: Claim, evidence: list[Evidence]
    ) -> InvestmentHypothesis:
        supporting_evidence = self._gather_evidence(claim, evidence)
        return InvestmentHypothesis(
            hypothesis_id=self._make_id("hypo-geo", claim.claim_id),
            title="Geopolitical substitution candidate",
            hypothesis_type="geopolitical_substitution",
            statement=(
                "Rising regional risk in one geography may shift demand "
                "toward this company if it can serve as a substitute "
                "supplier or region."
            ),
            companies=claim.entities,
            supporting_claims=[claim],
            evidence=supporting_evidence,
            counter_evidence=[],
            confidence=self._confidence(supporting_evidence, claim.confidence),
            watchlist_triggers=[
                "Reshoring announcement",
                "Localization initiative",
            ],
            risks_to_monitor=[
                "Escalating geopolitical tension",
                "Substitute capacity ramp delays",
            ],
        )

    def _build_risk_mispricing(
        self,
        risk_claim: Claim,
        claims: list[Claim],
        evidence: list[Evidence],
    ) -> InvestmentHypothesis:
        supporting_evidence = self._gather_evidence(risk_claim, evidence)
        # Counter-evidence is sourced from conflicting sentiment or
        # opportunity claims whose evidence points the other way.
        counter: list[Evidence] = []
        for other in claims:
            if other.claim_id == risk_claim.claim_id:
                continue
            if other.claim_type in {"opportunity", "sentiment"}:
                counter.extend(other.evidence[:1])
            if len(counter) >= 2:
                break
        return InvestmentHypothesis(
            hypothesis_id=self._make_id("hypo-risk", risk_claim.claim_id),
            title="Risk mispricing hypothesis",
            hypothesis_type="risk_mispricing",
            statement=(
                "The company continues to disclose risk while supporting "
                "evidence suggests the underlying situation may be "
                "improving, which could indicate mispricing worth "
                "investigating."
            ),
            companies=risk_claim.entities,
            supporting_claims=[risk_claim],
            evidence=supporting_evidence,
            counter_evidence=counter,
            confidence=self._confidence(supporting_evidence, risk_claim.confidence),
            watchlist_triggers=[
                "Risk disclosure language changes",
                "Mitigation milestone reached",
            ],
            risks_to_monitor=[
                "Risk re-escalation",
                "New related disclosure",
            ],
        )

    def _build_demand_acceleration(
        self, claim: Claim, entities: list[Entity]
    ) -> InvestmentHypothesis:
        supporting_evidence = self._gather_evidence(claim, claim.evidence)
        return InvestmentHypothesis(
            hypothesis_id=self._make_id("hypo-demand", claim.claim_id),
            title="Demand acceleration hypothesis",
            hypothesis_type="demand_acceleration",
            statement=(
                "The supporting claim may signal accelerating demand worth "
                "tracking as a research hypothesis."
            ),
            companies=claim.entities or entities,
            supporting_claims=[claim],
            evidence=supporting_evidence,
            counter_evidence=[],
            confidence=self._confidence(supporting_evidence, claim.confidence),
            watchlist_triggers=[
                "Order growth metric update",
                "Customer concentration disclosure",
            ],
            risks_to_monitor=[
                "Demand normalization",
                "Pricing pressure",
            ],
        )

    def _build_fallback_hypothesis(
        self, evidence: list[Evidence], entities: list[Entity]
    ) -> InvestmentHypothesis:
        return InvestmentHypothesis(
            hypothesis_id="hypo-fallback-0001",
            title="General research hypothesis",
            hypothesis_type="demand_acceleration",
            statement=(
                "Available evidence is sparse. The hypothesis below is a "
                "placeholder research artifact and should be refined when "
                "more evidence is collected."
            ),
            companies=entities,
            supporting_claims=[],
            evidence=evidence[:2],
            counter_evidence=[],
            confidence=0.2,
            watchlist_triggers=["Collect additional evidence"],
            risks_to_monitor=["Insufficient evidence"],
        )

    # -- helpers ----------------------------------------------------------
    def _first_claim(
        self,
        claims: list[Claim],
        claim_type: str,
        used: set[str],
    ) -> Claim | None:
        for claim in claims:
            if claim.claim_id in used:
                continue
            if claim.claim_type == claim_type:
                used.add(claim.claim_id)
                return claim
        return None

    def _gather_evidence(
        self,
        claim: Claim,
        evidence_pool: list[Evidence],
        include_risk: bool = False,
    ) -> list[Evidence]:
        collected: list[Evidence] = list(claim.evidence)
        if not collected:
            # Fall back to any evidence already in the pool that mentions
            # the claim id, otherwise use the first two pieces.
            for ev in evidence_pool:
                meta = ev.metadata or {}
                if meta.get("claim_id") == claim.claim_id:
                    collected.append(ev)
                    if len(collected) >= 2:
                        break
            if not collected and include_risk:
                collected = evidence_pool[:1]
        if not collected:
            collected = evidence_pool[:1]
        # Always guarantee at least one evidence item.
        if not collected and evidence_pool:
            collected = evidence_pool[:1]
        return collected

    def _confidence(
        self, evidence: list[Evidence], base: float
    ) -> float:
        if not evidence:
            return min(base, 0.3)
        avg_evidence = sum(e.confidence for e in evidence) / len(evidence)
        return max(0.0, min(1.0, (base + avg_evidence) / 2.0))

    def _make_id(self, prefix: str, claim_id: str) -> str:
        return f"{prefix}-{claim_id}"


ALLOWED_HYPOTHESIS_TYPES: set[HypothesisType] = {
    "supply_chain_opportunity",
    "policy_beneficiary",
    "sentiment_turnaround",
    "geopolitical_substitution",
    "risk_mispricing",
    "demand_acceleration",
}


def is_opportunity_agent(obj: object) -> bool:
    """Runtime helper for ``isinstance``-free protocol checks."""
    return isinstance(obj, Agent) and getattr(obj, "name", None) == "opportunity"
