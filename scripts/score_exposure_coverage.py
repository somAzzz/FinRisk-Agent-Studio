"""Compare sealed typed triples to a separately authored, cited reference."""

import argparse
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path


def token(s):
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFC", s.casefold()).replace("®", "").replace("™", "")))


def endpoint(kind, name):
    n = token(name)
    if kind == "Company":
        n = re.sub(r" (a s|plc|ltd|inc|corporation)$", "", n)
    if kind == "Segment":
        n = re.sub(r" segment$", "", n)
    return n


def triple(row):
    return (
        row["subject_kind"],
        endpoint(row["subject_kind"], row["subject"]),
        row["relation"],
        row["object_kind"],
        endpoint(row["object_kind"], row["object"]),
    )


def compare(reference, run):
    gold = {triple(r): r for r in reference["edges"]}
    aliases = {(*k[:-1], endpoint(k[-2], a)): k for k, r in gold.items() for a in r.get("aliases", [])}

    def norm(r):
        k = triple(r)
        return aliases.get(k, k)

    supported = {norm(r) for r in run["edges"] if r["status"] == "supported"}
    attempted = {norm(r) for r in run["edges"]}
    pages = set(run["sample_pages"])
    tp = set(gold) & supported
    fp = supported - set(gold)
    fn = set(gold) - tp
    failures = []
    for k in sorted(fn):
        candidates = [r for r in run["edges"] if norm(r)[2:] == k[2:]]
        if k in attempted:
            cause = "correct candidate abstained"
        elif candidates:
            cause = "object proposed with different subject"
        elif not pages.intersection(gold[k]["evidence_pages"]):
            cause = "no annotated object-disclosure page selected"
        else:
            cause = "annotated object page selected; exact relation not proposed"
        failures.append({"edge": k, "cause": cause, "witness_pages": gold[k]["evidence_pages"]})
    return {
        "TP": len(tp),
        "FP": len(fp),
        "FN": len(fn),
        "gold": len(gold),
        "precision": len(tp) / len(supported) if supported else None,
        "recall": len(tp) / len(gold) if gold else None,
        "supported_raw": sum(r["status"] == "supported" for r in run["edges"]),
        "unknown_raw": sum(r["status"] == "unknown" for r in run["edges"]),
        "supported_unique": len(supported),
        "miss_categories": dict(Counter(f["cause"] for f in failures)),
        "tp": sorted(tp),
        "fp": sorted(fp),
        "fn": failures,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("runs", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    ref = json.loads(args.reference.read_text())
    result = {}
    for arm in ("eight", "all"):
        r = json.loads((args.runs / arm / "result.json").read_text())
        if r["seed_sha256"] != ref["seed_sha256"]:
            raise ValueError("Reference and prediction used different annual reports")
        result[arm] = compare(ref, r)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
