"""Publish only source-reviewed predictions. The reference never adds a missing prediction."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from scripts.score_exposure_coverage import triple
from src.annual_reports.blind import entity, plain, project
from src.annual_reports.blind_sources import digest
from src.graph.client import Neo4jClient


def verify_original(folder, sha, quote, url, cutoff):
    raw = (folder / (sha + ".json")).read_bytes()
    source = json.loads(raw)
    body = plain(BeautifulSoup(source["details"]["body"], "html.parser").get_text(" ", strip=True))
    if (
        digest(raw) != sha
        or not quote.strip()
        or plain(quote) not in body
        or urlsplit(url).hostname != "www.gov.uk"
        or source["base_path"] != urlsplit(url).path
        or str(source["first_published_at"])[:10] > cutoff
    ):
        raise ValueError("Independent original verification failed")


def publish(base, recent, ref, output):
    reference = {triple(e): e for e in ref["edges"]}
    with Neo4jClient() as graph:
        for arm in ("eight", "all"):
            d = base / arm
            raw = json.loads((d / "result.json").read_text())
            reviewed = {k: v for k, v in raw.items() if k != "graph"}
            reviewed["stage"] = "independently reviewed"
            reviewed["edges"] = []
            checked = set()
            not_supported = []
            for e in raw["edges"]:
                k = triple(e)
                if e["status"] != "supported" or k not in reference:
                    reviewed["edges"].append(
                        {**e, "status": "unknown", "review": "Unestablished under the independent reference"}
                    )
                    if e["status"] == "supported":
                        not_supported.append(
                            {
                                "a": entity(e["subject_kind"], e["subject"]),
                                "b": entity(e["object_kind"], e["object"]),
                                "role": e["relation"],
                            }
                        )
                elif k not in checked:
                    checked.add(k)
                    reviewed["edges"].append(
                        {**e, "subject": reference[k]["subject"], "object": reference[k]["object"]}
                    )
            events = []
            for e in raw["events"]:
                verify_original(d / "originals", e["digest"], e["fact"], e["source"], raw["as_of"])
                events.append({**e, "stage": "frozen discovery"})
            if arm == "all":
                for e in json.loads((recent / "result.json").read_text())["events"]:
                    verify_original(recent / "originals", e["source_sha256"], e["quote"], e["source"], raw["as_of"])
                    events.append(
                        {
                            "stage": "post-freeze discovery",
                            "fact": e["quote"],
                            "quote": e["quote"],
                            "target": e["target"],
                            "segments": sorted({p["segment"].split("/", 1)[1] for p in e["paths"]}),
                            "source": e["source"],
                            "published": e["published"],
                            "digest": e["source_sha256"],
                            "page": 1,
                            "fulfillment": "unknown",
                            "realized_impact": "unknown",
                            "attributable_amount": "unknown",
                        }
                    )
            for e in events:
                k = triple(
                    {
                        "subject_kind": "Segment",
                        "subject": e["segments"][0],
                        "relation": "PRODUCES",
                        "object_kind": "Product",
                        "object": e["target"].split("/", 1)[1],
                    }
                )
                if len(e["segments"]) != 1 or k not in checked:
                    raise ValueError("No independently reviewed path")
                e["segments"] = [reference[k]["subject"]]
                e["target"] = entity("Product", reference[k]["object"])
            reviewed["events"] = events
            reviewed["graph"] = project(graph, reviewed)
            # Preserve the trial evidence, while preventing ordinary EXPOSURE traversals over rejected edges.
            graph.run(
                """UNWIND $pairs AS x MATCH (a:AnnualExposure {scope:$scope,id:x.a})
                          -[r:EXPOSURE {role:x.role}]->(b:AnnualExposure {scope:$scope,id:x.b})
                          MERGE (a)-[u:UNVERIFIED_EXPOSURE {role:r.role,digest:r.digest,page:r.page,quote:r.quote}]->(b)
                          SET u.status='unknown', u.trial_provenance=r.provenance DELETE r""",
                {"scope": raw["graph"]["scope"], "pairs": not_supported},
            )
            check = graph.run(
                """UNWIND $pairs AS x MATCH (:AnnualExposure {scope:$scope,id:x.a})
                       -[r:EXPOSURE {role:x.role}]->(:AnnualExposure {scope:$scope,id:x.b})
                       RETURN count(r) AS remaining""",
                {"scope": raw["graph"]["scope"], "pairs": not_supported},
            )[0]
            if check["remaining"]:
                raise ValueError("Unreviewed edge in factual traversal")
            (output / f"{arm}-reviewed.json").write_text(json.dumps(reviewed, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("frozen", "recent", "reference", "output"):
        p.add_argument(name, type=Path)
    args = p.parse_args()
    publish(args.frozen, args.recent, json.loads(args.reference.read_text()), args.output)
