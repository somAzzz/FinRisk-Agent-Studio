"""Run the full-document product fact audit with the report as its only issuer-specific input."""

import argparse
import json
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.annual_reports import segments
from src.annual_reports.coverage import collapse
from src.annual_reports.documents import download, extract


def run(source, out):
    started = time.monotonic()
    data = download(source)[0] if source.startswith(("https://", "http://")) else Path(source).read_bytes()
    doc = extract(data, source)
    note = segments.segment_note(doc)
    print("note", note["page"], list(note["definitions"]), flush=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = []
        for page, rows in zip(doc.pages, pool.map(lambda p: segments.product_edges(p, note), doc.pages), strict=True):
            records.append(
                {"page": page.number, "method": page.relationship_method, "ocr_reason": page.ocr_reason, "edges": rows}
            )
            if page.number % 30 == 0:
                print("finished", page.number, "/", len(doc.pages), flush=True)
    result = {
        "sha256": doc.sha256,
        "pages": records,
        "note": note,
        "elapsed_s": time.monotonic() - started,
        "methods": dict(Counter(r["method"] for r in records)),
        "warnings": doc.warnings,
        "edges": collapse([r for page in records for r in page["edges"]]),
    }
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source")
    p.add_argument("out", type=Path)
    run(**vars(p.parse_args()))
