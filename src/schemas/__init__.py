"""Shared schemas for FinText-LLM.

Centralizes the data contracts used across data ingestion, agents,
graph storage, and analysis modules.
"""

from src.schemas.claims import Claim, ClaimType
from src.schemas.entities import Entity, EntityType
from src.schemas.evidence import Evidence, SourceType
from src.schemas.filings import FilingMetadata, FilingRecord
from src.schemas.ids import stable_id
from src.schemas.relations import Relation, RelationType
from src.schemas.transcripts import Transcript, TranscriptMeta, TranscriptTurn

__all__ = [
    "Claim",
    "ClaimType",
    "Entity",
    "EntityType",
    "Evidence",
    "FilingMetadata",
    "FilingRecord",
    "Relation",
    "RelationType",
    "SourceType",
    "Transcript",
    "TranscriptMeta",
    "TranscriptTurn",
    "stable_id",
]
