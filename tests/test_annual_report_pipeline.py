# ruff: noqa: RUF001 -- German PDF fixtures preserve the original minus glyphs.
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from src.annual_reports.analysis import ExternalReport, Options, Shock, analyze
from src.annual_reports.decisions import PlantDecision
from src.annual_reports.documents import Document, DocumentError, Page, extract
from src.annual_reports.financials import reconciliation


def sample_document():
    text = """Operatives Ergebnis nach Segmenten
Mio. € 2025/26 2024/25 +/– in %
Sugar –177 –13
Other 340 363
Konzern 163 350
"""
    return Document("file", "digest", [Page(1, "4", text, "native")])


def test_segment_reconciliation_detects_misaligned_total():
    doc = sample_document()
    assert reconciliation(doc)[0]["status"] == "passed"
    doc.pages[0].text = doc.pages[0].text.replace("Konzern 163", "Konzern 162")
    assert reconciliation(doc)[0]["status"] == "mismatch"


def test_historical_analysis_excludes_later_external_source(monkeypatch):
    monkeypatch.setattr("src.annual_reports.analysis.extract", lambda *_: sample_document())
    late = ExternalReport(url="https://example.com/future.pdf", published_at=date(2026, 10, 8), topic="prices")
    options = Options(as_of=date(2026, 5, 21), published_at=date(2026, 5, 21), external=[late], narrative=False)
    result = analyze(b"test", "upload", options)
    assert result["external_events"][0]["status"] == "excluded_future_publication"
    assert set(result["sources"]) == {"annual"}
    options.published_at = date(2026, 5, 22)
    with pytest.raises(DocumentError, match="after"):
        analyze(b"test", "upload", options)


def test_ocr_does_not_discard_native_chart_percentages(monkeypatch):
    from src.annual_reports import documents

    monkeypatch.setattr(documents, "native_pages", lambda _: [Page(1, None, "Production –18,2 %", "native")])
    monkeypatch.setattr(documents, "ocr_page", lambda *_: "Production chart")
    doc = extract(b"%PDF-test", "test.pdf", {1})
    assert "–18,2 %" in doc.pages[0].text
    assert doc.warnings and doc.pages[0].method == "native+ocr"


def test_empty_scan_with_failed_ocr_is_not_a_success(monkeypatch):
    from src.annual_reports import documents

    monkeypatch.setattr(documents, "native_pages", lambda _: [Page(1, None, "", "native")])

    def fail(*_):
        raise DocumentError("OCR failed")

    monkeypatch.setattr(documents, "ocr_page", fail)
    with pytest.raises(DocumentError, match="No readable"):
        extract(b"%PDF-test", "scan.pdf")


def test_scenario_and_strategic_alternatives():
    scenario = Shock(
        name="stress",
        segment="sugar",
        currency="EUR",
        tonnes=100,
        price=20,
        variable_cost=10,
        volume_change="-0.1",
        price_change_per_tonne=2,
        repricing_share="0.5",
        cost_change_per_tonne=1,
        additional_idle_cost=25,
    )
    assert scenario.impact()["revenue_delta"] == Decimal("-110")
    assert scenario.impact()["contribution_after_idle_cost_delta"] == Decimal("-125")
    plant = PlantDecision(
        site="example",
        currency="EUR",
        assumptions_source="test assumptions",
        discount_rate=0,
        alternatives=[
            {"action": a, "initial_outflow": i, "annual_net_cashflows": [10, 5], "terminal_proceeds": 0}
            for a, i in (("continue", 5), ("convert", 15), ("exit", 20))
        ],
    )
    assert plant.compare()["npv"] == {"continue": 10, "convert": 0, "exit": -5}


def test_esef_scale_context_and_sign():
    data = b"""<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"><body>
    <context id="fy"><endDate>2026-02-28</endDate></context><unit id="eur">EUR</unit>
    <ix:nonFraction name="ifrs-full:ProfitLoss" contextRef="fy" unitRef="eur" format="ixt:num-comma-decimal"
    scale="6" sign="-">1.234,5</ix:nonFraction></body></html>"""
    fact = extract(data, "report.xhtml").tagged_facts[0]
    assert Decimal(fact["value"]) == -1234500000
    assert fact["context"] == ["2026-02-28"] and fact["unit"] == ["EUR"]


def test_uploaded_name_cannot_read_server_file(monkeypatch):
    from fastapi.testclient import TestClient

    from src.api.main import app

    monkeypatch.setenv("AUTH_DISABLED", "1")
    client = TestClient(app)
    result = client.post("/workflows/annual-report/upload", params={"filename": str(Path(__file__))}, content=b"")
    assert result.status_code == 422


