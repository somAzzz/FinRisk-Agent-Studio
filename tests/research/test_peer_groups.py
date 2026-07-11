from __future__ import annotations

import pytest

from src.research.peer_groups import (
    PeerGroupInput,
    PeerGroupStore,
    PeerMember,
    suggest_peer_candidates,
)


def _input() -> PeerGroupInput:
    return PeerGroupInput(
        name="Semiconductor leaders",
        base_ticker="NVDA",
        industry_template="semiconductor",
        members=[
            PeerMember(ticker="NVDA", inclusion_reason="Base company"),
            PeerMember(ticker="AMD", inclusion_reason="Accelerator competitor"),
        ],
    )


def test_peer_group_store_round_trip(tmp_path) -> None:
    store = PeerGroupStore(tmp_path / "research.sqlite")

    saved = store.save(_input())

    assert store.get(saved.peer_group_id) == saved
    assert store.list() == [saved]
    updated_input = _input().model_copy(update={"name": "Updated peers"})
    updated = store.update(saved.peer_group_id, updated_input)
    assert updated.name == "Updated peers"
    assert updated.created_at == saved.created_at
    assert store.delete(saved.peer_group_id)
    assert store.list() == []


def test_peer_group_requires_base_and_confirmation() -> None:
    with pytest.raises(ValueError, match="base_ticker"):
        PeerGroupInput(
            name="Invalid",
            base_ticker="NVDA",
            members=[
                PeerMember(ticker="AMD", inclusion_reason="Competitor"),
                PeerMember(ticker="INTC", inclusion_reason="Competitor"),
            ],
        )
    with pytest.raises(ValueError, match="confirmed"):
        PeerGroupInput(
            name="Invalid suggestion",
            base_ticker="NVDA",
            members=[
                PeerMember(ticker="NVDA", inclusion_reason="Base"),
                PeerMember(
                    ticker="AMD",
                    inclusion_reason="Suggested from SIC",
                    source="suggested",
                    confirmed_by_user=False,
                ),
            ],
        )


def test_suggests_same_sic_candidates_without_confirming_them() -> None:
    class Identity:
        def __init__(self, ticker: str) -> None:
            self.ticker = ticker
            self.cik = ticker
            self.name = f"{ticker} Corp"

    class Resolver:
        def resolve(self, ticker: str):
            return Identity(ticker)

    submissions = {
        "BASE": {"sic": "3674", "sicDescription": "Semiconductors"},
        "EXACT": {"sic": "3674", "sicDescription": "Semiconductors"},
        "DIV": {"sic": "3679", "sicDescription": "Electronic components"},
        "OTHER": {"sic": "6021", "sicDescription": "Banks"},
    }

    candidates = suggest_peer_candidates(
        base_ticker="BASE",
        candidate_tickers=["OTHER", "DIV", "EXACT"],
        resolver=Resolver(),
        submissions_fetcher=lambda cik: submissions[cik],
    )

    assert [item.ticker for item in candidates] == ["EXACT", "DIV"]
    assert candidates[0].similarity == "same_sic"
    assert all(item.confirmed_by_user is False for item in candidates)
    assert "requires analyst confirmation" in candidates[0].inclusion_reason
