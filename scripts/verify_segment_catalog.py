"""Evaluate sealed full-report predictions; never imported by the inference pipeline."""

import argparse
import json
import subprocess
from pathlib import Path

from scripts.score_exposure_coverage import token
from scripts.verify_segment_recall import REPORTS, read, verify
from src.annual_reports.blind import routes

# Evaluation assertions only. Do not offer these names or page coordinates to inference.
TARGETS = {
    "single dose device": ("named equipment in commercially allocated host entry", 90),
    "pre filled delivery systems": ("catalog family with independently allocated member", 90),
    "oral antidiabetic agents": ("treatment class within disclosed condition", 89),
    "novonorm": ("treatment class within disclosed condition", 89),
}


def verify_catalog(novo, traton, folder):
    results = {}
    for tag, pdf, ref, counts, floor in (
        ("novo", novo, REPORTS / "non-us-holdout/reference.json", (54, 22, 0), 58),
        ("traton", traton, REPORTS / "segment-regression/traton-full-reference.json", (14, 0, 0), 14),
    ):
        runfile = folder / f"{tag}-verified.json"
        r = verify(tag, pdf, runfile, ref, REPORTS / "segment-recall" / runfile.name, floor, prior_counts=counts)
        assert r["passed"]
        run, old, new = read(runfile), r["previous"], r["current"]
        before, after = set(map(tuple, old["tp"])), set(map(tuple, new["tp"]))
        gained = {t[-1] for t in after - before}
        assert gained == (set(TARGETS) if tag == "novo" else set())
        assert new["TP"] == floor and new["FP"] == 0 and before <= after
        if tag == "novo":
            details = {}
            for term, (rule, support_page) in TARGETS.items():
                witness = next(
                    e
                    for e in run["pages"][24]["edges"]
                    if token(e["object"]) == term and e.get("evidence_rule") == rule and e["status"] == "supported"
                )
                assert witness["segment_evidence"]["page"] == 89
                assert witness["cross_page_evidence"] and {p["page"] for p in witness["cross_page_evidence"]} == {
                    support_page
                }
                assert witness["source_spans"]
                details[term] = witness
            r["gained_evidence"] = details
            expected = {f["edge"][-1] for f in old["fn"]} - set(TARGETS)
            assert expected == {f["edge"][-1] for f in new["fn"]} and len(expected) == 18
            layout = subprocess.check_output(["pdftotext", "-layout", "-f", "25", "-l", "25", str(pdf), "-"], text=True)
            r["unknown_mentions"] = []
            for name in sorted(expected):
                mentions = [e for e in run["edges"] if token(e["object"]) == name]
                assert mentions and all(e["status"] == "unknown" for e in mentions)
                unbound = next(e for e in mentions if e["subject"] == "unknown" and e["page"] == 25)
                assert unbound["quote"] in layout and all(s in layout for s in unbound["source_spans"])
                r["unknown_mentions"].append(unbound)
            segment_nodes = [
                {
                    "status": "supported",
                    "subject_kind": "Company",
                    "relation": "HAS_SEGMENT",
                    "object_kind": "Segment",
                    "object": definition["name"],
                }
                for definition in run["note"]["definitions"].values()
            ]
            paths = routes(segment_nodes + run["edges"])
            reached = {token(k.split("/", 1)[1]) for k in paths}
            assert set(TARGETS) <= reached and not expected.intersection(reached)
            r["route_check"] = {
                "new_targets_reachable": len(set(TARGETS) & reached),
                "unknown_targets_reachable": len(expected & reached),
            }
        results[tag] = r
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("novo_pdf", "traton_pdf", "output"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    results = verify_catalog(args.novo_pdf, args.traton_pdf, args.output)
    (args.output / "verification.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n")
    print({k: (v["current"]["TP"], v["current"]["FP"], v["source_rows_verified"]) for k, v in results.items()})
