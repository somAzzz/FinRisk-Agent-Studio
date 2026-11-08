"""Run a frozen, paired eight-page / all-page blind using one PDF and non-US sources."""

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from src.annual_reports import coverage, product_evidence, segments
from src.annual_reports.audit import audit_segment_edges, key
from src.annual_reports.blind import investigate, project, report_md, routes
from src.annual_reports.documents import download, extract
from src.annual_reports.non_us import discover_non_us
from src.annual_reports.segments import product_edges, segment_note
from src.graph.client import Neo4jClient


def save(path, obj):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def run(source, out, cutoff):
    raw = download(source)[0] if source.startswith(("http://", "https://")) else Path(source).read_bytes()
    doc = extract(raw, source)
    cover = doc.pages[0].text[:1800]
    selected = coverage.eight_pages(doc)
    note = segment_note(doc)
    rules = [hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (coverage, segments, product_evidence)]
    work = out / "page-decisions" / key(rules, doc.sha256, note, "commercial-witness-v2", cover)
    work.mkdir(parents=True, exist_ok=True)

    def read_page(p):
        dest = work / f"{p.number:04}-{key(p.text, p.relationship_text)}.json"
        if not dest.exists():
            rows = coverage.page_edges(
                cover,
                p.number,
                p.relationship_text or p.text,
                segment_note={k: v for k, v in note.items() if k != "sales_brands"},
            )
            for row in rows:
                if row["relation"] == "PRODUCES" and row["object_kind"] == "Product":
                    row.update(status="unknown", review="Requires a verified product row and commercial disclosure.")
            save(dest, audit_segment_edges(rows, note) + product_edges(p, note))
        return json.loads(dest.read_text())

    for arm, nums in [("eight", selected), ("all", [p.number for p in doc.pages])]:
        dest = out / arm
        folder = dest / "originals"
        folder.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            pages = list(pool.map(read_page, (doc.pages[n - 1] for n in nums)))
        edges = coverage.collapse([e for page in pages for e in page])
        companies = [e["subject"] for e in edges if e["relation"] == "HAS_SEGMENT" and e["status"] == "supported"]
        issuer = (
            max(dict.fromkeys(companies), key=companies.count) if companies else (cover.splitlines() or ["unknown"])[0]
        )
        tasks, trace, events, unknown = investigate(issuer, routes(edges), cutoff, folder, discovery=discover_non_us)
        r = {
            "issuer": issuer,
            "as_of": str(cutoff),
            "seed_sha256": doc.sha256,
            "page_count": len(doc.pages),
            "sample_pages": nums,
            "segment_note_page": note["page"],
            "edges": edges,
            "tasks": tasks,
            "search": trace,
            "events": events,
            "unresolved_external": unknown,
        }
        with Neo4jClient() as graph:
            r["graph"] = project(graph, r)
        save(dest / "result.json", r)
        (dest / "report.md").write_text(report_md(r))
        print(f"{arm} snapshot sealed", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    run(args.source, args.output, date.today())
