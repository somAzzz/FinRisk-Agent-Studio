"""Measure three representations using a sealed reference, sequential local requests and board sampling."""

import argparse
import hashlib
import json
import subprocess
import threading
import time
from functools import partial
from pathlib import Path

from scripts.score_exposure_coverage import compare
from src.ai.model_factory import resolve_agent_model_config
from src.annual_reports import coverage, documents


def memory():
    lines = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.used",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    ).splitlines()
    return {name: int(value) for name, value in (line.rsplit(", ", 1) for line in lines)}


def measure(operation):
    baseline = memory()
    peak = dict(baseline)
    stop = threading.Event()

    def poll():
        while not stop.wait(0.2):
            for gpu, used in memory().items():
                peak[gpu] = max(peak[gpu], used)

    thread = threading.Thread(target=poll)
    thread.start()
    try:
        start = time.monotonic()
        result = operation()
        elapsed = time.monotonic() - start
    finally:
        stop.set()
        thread.join()
    return result, {"seconds": elapsed, "baseline_MiB": baseline, "peak_MiB": peak}


def page_text(pdf, page, mode):
    if mode == "ocr":
        return documents.ocr_page(pdf, page)
    return subprocess.check_output(
        ["pdftotext", "-f", str(page), "-l", str(page), "-" + mode, "-enc", "UTF-8", str(pdf), "-"], text=True
    ).strip()


def products(edges):
    return [r for r in edges if r["relation"] == "PRODUCES" and r["object_kind"] == "Product"]


def run(pdf, reference, out, pages, note_page, cover):
    gold = json.loads(reference.read_text())
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if gold["seed_sha256"] != digest:
        raise ValueError("Report does not match the sealed reference")
    note = page_text(pdf, note_page, "raw")
    config = resolve_agent_model_config()
    record = {
        "model": config.model,
        "provider": config.provider,
        "temperature": 0,
        "seed_sha256": digest,
        "reference_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
        "extractor_sha256": hashlib.sha256(Path(coverage.__file__).read_bytes()).hexdigest(),
        "arms": {},
    }
    for mode in ("raw", "layout", "ocr"):
        arm = {"pages": {}}
        record["arms"][mode] = arm
        for n in pages:
            text, parsing = measure(partial(page_text, pdf, n, mode))
            rows, inference = measure(partial(coverage.page_edges, cover, n, text, segment_note={str(note_page): note}))
            arm["pages"][n] = {
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "parsing": parsing,
                "inference": inference,
                "edges": rows,
            }
            print(mode, n, len(rows), flush=True)
            out.write_text(json.dumps(record, indent=2, ensure_ascii=False))
        for n in pages:
            arm["pages"][n]["scores"] = compare(
                {"edges": [r for r in products(gold["edges"]) if n in r["evidence_pages"]]},
                {"sample_pages": [n], "edges": products(arm["pages"][n]["edges"])},
            )
        arm["scores"] = compare(
            {"edges": [r for r in products(gold["edges"]) if set(pages).intersection(r["evidence_pages"])]},
            {"sample_pages": pages, "edges": products([e for p in arm["pages"].values() for e in p["edges"]])},
        )
        out.write_text(json.dumps(record, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("pdf", "reference", "out"):
        p.add_argument(name, type=Path)
    p.add_argument("--pages", type=int, nargs="+", default=[25, 89, 90])
    p.add_argument("--note-page", type=int, default=89)
    p.add_argument("--cover", default="Novo Nordisk Annual Report 2025")
    run(**vars(p.parse_args()))
