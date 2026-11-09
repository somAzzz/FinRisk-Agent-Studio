"""Evaluate two report-only runs against the sealed recall protocol and replay their source spans."""

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from scripts.score_exposure_coverage import compare

REPORTS = Path(__file__).resolve().parents[1] / "docs/reports"


def read(path):
    return json.loads(path.read_text())


def verify(tag, pdf, prediction, reference, baseline, min_tp, *, prior_counts=None):
    run, gold, prior = map(read, (prediction, reference, baseline))
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if not digest == run["sha256"] == prior["sha256"] == gold["seed_sha256"]:
        raise ValueError("Report identity mismatch")
    layers = [
        [
            " ".join(p.split())
            for p in subprocess.check_output(["pdftotext", mode, str(pdf), "-"], text=True).split("\f")[:-1]
        ]
        for mode in ("-raw", "-layout")
    ]
    pages = list(range(1, len(layers[0]) + 1))
    assert pages == [p["page"] for p in run["pages"]] == [p["page"] for p in prior["pages"]]
    gold["edges"] = [e for e in gold["edges"] if e["relation"] == "PRODUCES" and e["object_kind"] == "Product"]

    def scores(r):
        return compare(gold, {"sample_pages": pages, "edges": r["edges"]})

    old, new = scores(prior), scores(run)
    assert (old["TP"], old["FN"], old["FP"]) == (prior_counts or ((28, 48, 0) if tag == "novo" else (5, 9, 0)))
    preserved = set(map(tuple, old["tp"])).issubset(set(map(tuple, new["tp"])))
    checked = 0
    ocr = {}
    for p in run["pages"]:
        for row in p["edges"]:
            if row["status"] != "supported":
                continue
            assert row["page"] == p["page"]
            definition = row["segment_evidence"]
            assert definition["sha256"] == digest and definition["name"] == row["subject"]
            spans = [(p["page"], row[k]) for k in ("quote", "allocation_quote", "commercial_quote")]
            spans.extend((p["page"], text) for text in row.get("source_spans", []))
            spans.extend((p["page"], text) for text in row.get("family_presentations", []))
            for proof in [definition, row.get("alias_evidence"), *row.get("cross_page_evidence", [])]:
                if proof:
                    spans.append((proof["page"], proof["quote"]))
                    if "allocation_quote" in proof:
                        assert proof["sha256"] == digest and proof["segment"] == row["subject"]
                        spans.append((proof["page"], proof["allocation_quote"]))
            for n, text in spans:
                needle = " ".join(text.split())
                assert needle
                if any(needle in layer[n - 1] for layer in layers):
                    continue
                assert run["pages"][n - 1]["method"] == "ocr", (n, text)
                if n not in ocr:
                    from src.annual_reports.documents import ocr_page

                    ocr[n] = " ".join(ocr_page(pdf, n).split())
                assert needle in ocr[n], (n, text)
            checked += 1
    controls = ["Kyinsu", "CagriSema"] if tag == "novo" else ["e-Volksbus 22L", "NEXT ERA", "Super 13", "TGM", "eTGS"]
    controls = {
        n: sorted(
            {r["status"] for r in run["edges"] if re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", r["object"], re.I)}
        )
        or ["not proposed"]
        for n in controls
    }
    bad_segments = {
        "TRATON Operations",
        "Reconciliation",
        "RARE DISEASE PRODUCTION",
        "US Operations",
        "International Operations",
    }
    assert not (bad_segments & {r["subject"] for r in run["edges"] if r["status"] == "supported"})
    assert all("supported" not in states for states in controls.values())
    return {
        "previous": old,
        "current": new,
        "all_prior_matches_retained": preserved,
        "source_rows_verified": checked,
        "ocr_readback_pages": sorted(ocr),
        "negative_controls": controls,
        "page_count": len(pages),
        "elapsed_s": run["elapsed_s"],
        "passed": preserved and new["FP"] == 0 and new["TP"] >= min_tp,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("novo_pdf", type=Path)
    parser.add_argument("traton_pdf", type=Path)
    parser.add_argument("output", type=Path)
    a = parser.parse_args()
    base = REPORTS / "segment-regression"
    scores = {}
    for tag, ref, pdf, floor in [
        ("novo", REPORTS / "non-us-holdout/reference.json", a.novo_pdf, 36),
        ("traton", base / "traton-full-reference.json", a.traton_pdf, 7),
    ]:
        scores[tag] = verify(tag, pdf, a.output / f"{tag}-verified.json", ref, base / f"{tag}-final.json", floor)
    (a.output / "verification.json").write_text(json.dumps(scores, indent=2, ensure_ascii=False) + "\n")
    print({k: (r["current"]["TP"], r["current"]["FP"], r["passed"]) for k, r in scores.items()})
    if not all(r["passed"] for r in scores.values()):
        raise SystemExit(1)
