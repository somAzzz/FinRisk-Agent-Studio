"""Read-only sealed case snapshots and immutable, server-owned annual analysis runs."""

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
CASE = ROOT / "docs/reports/suedzucker-reanalysis"
CASE_ID = "suedzucker-2025-26"
CASE_URL = "https://www.suedzuckergroup.com/sites/default/files/2026-05/Suedzucker_Geschaeftsbericht_2025-26.pdf"
PUBLIC = ROOT / "docs/reports/company-continuity"
PRIOR_ID = "suedzucker-2024-25"
DAYS = ["2026-05-21", "2026-10-08", "2026-11-08"]


def store():
    return Path(os.getenv("FINRISK_ANNUAL_LIBRARY", ROOT / ".cache/annual-report-library"))


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def entry(run_id, annual):
    meta = annual["identity"]
    cover = meta.get("cover") or []
    company = cover[0] if cover else "Unnamed issuer"
    return {
        "id": run_id,
        "issuer": meta.get("issuer", {"status": "unknown", "company_id": None}),
        "period_end": meta.get("period_end"),
        "company": company,
        "period": f"{meta.get('period_start') or '?'} to {meta.get('period_end') or '?'}",
        "published": meta.get("published_at") or annual["sources"]["annual"].get("published_at"),
        "as_of": annual["as_of"],
        "sha256": annual["sources"]["annual"]["sha256"],
        "pages": annual["sources"]["annual"]["page_count"],
        "status": annual["status"],
        "dates": [annual["as_of"]],
        "lanes": ["Annual analysis"],
    }


def prior_entry():
    annual = read(PUBLIC / "2024-25.json")
    return {**entry(PRIOR_ID, annual), "period": "FY 2024/25"}


def sealed_entry():
    proof = read(PUBLIC / "2025-26.json")
    if proof["sources"]["annual"]["sha256"] != "597193d6e3ff8ba389272bdfd597554a278b4ad9cc1137d87d8d5232d90a791e":
        raise ValueError("Issuer proof fingerprint mismatch")
    return {
        "issuer": proof["identity"]["issuer"],
        "period_end": proof["identity"]["period_end"],
        "id": CASE_ID,
        "company": "Südzucker AG",
        "period": "FY 2025/26",
        "published": DAYS[0],
        "as_of": DAYS[-1],
        "dates": DAYS,
        "pages": 278,
        "lanes": ["Annual analysis", "Fresh tracking", "Reviewed replay"],
        "status": "needs_review",
        "sha256": "597193d6e3ff8ba389272bdfd597554a278b4ad9cc1137d87d8d5232d90a791e",
    }


@lru_cache(maxsize=64)
def _legacy_issuer(path, fingerprint, modified):
    """Backfill a derived view without altering a saved historical analysis."""
    from hashlib import sha256

    from src.annual_reports.company_identity import extract_issuer
    from src.annual_reports.documents import Document, DocumentError, native_pages

    original = path / "original.pdf"
    data = original.read_bytes()
    if sha256(data).hexdigest() != fingerprint:
        return {}
    try:
        doc = Document(str(original), fingerprint, native_pages(data))
        return extract_issuer(doc, doc.pages[0].text.splitlines()[:1])
    except DocumentError:
        return {}


def saved_meta(path):
    meta = read(path / "meta.json")
    if "issuer" not in meta and (path / "original.pdf").is_file():
        meta["issuer"] = _legacy_issuer(path, meta["sha256"], (path / "original.pdf").stat().st_mtime_ns)
        if meta["issuer"].get("company_id"):
            meta["period_end"] = read(path / "annual.json")["identity"].get("period_end")
    return meta


def entries():
    saved = [saved_meta(p.parent) for p in store().glob("run-*/meta.json")]
    return sorted(
        saved + [prior_entry()] + ([sealed_entry()] if (CASE / "annual.json").is_file() else []),
        key=lambda item: (item["as_of"], item.get("saved_at", "")),
        reverse=True,
    )


