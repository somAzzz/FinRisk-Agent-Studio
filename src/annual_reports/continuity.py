"""Point-in-time company research read model. No writeback to historical filings or review verdicts."""

from collections import Counter
from datetime import date
from itertools import pairwise

from src.annual_reports import library


def eligible(entries, day):
    return [
        e
        for e in entries
        if e.get("issuer", {}).get("status") == "confirmed"
        and e.get("published")
        and e["published"] <= day
        and any(d <= day for d in e["dates"])
    ]


def resolve_record(entries, ticker, day, explicit=None, *, as_of=None):
    """Bind explicit issuer scope, or bracket a qualified symbol with consistent dated disclosures."""
    anchors = [
        (e["issuer"]["company_id"], listing, e["published"])
        for e in eligible(entries, as_of or day)
        for listing in e["issuer"]["listings"]
    ]
    symbol = ticker.strip().upper()
    if explicit:
        return (
            explicit
            if any(
                k == explicit and d <= day and symbol in (listing["qualified"], listing["symbol"])
                for k, listing, d in anchors
            )
            else None
        )
    observations = [(k, d, listing["isin"]) for k, listing, d in anchors if symbol == listing["qualified"]]
    owners = {(k, isin) for k, _, isin in observations}
    if len(owners) == 1 and min(d for _, d, _ in observations) <= day <= max(d for _, d, _ in observations):
        return observations[0][0]
    return None


def checked_tables(b):
    return [
        t
        for t in b["annual"]["reconciliations"]
        if t["status"] == "passed" and t["metric"] != "operating_result_bridge" and len(t["periods"]) == 2
    ]


def fiscal_label(meta):
    end = meta.get("period_end")
    if not end:
        return None
    return str(int(end[:4]) - 1) + "/" + end[2:4]


def compare(old, new):
    rows = []
    for a in checked_tables(old):
        matching = [t for t in checked_tables(new) if (t["metric"], t["unit"]) == (a["metric"], a["unit"])]
        if len(matching) != 1 or a["periods"][0] != fiscal_label(old["meta"]):
            continue
        b = matching[0]
        if b["periods"] != [fiscal_label(new["meta"]), a["periods"][0]]:
            continue
        left = {r["label"]: r for r in a["rows"]}
        right = {r["label"]: r for r in b["rows"]}
        if len(left) != len(a["rows"]) or len(right) != len(b["rows"]):
            continue
        for key in dict.fromkeys([*left, *right]):
            first = left.get(key)
            second = right.get(key)
            prior = first["values"][0] if first else None
            current = second["values"][0] if second else None
            comparative = second["values"][1] if second else None
            ok = prior is not None and current is not None and prior == comparative
            rows.append(
                {
                    "segment": key,
                    "metric": a["metric"],
                    "unit": a["unit"],
                    "prior": prior,
                    "current": current,
                    "comparative": comparative,
                    "change": current - prior if ok else None,
                    "status": "comparable" if ok else "basis_unknown",
                    "pages": [a["physical_page"], b["physical_page"]],
                    "quotes": [first and first["quote"], second and second["quote"]],
                }
            )
    return rows


def question_trail(snapshot, task, published, day):
    """Traverse saved graph IDs; a CHECKED passage is a search result, not a direct answer."""
    from collections import defaultdict

    g = snapshot["graph"]
    nodes = {n["id"]: n for n in g["nodes"]}
    edges = defaultdict(set)
    for left, relation, right in g["edges"]:
        edges[left, relation].add(right)
    result = {}
    for tid, t in nodes.items():
        if t["kind"] != "Task" or (t.get("seed_id"), t.get("question"), t.get("scope")) != (
            task["seed_id"],
            task["question"],
            task["scope"],
        ):
            continue
        for cid in sorted(edges[tid, "EXAMINES"]):
            for vid in sorted(edges[cid, "JUDGED_BY"]):
                for eid in sorted(edges[vid, "CHECKED"] | edges[cid, "CITES"]):
                    e = nodes[eid]
                    docs = [
                        nodes[k]
                        for k in edges[eid, "FROM"]
                        if nodes[k]["kind"] == "Document"
                        and nodes[k]["digest"] == e["digest"]
                        and nodes[k]["published"] == e["published"]
                    ]
                    if (
                        e["kind"] != "Evidence"
                        or len(docs) != 1
                        or not published < e["published"] <= day
                        or e["digest"] not in snapshot["eligible_digests"]
                    ):
                        continue
                    cited = eid in edges[cid, "CITES"]
                    verdict = nodes[vid]["status"] if cited else "checked_only"
                    source = docs[0]["source"]
                    result[e["digest"], e["page"], verdict] = {
                        "published": e["published"],
                        "page": e["page"],
                        "digest": e["digest"],
                        "url": source if source.startswith("https://") else None,
                        "verdict": verdict,
                        "quote": nodes[vid]["quote"] if cited and eid in edges[vid, "DECIDED_ON"] else e["text"][:280],
                        "reviewed": day,
                        "path": [tid, cid, vid, eid, docs[0]["id"]],
                    }
    return result


