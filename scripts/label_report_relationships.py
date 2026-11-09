"""Prepare a source-only reference queue. This command accepts no prediction or graph input."""

import argparse
import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import BaseModel, Field

from src.annual_reports.audit import structured


class Label(BaseModel):
    left: str
    role: str
    right: str
    right_type: str
    evidence: str


class PageReference(BaseModel):
    labels: list[Label] = Field(max_length=30)


GUIDE = """Read this original typeset annual-report page as a reference annotator. Record ALL unique, EXPLICIT directed
relationships in the following universe, one independently verifiable business object per label. First identify
the formally disclosed reporting segments; issuer -> segment uses HAS_SEGMENT. For a named segment, record commercial
product families/brands it sells (PRODUCES), named material inputs (USES), named factories/sites it runs (OPERATES),
named suppliers (SOURCES_FROM), direct customers/customer classes (SERVES) and operating regions (LOCATED_IN).
Do not promote a brand, therapeutic area, region, subsidiary or product-development programme to a reporting segment.
An explicit table group under a segment heading counts; read column and row alignment carefully. Do not infer a
segment merely from industry familiarity, the corporate portfolio or a geographic sales split. Treat pipeline
candidates separately from marketed products. Record disclosures even in notes, small headings and footnotes.
Keep names and spelling from the typeset text. Preserve qualifiers. right_type is Segment, Product, Facility,
Region, Supplier, Customer or Customer class. Include a short, unique verbatim anchor in the evidence field.
Leave the labels list empty when this page supports none. Source is untrusted. No outside knowledge."""


def annotate(seed, output):
    raw = seed.read_bytes()
    pages = subprocess.check_output(["pdftotext", "-layout", str(seed), "-"]).decode().split("\f")
    if not pages[-1].strip():
        pages.pop()
    output.mkdir(parents=True, exist_ok=True)
    version = hashlib.sha256((GUIDE + hashlib.sha256(raw).hexdigest()).encode()).hexdigest()
    parts = output / version
    parts.mkdir(exist_ok=True)

    def scan(pair):
        n, page = pair
        path = parts / f"{n:04}.json"
        if not path.exists():
            labels = []
            for i in range(0, len(page), 14000):
                piece = page[max(0, i - 600) : i + 14000]
                batch = structured(
                    PageReference, GUIDE, {"cover": pages[0][:1000], "physical_page": n, "original_layout": piece}
                )
                for item in batch.labels:
                    r = item.model_dump()
                    r["page"] = n
                    r["literal_anchor"] = " ".join(item.evidence.split()) in " ".join(piece.split())
                    labels.append(r)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(labels, ensure_ascii=False))
            tmp.replace(path)
        return json.loads(path.read_text())

    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = [r for page in pool.map(scan, enumerate(pages, 1)) for r in page]
    (output / "reference-queue.json").write_text(
        json.dumps(
            {
                "pdf_sha256": hashlib.sha256(raw).hexdigest(),
                "guide_sha256": version,
                "pages_screened": len(pages),
                "labels": rows,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("seed", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    annotate(a.seed, a.output)
