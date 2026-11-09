"""Rebuild the public case from BOTH full PDFs. No network, model or later-year inputs during old-year extraction."""

import argparse
import hashlib
import json
from pathlib import Path

from fastapi.encoders import jsonable_encoder

from src.annual_reports.company_identity import extract_issuer, range_questions
from src.annual_reports.documents import Document, native_pages
from src.annual_reports.financials import comparable_rows, identity, reconciliation
from src.annual_reports.library import CASE_URL, ROOT

OUT = ROOT / "docs/reports/company-continuity"
OLD_URL = "https://www.suedzuckergroup.com/sites/default/files/2025-05/Suedzucker_Geschaeftsbericht_2024%E2%80%9325.pdf"


def parse(path, url):
    data = path.read_bytes()
    doc = Document(url, hashlib.sha256(data).hexdigest(), native_pages(data))
    meta = identity(doc)
    meta["issuer"] = extract_issuer(doc, meta["cover"])
    return jsonable_encoder(
        {
            "identity": meta,
            "sources": {
                "annual": {
                    "source": url,
                    "sha256": doc.sha256,
                    "page_count": len(doc.pages),
                    "published_at": meta["published_at"],
                    "selected_pages": [],
                    "ocr_pages": [],
                }
            },
            "as_of": meta["published_at"],
            "status": "needs_review",
            "outlook_questions": range_questions(doc, meta),
            "reconciliations": reconciliation(doc),
            "financial_rows": comparable_rows(doc),
            "warnings": ["Native-text financial and identity extraction; no narrative or external review."],
            **{
                k: []
                for k in (
                    "findings",
                    "fact_reviews",
                    "supply_chain_edges",
                    "chart_rows",
                    "external_events",
                    "market_observations",
                    "scenarios",
                    "plant_decisions",
                    "unknown_topics",
                    "decision_data_gaps",
                    "inline_xbrl_facts",
                )
            },
        }
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(__doc__)
    ap.add_argument("older", type=Path)
    ap.add_argument("newer", type=Path)
    args = ap.parse_args()
    # These checks pin the public acceptance inputs, not the production resolution rules.
    for path, digest in [
        (args.older, "5f948070a72ffaa11b8024a91a6447e1a59fff0d5b8e1b7c24fa3de4c05e64fe"),
        (args.newer, "597193d6e3ff8ba389272bdfd597554a278b4ad9cc1137d87d8d5232d90a791e"),
    ]:
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            ap.error(f"PDF does not match the frozen acceptance input: {path.name}")
    for key, path, url in [("2024-25", args.older, OLD_URL), ("2025-26", args.newer, CASE_URL)]:
        annual = parse(path, url)
        if key == "2025-26":
            annual = {k: annual[k] for k in ("identity", "sources", "outlook_questions")}
        (OUT / (key + ".json")).write_text(json.dumps(annual, ensure_ascii=False, indent=2) + "\n")
