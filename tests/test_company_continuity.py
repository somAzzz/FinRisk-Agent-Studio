from copy import deepcopy
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from src.annual_reports import library
from src.annual_reports.company_identity import extract_issuer
from src.annual_reports.continuity import compare, resolve_record, workspace
from src.annual_reports.documents import Document, Page
from src.api.main import app
from src.research.journal import ResearchJournalStore
from src.schemas.finrisk import RiskReport, WorkflowTraceEvent

KEY = "de-mannheim-hrb-42"


def test_two_independent_originals_and_eligible_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("FINRISK_ANNUAL_LIBRARY", str(tmp_path))
    old = workspace(KEY, "2025-05-15")
    assert len(old["filings"]) == 1 and not old["comparisons"]
    (old_question,) = old["questions"]
    assert old_question["status"] == "unknown" and old_question["answer"] is None
    assert old_question["page"] == 58
    with pytest.raises(KeyError):
        workspace(KEY, "2025-05-14")
    new = workspace(KEY, "2026-05-21")
    assert len({f["sha256"] for f in new["filings"]}) == 2
    assert [f["issuer"]["registration"]["page"] for f in new["filings"]] == [187, 205]
    rows = new["comparisons"][0]["rows"]
    for metric, values in [("Umsatzerlöse", (3876, 2786, -1090)), ("Operatives Ergebnis", (-13, -177, -164))]:
        row = next(r for r in rows if (r["segment"], r["metric"]) == ("Zucker", metric))
        assert (row["prior"], row["current"], row["change"]) == values and row["pages"] == [3, 6]
    assert len(rows) == 12
    q = new["questions"][0]
    assert q["id"] == old_question["id"] and q["answer"]["value"] == -177 and q["status"] == "within_range"
    assert q["fulfillment"] == "unknown"
    assert all(not q.get("trail") for q in new["questions"])
    recent = workspace(KEY, "2026-11-08")
    saved = [q for q in recent["questions"] if q["kind"] == "existing_task"]
    assert len(saved) == 3
    assert all(q["status"] == q["fulfillment"] == "unknown" for q in saved)
    evidence = [e for q in saved for e in q["trail"]]
    assert any(e["verdict"] == "wrong_citation" and e["url"].startswith("https://") for e in evidence)
    assert all(e["published"] <= e["reviewed"] <= recent["as_of"] for e in evidence)


def test_no_merge_from_ticker_name_bond_or_conflicting_registration():
    page = Page(1, None, "Example AG\nISIN DE0007297004\nBörsenkürzel SZU", "native")
    assert extract_issuer(Document("url", "a", [page]), ["Example AG"])["status"] == "unknown"
    own = library.prior_entry()
    text = own["issuer"]["registration"]["quote"]
    doc = Document("url", "a", [Page(1, None, text + "\n" + text.replace("42 beim", "43 beim"), "native")])
    assert extract_issuer(doc, ["Südzucker AG"])["status"] == "unknown"
    assert extract_issuer(Document("url", "a", [Page(1, None, text, "native")]), ["Example AG"])["status"] == "unknown"
    entries = [own, library.sealed_entry()]
    assert resolve_record(entries, "SZU", "2026-05-21") is None
    assert resolve_record(entries, "SZUG.DE", "2025-12-01", as_of="2025-12-01") is None
    assert resolve_record(entries, "SZUG.DE", "2025-12-01", as_of="2026-05-21") == KEY
    conflict = deepcopy(own)
    conflict["issuer"]["company_id"] = "other"
    assert resolve_record(entries + [conflict], "SZUG.DE", "2026-05-21") is None
    assert resolve_record(entries, "WRONG", "2026-05-21", KEY) is None


def test_restatement_does_not_create_growth():
    a = library.bundle(library.PRIOR_ID)
    b = library.bundle(library.CASE_ID)
    b["annual"]["reconciliations"][0]["rows"][0]["values"][1] += 12
    row = compare(a, b)[0]
    assert row["status"] == "basis_unknown" and row["change"] is None


def test_existing_brief_and_journal_stores_join_through_api(tmp_path, monkeypatch):
    import asyncio

    from src.api import research, workflows
    from src.api.run_store import FinRiskSQLiteRunStore

    client = TestClient(app)
    monkeypatch.setenv("AUTH_DISABLED", "1")
    monkeypatch.setenv("FINRISK_SKIP_BACKGROUND", "1")
    monkeypatch.setenv("FINRISK_ANNUAL_LIBRARY", str(tmp_path))
    store = FinRiskSQLiteRunStore(tmp_path / "runs.sqlite")
    monkeypatch.setattr(workflows, "_run_store", store)
    monkeypatch.setattr(research, "_journal_store", ResearchJournalStore(tmp_path / "journals.sqlite"))

    def brief(ticker, company=None):
        payload = {"ticker": ticker, "analysis_goal": "Verify the fiscal result"}
        if company:
            payload["company_id"] = company
        return client.post("/workflows/finrisk/run", json=payload)

    assert brief("WRONG", KEY).status_code == 422
    for ticker, company in [("SZU", KEY), ("SZU", None), ("SZUG.DE", None)]:
        resp = brief(ticker, company)
        assert resp.status_code == 202, resp.text
        state = asyncio.run(store.get(resp.json()["run_id"]))
        # Storage-contract fixture: no model/network. The financial acceptance above uses two actual reports.
        state.status = "completed"
        state.report = RiskReport(
            title="FY operating result",
            executive_summary="Reviewed issuer disclosure.",
            evidence_vs_inference="Annual accounts",
            limitations="No causal attribution.",
            markdown="Reviewed.",
        )
        stamp = datetime(2026, 5, 21, 12, tzinfo=UTC)
        state.trace = [
            WorkflowTraceEvent(step_name="report_generator", status="completed", started_at=stamp, completed_at=stamp)
        ]
        asyncio.run(store.update(state))
    thesis = {
        "ticker": "SZU",
        "statement": "Watch operating result",
        "time_horizon": "12 months",
        "disconfirming_conditions": ["New disclosure"],
    }
    for extra in [{"company_id": KEY}, {}]:
        assert client.post("/research/theses", json=thesis | extra).status_code == 201
    assert client.post("/research/theses", json=thesis | {"company_id": "other"}).status_code == 422
    url = "/research/companies/" + KEY + "/workspace"
    today = client.get(url).json()
    assert len(today["briefs"]) == 2 and len(today["journal"]) == 1
    earlier = client.get(url, params={"as_of": "2025-05-15"}).json()
    assert not earlier["briefs"] and not earlier["journal"]
    assert client.get("/research/companies/missing/workspace").status_code == 404


def test_esef_only_merges_unique_valid_reporting_lei():
    from src.annual_reports.documents import extract

    def report(second):
        body = f"""<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" xmlns:x="http://www.xbrl.org/2003/instance"><body>
        <x:context id="a"><x:entity><x:identifier scheme="http://standards.iso.org/iso/17442">529900T8BM49AURSDO55</x:identifier></x:entity></x:context>
        <x:context id="b"><x:entity><x:identifier scheme="http://standards.iso.org/iso/17442">{second}</x:identifier></x:entity></x:context>
        <ix:nonFraction name="Profit" contextRef="a">1</ix:nonFraction>
        <ix:nonFraction name="Sales" contextRef="b">3</ix:nonFraction></body></html>"""
        return extract_issuer(extract(body.encode(), "inline"), ["Example issuer"])

    assert report("529900T8BM49AURSDO55")["company_id"] == "lei-529900t8bm49aursdo55"
    assert report("529900T8BM49AURSDO56")["status"] == "unknown"