def persist(annual, original):
    from datetime import UTC, datetime

    run_id = "run-" + uuid4().hex
    meta = {**entry(run_id, annual), "saved_at": datetime.now(UTC).isoformat()}
    root = store()
    root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=root) as temp:
        stage = Path(temp) / "run"
        stage.mkdir()
        for name, value in (("meta", meta), ("annual", annual)):
            (stage / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        if original.startswith(b"%PDF-"):
            (stage / "original.pdf").write_bytes(original)
        stage.rename(root / run_id)
    return run_id


def directory(run_id):
    if not re.fullmatch(r"run-[0-9a-f]{32}", run_id) or not (store() / run_id / "meta.json").is_file():
        raise KeyError(run_id)
    return store() / run_id


def bundle(run_id, cutoff=None):
    if run_id == PRIOR_ID:
        meta = prior_entry()
        if cutoff and cutoff != meta["as_of"]:
            raise KeyError(cutoff)
        annual = read(PUBLIC / "2024-25.json")
        return {
            "meta": meta,
            "annual": annual,
            "cutoff": meta["as_of"],
            "original": annual["sources"]["annual"]["source"],
        }
    if run_id != CASE_ID:
        folder = directory(run_id)
        meta = saved_meta(folder)
        if cutoff and cutoff not in meta["dates"]:
            raise KeyError(cutoff)
        pdf = folder / "original.pdf"
        return {
            "meta": meta,
            "cutoff": meta["as_of"],
            "annual": read(folder / "annual.json"),
            "original": f"/workflows/annual-report/library/{run_id}/original" if pdf.is_file() else None,
        }
    meta = sealed_entry()
    day = cutoff or meta["as_of"]
    if day not in DAYS or not (CASE / "annual.json").is_file():
        raise KeyError(day)
    annual = read(CASE / "annual.json")
    if annual["sources"]["annual"]["sha256"] != meta["sha256"]:
        raise ValueError("Case document fingerprint mismatch")
    tracking = read(CASE / "fresh-tracking" / f"{day}.json")
    replay = read(CASE / "replay" / f"{day}.json") if day in DAYS[1:] else None
    # Only primary annual disclosures in this baseline. Synthesis and the later review run
    # belong to the latest cutoff; the fresh tracking corpus has its own dated manifest.
    docs = [n for n in tracking["graph"]["nodes"] if n["kind"] == "Document"]
    if any(n["published"] > day for n in docs) or (
        replay and any(e["published"] > day for e in replay["evidence"].values())
    ):
        raise ValueError("Snapshot contains a later publication")
    latest = day == meta["as_of"]
    if not latest:
        annual = {
            **annual,
            "findings": [],
            "fact_reviews": [],
            "supply_chain_edges": [],
            "warnings": [],
            "unknown_topics": [],
            "as_of": day,
        }
    # Some replay snapshots emit only changed graph nodes. Resolve eligible hashes
    # from this and earlier snapshots; never consult a later manifest.
    originals = {}
    for previous in DAYS:
        if previous > day:
            break
        snapshot = tracking if previous == day else read(CASE / "fresh-tracking" / f"{previous}.json")
        for node in snapshot["graph"]["nodes"]:
            if (
                node["kind"] == "Document"
                and node["published"] <= day
                and node["digest"] in tracking["eligible_digests"]
            ):
                originals[node["digest"]] = node
    tracking["originals"] = list(originals.values())
    if latest:
        tracking["search_trace"] = read(CASE / "fresh-tracking/discovery.json")
    product = read(CASE / "product-audit.json") if latest else None
    if product and product["sha256"] != meta["sha256"]:
        raise ValueError("Product audit fingerprint mismatch")
    # Row labels are document-scoped; never match another issuer by a translated name.
    segment_keys = {
        "Zucker": "Segment/Sugar",
        "Spezialitäten": "Segment/Special products",
        "CropEnergies": "Segment/CropEnergies",
        "Stärke": "Segment/Starch",
        "Frucht": "Segment/Fruit",
    }
    admitted = {
        e["object"]
        for e in (replay or {}).get("edges", [])
        if e["relation"] == "HAS_SEGMENT"
        and e["provenance"] == "annual_report_disclosure"
        and replay["evidence"][e["evidence"]]["sha256"] == meta["sha256"]
    }
    return {
        "segment_nodes": {k: v for k, v in segment_keys.items() if v in admitted},
        "meta": meta,
        "cutoff": day,
        "annual": annual,
        "original": CASE_URL,
        "fresh": tracking,
        "reviewed": replay,
        "product": {"edges": product["edges"], "note": product["note"], "methods": product["methods"]}
        if product
        else None,
        "narrative": (CASE / "report.md").read_text() if latest else None,
        "annual_review_available": latest,
    }