def workspace(key, day, entries=None):
    candidates = eligible(library.entries() if entries is None else entries, day)
    # Prefer the sealed replay over a second analysis of the very same PDF. Do not suppress
    # a distinct restated PDF for the same period: both must remain visible for review.
    candidates.sort(key=lambda e: len(e["lanes"]), reverse=True)
    docs = {}
    for e in candidates:
        if e["issuer"]["company_id"] == key and e["sha256"] not in docs:
            docs[e["sha256"]] = e
    if not docs:
        raise KeyError(key)
    bundles = [
        library.bundle(e["id"], max(d for d in e["dates"] if d <= day))
        for e in sorted(docs.values(), key=lambda x: (x.get("period_end") or "", x["published"]))
    ]
    periods = Counter(b["meta"].get("period_end") for b in bundles)
    filings = [
        {
            **{k: b["meta"][k] for k in ("id", "issuer", "company", "period", "period_end", "published", "sha256")},
            "original": b["original"],
            "cutoff": b["cutoff"],
        }
        for b in bundles
    ]
    comparisons = []
    questions = []
    for a, b in pairwise(bundles):
        rows = compare(a, b) if all(periods[x["meta"].get("period_end")] == 1 for x in (a, b)) else []
        comparisons.append({"from": a["meta"]["id"], "to": b["meta"]["id"], "rows": rows})
    for i, b in enumerate(bundles):
        origin = b["meta"]
        for q in b["annual"].get("outlook_questions", []):
            matches = []
            for later in bundles[i + 1 :]:
                if (
                    later["meta"]["published"] <= origin["published"]
                    or periods[later["meta"].get("period_end")] != 1
                    or fiscal_label(later["meta"]) != q["period"]
                    or periods[origin.get("period_end")] != 1
                ):
                    continue
                for t in checked_tables(later):
                    if (t["periods"][0], t["metric"], t["unit"]) != (q["period"], q["metric"], q["unit"]):
                        continue
                    matches.extend(
                        {
                            "value": r["values"][0],
                            "page": t["physical_page"],
                            "report": later["meta"]["id"],
                            "quote": r["quote"],
                            "published": later["meta"]["published"],
                        }
                        for r in t["rows"]
                        if r["label"] == q["segment"]
                    )
            hit = matches[0] if len(matches) == 1 else None
            questions.append(
                {
                    **q,
                    "origin": origin["id"],
                    "kind": "disclosed_outlook",
                    "answer": hit,
                    "status": ("within_range" if q["range"][0] <= hit["value"] <= q["range"][1] else "outside_range")
                    if hit
                    else "unknown",
                    "fulfillment": "unknown",
                }
            )
        fresh = b.get("fresh") or {}
        for t in fresh.get("tasks", []):
            # Follow persisted task -> scoped audit -> cited passage, including rejected citations.
            # A rejected proposal is a review trail, never proof of fulfilment.
            trail = {}
            for d in sorted(x for x in origin["dates"] if x <= b["cutoff"]):
                f = (b if d == b["cutoff"] else library.bundle(origin["id"], d)).get("fresh") or {}
                if not any(k["id"] == t["id"] for k in f.get("tasks", [])):
                    continue
                for sig, proof in question_trail(f, t, origin["published"], d).items():
                    trail.setdefault(sig, proof)
            questions.append(
                {
                    "id": t["id"],
                    "origin": origin["id"],
                    "kind": "existing_task",
                    "question": t["question"],
                    "status": t["state"],
                    "fulfillment": t["fulfillment"],
                    "required": t["direct_evidence_needed"],
                    "cutoff": b["cutoff"],
                    "trail": sorted(
                        trail.values(), key=lambda e: (e["verdict"] == "checked_only", e["published"], e["page"])
                    ),
                }
            )
    return {
        "id": key,
        "name": filings[-1]["company"],
        "as_of": day,
        "filings": filings,
        "comparisons": comparisons,
        "questions": questions,
        "briefs": [],
        "journal": [],
    }


def binding_for_write(ticker, company_id):
    if not company_id:
        return
    if resolve_record(library.entries(), ticker, date.today().isoformat(), company_id) != company_id:
        raise ValueError("The ticker is not a disclosed listing of the selected company.")
