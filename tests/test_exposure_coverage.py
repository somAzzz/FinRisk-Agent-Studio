from datetime import date

import pytest

from scripts.score_exposure_coverage import compare
from src.annual_reports import non_us
from src.annual_reports.coverage import eight_pages, windows
from src.annual_reports.documents import Document, Page


def test_eight_unique_pages_and_full_window_coverage():
    d = Document(
        "example", "sha", [Page(i, None, "reportable segments and customers " * 5, "native") for i in range(1, 20)]
    )
    selected = eight_pages(d)
    assert len(set(selected)) == len(selected) == 8
    source = "a" * 5100 + "distinct boundary sentence" + "b" * 6200
    assert any("distinct boundary sentence" in w for w in windows(source))
    assert list(windows(source))[-1].endswith("b" * 100)


def test_duplicates_abstentions_and_wrong_direction_do_not_inflate_precision_or_recall():
    edge = {
        "subject_kind": "Company",
        "subject": "Example",
        "relation": "HAS_SEGMENT",
        "object_kind": "Segment",
        "object": "Materials",
        "evidence_pages": [1],
    }
    p = {**edge, "status": "supported"}
    missed = {**edge, "object": "Services", "evidence_pages": [12]}
    bad = {**p, "subject_kind": "Segment", "subject": "Materials", "object_kind": "Company", "object": "Example"}
    r = compare(
        {"edges": [edge, missed]},
        {"sample_pages": [1], "edges": [p, {**p, "object": "Materials segment"}, bad, {**missed, "status": "unknown"}]},
    )
    assert (r["TP"], r["FP"], r["FN"]) == (1, 1, 1)
    assert r["precision"] == r["recall"] == 0.5


def test_us_hit_is_never_fetched(monkeypatch, tmp_path):
    monkeypatch.setattr(non_us, "british_hits", lambda q: [])
    monkeypatch.setattr(non_us, "web_hits", lambda q: [{"url": "https://www.fda.gov/example", "title": "US"}])

    def fail(*args):
        pytest.fail("US original fetched in non-US mode")

    monkeypatch.setattr(non_us, "fetch", fail)
    docs, trace = non_us.discover_non_us([{"target": "Product/Test", "web_query": "Test"}], date.today(), tmp_path)
    assert not docs
    assert trace[-1]["results"][0]["decision"] == "Outside the non-US official-source scope"
