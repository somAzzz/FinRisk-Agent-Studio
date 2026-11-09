"""Follow up frozen, machine-selected targets using recent UK official publications."""

import argparse
import json
import re
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel

from src.annual_reports.audit import structured
from src.annual_reports.blind import adjudicate
from src.annual_reports.documents import download
from src.annual_reports.non_us import british_original
from src.graph.client import Neo4jClient


class Selection(BaseModel):
    index: int | None


def check(run_dir, out, days):
    frozen = json.loads((run_dir / "result.json").read_text())
    cutoff = date.fromisoformat(frozen["as_of"])
    start = cutoff - timedelta(days=days)
    originals = out / "originals"
    originals.mkdir(parents=True, exist_ok=True)
    events, log, seen = [], [], set()
    with Neo4jClient() as graph:
        for task in frozen["tasks"]:
            target = task["target"]
            term = re.sub("[®™©]", "", target.split("/", 1)[1]).strip()
            query = {"q": term, "count": 6, "fields": "title,link", "filter_public_timestamp": "from:" + str(start)}
            listing, _ = download("https://www.gov.uk/api/search.json?" + urlencode(query), discover_pdf=False)
            for item in json.loads(listing)["results"]:
                if not item["link"].startswith("/"):
                    continue
                url = "https://www.gov.uk" + item["link"]
                if (target, url) in seen:
                    continue
                seen.add((target, url))
                attempt = {"query": term, "target": target, "url": url, "decision": "unknown"}
                log.append(attempt)
                try:
                    doc = british_original({"title": item["title"], "url": url}, cutoff, originals)
                    if not start.isoformat() <= doc["first_published"][:10] <= cutoff.isoformat():
                        raise ValueError("Outside publication window")
                except (ValueError, OSError, KeyError, httpx.HTTPError) as exc:
                    attempt["reason"] = str(exc)[:200]
                    continue
                body = doc["pages"][0]
                sentences = re.split(r"(?<=[.!?])\s+", body)
                spans = [s for s in sentences if term.casefold() in s.casefold() and len(s) < 2000][:16]
                if not spans:
                    attempt["reason"] = "No named target sentence"
                    continue
                chosen = structured(
                    Selection,
                    "Select the integer index of a source sentence that states an "
                    "official action or decision concerning the target brand. Preserve scope. Return null "
                    "for general safety advice or mere co-occurrence.",
                    {
                        "issuer": frozen["issuer"],
                        "target": target,
                        "title": doc["title"],
                        "sentences": dict(enumerate(spans)),
                    },
                ).index
                if chosen is None or not 0 <= chosen < len(spans):
                    attempt["reason"] = "No decisive span selected"
                    continue
                quote = spans[chosen]
                row = adjudicate(
                    [{"target": term, "quote": quote}],
                    [quote],
                    "Require the named product, a concrete official action and its scope to follow from "
                    "the original passage alone. A product's clinical indication alone does not establish "
                    "a change in regulatory status.",
                )[0]
                if row["status"] != "supported":
                    attempt["reason"] = row["review"]
                    continue
                paths = graph.run(
                    """MATCH (p:AnnualExposure {scope:$scope,id:$target})<-[r:EXPOSURE]-
                    (s:AnnualExposure {kind:'Segment'})<-[:EXPOSURE {role:'HAS_SEGMENT'}]-
                    (:AnnualExposure {kind:'Company'})
                    WHERE r.role IN ['PRODUCES','USES','OPERATES','SOURCES_FROM','SERVES']
                    RETURN DISTINCT s.id AS segment,r.page AS page,r.quote AS quote ORDER BY segment,page""",
                    {"scope": frozen["graph"]["scope"], "target": target},
                )
                if paths:
                    attempt["decision"] = "supported"
                    events.append(
                        {
                            "source": url,
                            "source_sha256": doc["digest"],
                            "published": doc["first_published"][:10],
                            "target": target,
                            "quote": quote,
                            "paths": paths,
                            "attributable_amount": "unknown",
                            "fulfillment": "unknown",
                            "realized_impact": "unknown",
                        }
                    )
    result = {
        "stage": "post-freeze diagnostic",
        "start": str(start),
        "cutoff": str(cutoff),
        "search": log,
        "events": events,
    }
    (out / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(len(events), "recent paths", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run_directory", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--days", type=int, default=180)
    a = p.parse_args()
    check(a.run_directory, a.output, a.days)