def test_online_private_address_is_blocked():
    from src.annual_reports.documents import download

    with pytest.raises(DocumentError, match="publicly routable"):
        download("http://127.0.0.1:8001/v1/models")


def test_market_series_uses_only_observations_available_at_release(monkeypatch):
    import hashlib

    from src.annual_reports.markets import MarketSeries

    csv = b"day,price\n2026-05-01,42\n2026-05-02,40\n2026-05-04,50\n"
    monkeypatch.setattr("src.annual_reports.markets.download", lambda url, **kw: (csv, url))
    series = MarketSeries(
        driver="sugar_price",
        segment="sugar",
        region="EU",
        unit="EUR/t",
        url="https://example.org/snapshot",
        published_at=date(2026, 5, 3),
        date_column="day",
        value_column="price",
        sha256=hashlib.sha256(csv).hexdigest(),
    )
    assert series.snapshot(date(2026, 5, 2))["status"] == "excluded_future_publication"
    assert series.snapshot(date(2026, 5, 3))["change_in_source_units"] == -2


@pytest.mark.parametrize("same_swatch", [False, True])
def test_chart_units_and_years_follow_colors_not_pdf_reading_order(same_swatch):
    from io import BytesIO
    from xml.etree.ElementTree import Element, SubElement, tostring

    from PIL import Image, ImageDraw

    from src.annual_reports.charts import chart_rows

    page = SubElement(root := Element("doc"), "page", width="300", height="100")
    image = Image.new("RGB", (300, 100), "white")
    paint = ImageDraw.Draw(image)
    for text, x, y, width in [
        ("GRAFIK 001", 230, 78, 46),
        ("2024", 240, 64, 14),
        ("2025", 262, 64, 14),
        ("+15,1 %", 240, 36, 30),
        ("12,1 t/ha", 34, 45, 35),
        ("13,9 t/ha", 34, 36, 35),
        ("Zuckerertrag", 32, 28, 48),
    ]:
        line = SubElement(page, "line", xMin=str(x), xMax=str(x + width), yMin=str(y), yMax=str(y + 6))
        SubElement(line, "word").text = text
    for box, color in [
        ((234, 65, 239, 69), "lightblue"),
        ((256, 65, 261, 69), "lightblue" if same_swatch else "navy"),
        ((34, 36, 169, 42), "navy"),
        ((34, 45, 143, 51), "lightblue"),
    ]:
        paint.rectangle(box, fill=color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    rows = chart_rows(tostring(root), buffer.getvalue(), 45, "43")
    if same_swatch:
        assert rows == []
    else:
        (row,) = rows
        assert row["metric"] == "Zuckerertrag" and row["unit"] == "t/ha"
        assert row["decimal_values"] == {"2024": "12.1", "2025": "13.9"}
        assert row["change"] == {
            "from_year": "2024",
            "to_year": "2025",
            "unit": "%",
            "value": "+15,1",
            "decimal_value": "15.1",
        }


def test_local_findings_reject_repeated_forged_evidence(monkeypatch):
    import json

    import httpx
    from pydantic_ai.messages import ModelResponse, TextPart
    from pydantic_ai.models.function import FunctionModel

    from src.ai import model_factory
    from src.annual_reports.analysis import grounded_findings

    attempts = []
    finding = {
        "topic": "production", "subject": "factory", "counterparty_or_region": "region",
        "status": "reported", "assessment": "Output increased", "contrary_evidence_or_test": "Check volume",
        "missing_data": "Volume", "decision": "Review the filing", "evidence_ids": ["FORGED"],
    }

    async def respond(messages, info):
        attempts.append(messages)
        return ModelResponse(parts=[TextPart(json.dumps({"items": [finding]}))], finish_reason="stop")

    def reject_raw_http(*args, **kwargs):
        pytest.fail("The local analysis bypassed the model runtime")

    monkeypatch.setenv("LLM_PROVIDER", "sglang")
    monkeypatch.setattr(model_factory, "build_agent_model", lambda config: FunctionModel(respond))
    monkeypatch.setattr(httpx.Client, "post", reject_raw_http)
    findings, warnings = grounded_findings(
        {"annual": {1: "The company reported a change in its production volume."}},
        "production", date(2026, 5, 1), {"annual": date(2026, 4, 1)},
    )
    assert not findings and warnings
    assert len(attempts) == 2
