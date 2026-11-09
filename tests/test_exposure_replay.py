"""Regression checks for period selection, provenance and as-of boundaries."""

# ruff: noqa: RUF001 -- exercise the original PDF minus signs.
import json
from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest

from src.annual_reports.exposure import EvidenceBook, audit_lineage, build, half_year_actuals

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "config/annual_reports/suedzucker-p1.json"
ARCHIVE = ROOT / ".cache/p0/verified/597193d6e3ff8ba3"
CACHE = ROOT / ".cache/p1/sources"
OCT = "2026-10-08"
NOV = "2026-11-08"
TABLE = """Business performance – Sugar segment
2nd quarter      1st half year
2026/27    2025/26   + / – in %   2026/27   2025/26   + / – in %
Revenues          € million   640    685    – 6.6    1,269    1,389    – 8.6
Operating EBITDA  € million   –3    –12   –75    –24    –46    –47.8
Operating result  € million   – 23    – 33   – 30.3    – 63    – 89    – 29.2
"""


def test_signed_half_year_metrics_and_fail_closed_layout():
    actual = half_year_actuals(TABLE, "Sugar")
    assert actual["Operating result"] == {"prior": -89, "current": -63, "change": 26}
    assert actual["Revenues"]["change"] == -120
    for bad in [
        TABLE.replace("2nd quarter", "1st quarter"),
        TABLE.replace("€ million", "%"),
        TABLE.replace("1,389", "unavailable"),
        TABLE.replace("Sugar segment", "Starch segment"),
    ]:
        with pytest.raises(ValueError):
            half_year_actuals(bad, "Sugar")


def test_future_material_never_opened(tmp_path):
    case = json.loads(CASE.read_text())
    book = EvidenceBook(case, tmp_path, tmp_path, date.fromisoformat(OCT), False)
    assert book.cite("de_review") is None
    assert book.cite("de_cabinet") is None
    assert book.used == {}
    with pytest.raises(ValueError, match="Future"):
        book.original("de_cabinet")


@pytest.fixture
def local_case():
    c = json.loads(CASE.read_text())
    if not (ARCHIVE / f"{OCT}.json").exists() or not CACHE.exists():
        pytest.skip("Local pinned source archive is required for issuer replay")
    return c


def test_reverse_replay_and_unknowns(local_case, tmp_path):
    november = build(local_case, ARCHIVE, CACHE, NOV)
    october = build(local_case, ARCHIVE, CACHE, OCT)
    for r in [november, october]:
        assert not r["unmapped_alerts"]
        assert len(r["alerts"]) == 2
        assert all(
            a["attributable_revenue"] == a["attributable_operating_result"] == a["fulfillment"] == "unknown"
            for a in r["alerts"]
        )
        assert [
            (a["actuals"]["Revenues"]["change"], a["actuals"]["Operating result"]["change"]) for a in r["alerts"]
        ] == [(-120, 26), (-18, 7)]
        assert all(e["published"] <= r["as_of"] for e in r["evidence"].values())
        assert r["policies"]["FR"]["status"] == "in force"
        assert r["policies"]["EU"]["status"] == "Commission policy coordination"
        assert r["tax_scenario"]["tonnes_removed"] == 60
        assert {a["alert"] for a in r["alerts"]} == {a["alert"] for a in october["alerts"]}
    assert october["policies"]["DE"]["status"] == "coalition proposal"
    assert november["policies"]["DE"]["status"] == "under parliamentary consideration"
    assert not {"de_review", "de_scope", "de_cabinet"} & october["evidence"].keys()
    # Discard everything first available after October; the entire October output must be identical.
    for path in ARCHIVE.iterdir():
        if path.suffix == ".pdf" or path.name in (OCT + ".json", "2026-05-21.json"):
            (tmp_path / path.name).symlink_to(path)
    for doc in local_case["documents"].values():
        original = CACHE / (doc["sha256"] + "." + doc["format"])
        if doc["published"] <= OCT and original.exists():
            (tmp_path / original.name).symlink_to(original)
    assert build(local_case, tmp_path, tmp_path, OCT) == october


def test_reject_false_jurisdiction_status_and_quote(local_case):
    backdated = deepcopy(local_case)
    backdated["documents"]["de_cabinet"]["published"] = "2026-10-01"
    with pytest.raises(ValueError, match="Publication date"):
        build(backdated, ARCHIVE, CACHE, OCT)
    bad = deepcopy(local_case)
    next(s for s in bad["policy_task"]["states"] if s["jurisdiction"] == "FR")["jurisdiction"] = "DE"
    with pytest.raises(ValueError, match="Jurisdiction mismatch"):
        build(bad, ARCHIVE, CACHE, OCT)
    bad = deepcopy(local_case)
    bad["policy_task"]["states"][0].update(status="in force", effective=OCT)
    with pytest.raises(ValueError, match="in-force"):
        build(bad, ARCHIVE, CACHE, OCT)
    snap = json.loads((ARCHIVE / f"{OCT}.json").read_text())
    alert = next(n for n in snap["graph"]["nodes"] if n["kind"] == "Alert")
    _, verdict = audit_lineage(snap, alert)
    verdict["quote"] = "A named customer cancelled deliveries."
    with pytest.raises(ValueError, match="lineage"):
        audit_lineage(snap, alert)
