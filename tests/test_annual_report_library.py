from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.annual_reports import library
from src.api import annual_reports
from src.api.main import app


def test_sealed_snapshot_boundaries():
    may, oct_, nov = (library.bundle(library.CASE_ID, d) for d in library.DAYS)
    assert may["reviewed"] is None and not may["segment_nodes"]
    for snapshot in [may, oct_, nov]:
        fresh = snapshot["fresh"]
        assert not fresh["alerts"]
        assert set(fresh["eligible_digests"]) == {source["digest"] for source in fresh["originals"]}
        assert all(source["published"] <= snapshot["cutoff"] for source in fresh["originals"])
        if snapshot is not nov:
            assert not snapshot["narrative"] and not snapshot["product"]
            assert not snapshot["annual"]["fact_reviews"] and "search_trace" not in fresh
    assert {a["alert"] for a in nov["reviewed"]["alerts"]} == {a["alert"] for a in oct_["reviewed"]["alerts"]}
    assert len(oct_["reviewed"]["alerts"]) == 2
    assert all(a["day"] == oct_["cutoff"] for a in nov["reviewed"]["alerts"])
    assert all(a["attributable_operating_result"] == a["fulfillment"] == "unknown" for a in nov["reviewed"]["alerts"])
    assert len(nov["annual"]["financial_rows"]) == 128
    assert len(nov["product"]["edges"]) == 28
    assert all(e["status"] == "unknown" for e in nov["product"]["edges"])
    assert Counter(e["provenance"] for e in nov["reviewed"]["edges"])["model_inference"] == 7
    assert nov["segment_nodes"]["Zucker"] == "Segment/Sugar"
    with pytest.raises(KeyError):
        library.bundle(library.CASE_ID, "2026-10-01")


def test_saved_job_and_original_survive_reopen(monkeypatch, tmp_path):
    monkeypatch.setenv("FINRISK_ANNUAL_LIBRARY", str(tmp_path))
    monkeypatch.setenv("AUTH_DISABLED", "1")
    annual = library.read(library.CASE / "annual.json")
    calls = []

    def analyze(data, source, _options):
        calls.append(source)
        return annual

    monkeypatch.setattr(annual_reports, "analyze", analyze)
    client = TestClient(app)
    url = "/workflows/annual-report"
    pdf = b"%PDF-test-original"
    response = client.post(url + "/jobs/upload", params={"filename": "../issuer.pdf"}, content=pdf)
    assert response.status_code == 202
    job = client.get(url + "/jobs/" + response.json()["id"]).json()
    assert job["status"] == "completed" and "owner" not in job
    run = job["report_id"]
    assert any(x["id"] == run for x in client.get(url + "/library").json())
    result = client.get(url + "/library/" + run).json()
    assert result["annual"] == annual and "reviewed" not in result
    assert client.get(result["original"]).content == pdf
    assert calls == ["issuer.pdf"]
    assert client.get(url + "/library/" + run + "?cutoff=2000-01-01").status_code == 404
    assert client.get(url + "/library/jobs").status_code == 404
    assert library.persist(annual, b"document") != run
    with pytest.raises(KeyError):
        library.directory(str(Path(__file__)))


def test_failed_job_is_recoverable_without_creating_a_report(monkeypatch, tmp_path):
    monkeypatch.setenv("FINRISK_ANNUAL_LIBRARY", str(tmp_path))
    monkeypatch.setenv("AUTH_DISABLED", "1")
    client = TestClient(app)
    response = client.post("/workflows/annual-report/jobs/upload", content=b"")
    assert response.status_code == 202
    job = client.get("/workflows/annual-report/jobs/" + response.json()["id"]).json()
    assert job["status"] == "failed" and "report_id" not in job
    assert not list(tmp_path.glob("run-*"))


def test_url_job_runs_real_parser_and_protects_archive(monkeypatch, tmp_path):
    client = TestClient(app)
    url = "/workflows/annual-report"
    monkeypatch.delenv("AUTH_DISABLED", raising=False)
    monkeypatch.setenv("FINRISK_API_KEYS", "annual-test-key")
    monkeypatch.setenv("FINRISK_ANNUAL_LIBRARY", str(tmp_path))
    assert client.get(url + "/library").status_code == 401
    assert client.get(url + "/jobs/not-a-job").status_code == 401
    client.headers["X-API-Key"] = "annual-test-key"
    html = b"""<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"><body><h1>Example issuer</h1>
    <context id="fy"><endDate>2026-02-28</endDate></context><unit id="eur">EUR</unit>
    <ix:nonFraction name="ifrs-full:ProfitLoss" contextRef="fy" unitRef="eur">123</ix:nonFraction></body></html>"""
    monkeypatch.setattr(annual_reports, "download", lambda source: (html, source))
    response = client.post(url + "/jobs/url", json={"url": "https://example.org/issuer.xhtml", "narrative": False})
    assert response.status_code == 202
    job = client.get(url + "/jobs/" + response.json()["id"]).json()
    assert job["status"] == "completed", job
    b = client.get(url + "/library/" + job["report_id"]).json()
    assert b["original"] is None and len(b["annual"]["sources"]) == 1
    assert b["annual"]["inline_xbrl_facts"][0]["value"] == "123"
    assert "fresh" not in b and "reviewed" not in b
