from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from src.api.research import (
    ManagementResearchService,
    get_management_comparison,
    set_management_research_service_for_tests,
)
from src.schemas.transcripts import Transcript, TranscriptTurn


class _Provider:
    def get_transcript(self, ticker: str, year: int, quarter: int) -> Transcript:
        positive = year >= 2026
        return Transcript(
            ticker=ticker,
            year=year,
            quarter=quarter,
            provider="fixture",
            transcript_id=f"{ticker}-{year}Q{quarter}",
            published_at=datetime(year, 4, 1, tzinfo=UTC),
            turns=[
                TranscriptTurn(
                    speaker="CEO",
                    role="ceo",
                    text=(
                        "We raised guidance on strong demand."
                        if positive
                        else "We lowered guidance as demand was weak."
                    ),
                    section="prepared_remarks",
                    turn_index=0,
                )
            ],
        )


@pytest.fixture(autouse=True)
def _service():
    set_management_research_service_for_tests(ManagementResearchService(_Provider()))
    yield
    set_management_research_service_for_tests(ManagementResearchService())


@pytest.mark.asyncio
async def test_management_api_compares_evidence_backed_periods() -> None:
    response = await get_management_comparison("ACME", 2026, 1, 2025, 4)
    assert response.current.guidance_signal == "raised"
    assert response.previous is not None
    assert response.previous.guidance_signal == "lowered"
    assert any(change.dimension == "guidance_signal" for change in response.changes)


@pytest.mark.asyncio
async def test_management_api_requires_complete_comparison_period() -> None:
    with pytest.raises(HTTPException) as raised:
        await get_management_comparison("ACME", 2026, 1, 2025, None)
    assert raised.value.status_code == 422
