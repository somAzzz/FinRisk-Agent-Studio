from datetime import date

import pytest

from src.annual_reports import blind, blind_sources


def edge(a, ak, role, b, bk, status="supported"):
    return {"subject": a, "subject_kind": ak, "relation": role, "object": b, "object_kind": bk, "status": status}


def test_verified_segment_paths_do_not_expand_company_or_region_exposure():
    rows = [
        edge("Example", "Company", "HAS_SEGMENT", "Hardware", "Segment"),
        edge("Example", "Company", "HAS_SEGMENT", "Research", "Segment"),
        edge("Hardware", "Segment", "PRODUCES", "Instrument A", "Product"),
        edge("Research", "Segment", "PRODUCES", "Instrument A", "Product", "unknown"),
        edge("Hardware", "Segment", "LOCATED_IN", "West", "Region"),
        edge("Unverified division", "Segment", "USES", "Instrument B", "Product"),
    ]
    assert blind.routes(rows) == {"Product/Instrument A": [rows[2]]}


def test_missing_audit_verdict_defaults_to_unknown(monkeypatch):
    monkeypatch.setattr(blind, "structured", lambda *a: blind.Reviews(decisions=[]))
    assert blind.adjudicate([{"fact": "unresolved"}], ["text"], "audit")[0]["status"] == "unknown"


@pytest.mark.parametrize(
    "article,reason",
    [
        ("<main>no dated release</main>", "publication metadata"),
        ('<meta property="article:published_time" content="2027-01-01"><main>future</main>', "cutoff"),
    ],
)
def test_external_release_requires_dated_original(monkeypatch, tmp_path, article, reason):
    url = "https://agency.gov/notice"
    monkeypatch.setattr(blind_sources, "download", lambda *a, **kw: (article.encode(), url))
    with pytest.raises(ValueError, match=reason):
        blind_sources.fetch({"url": url}, date(2026, 11, 8), tmp_path)
    assert not list(tmp_path.iterdir())


def test_misleading_authority_domain_rejected_before_fetch(tmp_path):
    with pytest.raises(ValueError, match="publisher"):
        blind_sources.fetch({"url": "https://agency.gov.example.org/news"}, date.today(), tmp_path)


def test_official_id_dash_and_adjacent_articles():
    pages = [
        "unrelated opening [FR Doc. 2026\u201311111 Filed yesterday] correct opening",
        "correct ending [FR Doc. 2026\u201322222 Filed today] adjacent notice",
    ]
    result = blind_sources.register_pages(pages, "2026-22222")
    assert "correct opening" in result[0] and "unrelated opening" not in result[0]
    assert result[1] == "correct ending "
    with pytest.raises(ValueError, match="missing"):
        blind_sources.register_pages(pages, "2026-33333")
