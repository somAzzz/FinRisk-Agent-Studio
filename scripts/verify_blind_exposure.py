"""Verify a completed single-report run against its frozen originals and derived graph, offline."""

import argparse
import json
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup

from src.annual_reports.audit import key
from src.annual_reports.blind import entity, plain, routes
from src.annual_reports.blind_sources import digest, register_pages
from src.annual_reports.documents import extract, native_pages


def verify(seed, originals, report):
    raw = seed.read_bytes()
    if digest(raw) != report["seed_sha256"]:
        raise ValueError("Wrong annual report")
    pages = {p.number: (plain(p.text), plain(p.relationship_text)) for p in extract(raw, str(seed)).pages}
    verified = [r for r in report["edges"] if r["status"] == "supported"]
    for r in verified:
        if not plain(r["quote"]) or not any(plain(r["quote"]) in text for text in pages.get(r["page"], ())):
            raise ValueError("Unknown annual-report citation")
        if (proof := r.get("segment_evidence")) and (
            proof["sha256"] != report["seed_sha256"]
            or not proof["quote"]
            or not any(plain(proof["quote"]) in text for text in pages.get(proof["page"], ()))
        ):
            raise ValueError("Unverified formal segment note")
    graph = routes(report["edges"])
    observed = set()
    cutoff = date.fromisoformat(report["as_of"])
    for event in report["events"]:
        files = list(originals.glob(event["digest"] + ".*"))
        if len(files) != 1 or digest(data := files[0].read_bytes()) != event["digest"]:
            raise ValueError("Wrong external original")
        if files[0].suffix == ".pdf":
            pages_text = [p.text for p in native_pages(data)]
            # Numbered PDF path and article ID originate in the public registry response.
            identifier = event["source"].rsplit("/", 1)[-1].removesuffix(".pdf")
            text = register_pages(pages_text, identifier)[event["page"] - 1]
        else:
            text = BeautifulSoup(data, "html.parser").get_text(" ", strip=True)
        if event["fact"] != event["quote"]:
            raise ValueError("Published observation extends beyond decisive span")
        if not plain(event["quote"]) or plain(event["quote"]) not in plain(text):
            raise ValueError("Unknown external citation")
        if date.fromisoformat(event["published"]) > cutoff:
            raise ValueError("Future external evidence")
        segments = {r["subject"] for r in graph.get(event["target"], [])}
        if segments != set(event["segments"]) or not segments:
            raise ValueError("No verified product-to-segment path")
        eid = entity("Event", key(event["digest"], event["target"], event["fact"]))
        observed.update((eid, event["target"], entity("Segment", name)) for name in segments)
        if any(event[k] != "unknown" for k in ("realized_impact", "attributable_amount", "fulfillment")):
            raise ValueError("Financial attribution or fulfillment without independent direct evidence")
    if "graph" in report:
        paths = {(p["event"], p["target"], p["segment"]) for p in report["graph"]["paths"]}
        if observed != paths:
            raise ValueError("Neo4j path mismatch")
    return {
        "seed_sha256": report["seed_sha256"],
        "issuer_edges_checked": len(verified),
        "unknown_edges": len(report["edges"]) - len(verified),
        "primary_event_citations_checked": len(report["events"]),
        "distinct_verified_paths": len(observed),
        "unsupported_financial_amounts": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("seed", type=Path)
    parser.add_argument("run_directory", type=Path)
    args = parser.parse_args()
    report = json.loads((args.run_directory / "result.json").read_text())
    print(json.dumps(verify(args.seed, args.run_directory / "originals", report), indent=2))
