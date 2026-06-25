"""Analysis models: sentiment, policy exposure, and risk assessment outputs.

These schemas describe the structured outputs produced by the
``sentiment_agent``, ``policy_geo_agent`` and ``risk_agent`` modules. Every
model uses ``extra="forbid"`` and ``Pydantic v2`` semantics so the rest of
the pipeline can rely on a closed data contract.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.claims import Claim
from src.schemas.entities import Entity
from src.schemas.evidence import Evidence

Topic = Literal[
    "demand",
    "margin",
    "supply_chain",
    "capex",
    "guidance",
    "competition",
    "policy",
    "geopolitics",
]

SentimentLabel = Literal["positive", "neutral", "negative", "mixed", "unclear"]

OverallTone = Literal["positive", "neutral", "negative", "mixed"]

GuidanceSignal = Literal["raised", "lowered", "maintained", "unclear"]

PolicyExposureType = Literal["beneficiary", "risk", "mixed", "unknown"]

TimeHorizon = Literal["short", "mid", "long", "unknown"]


class TopicSentiment(BaseModel):
    """Sentiment on a single topic, anchored to supporting evidence."""

    model_config = ConfigDict(extra="forbid")

    topic: Topic
    sentiment: SentimentLabel
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)


class ManagementSentimentResult(BaseModel):
    """Aggregated management-tone view across transcripts and MD&A."""

    model_config = ConfigDict(extra="forbid")

    overall_tone: OverallTone
    uncertainty: float = Field(ge=0.0, le=1.0)
    defensiveness: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    guidance_signal: GuidanceSignal = "unclear"
    topic_sentiment: list[TopicSentiment] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)


class PolicyExposure(BaseModel):
    """A single policy exposure (beneficiary, risk, or mixed)."""

    model_config = ConfigDict(extra="forbid")

    policy_name: str
    exposure_type: PolicyExposureType
    affected_segments: list[str] = Field(default_factory=list)
    time_horizon: TimeHorizon = "unknown"
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[Evidence] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)


class GeopoliticalExposure(BaseModel):
    """A single geopolitical risk or opportunity exposure."""

    model_config = ConfigDict(extra="forbid")

    risk_type: str
    region: str
    impacted_entities: list[Entity] = Field(default_factory=list)
    supply_chain_paths: list[list[Entity]] = Field(default_factory=list)
    risk_score: float = Field(ge=0.0, le=1.0)
    opportunity_offset: list[Claim] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    """Aggregated risk view for a company."""

    model_config = ConfigDict(extra="forbid")

    company: Entity
    risks: list[Claim] = Field(default_factory=list)
    overall_risk_score: float = Field(ge=0.0, le=1.0)
    top_risk_categories: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
