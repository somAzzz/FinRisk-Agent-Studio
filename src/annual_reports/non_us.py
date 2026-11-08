"""Discover dated independent publications outside US catalogues from an audited graph."""

import json
from datetime import date
from urllib.parse import urlencode, urlsplit

import httpx
from bs4 import BeautifulSoup

from .blind_sources import authority, digest, fetch, web_hits
from .documents import download


def british_hits(query):
    params = {"q": query, "count": 5, "fields": "title,link"}
    raw, _ = download("https://www.gov.uk/api/search.json?" + urlencode(params), discover_pdf=False)
    return [
        {"title": v["title"], "url": "https://www.gov.uk" + v["link"]}
        for v in json.loads(raw)["results"]
        if v.get("link", "").startswith("/")
    ]


def british_original(hit, cutoff, folder):
    path = urlsplit(hit["url"]).path
    raw, url = download("https://www.gov.uk/api/content" + path, discover_pdf=False)
    obj = json.loads(raw)
    if (
        obj.get("base_path") != path
        or urlsplit(url).hostname != "www.gov.uk"
        or obj.get("document_type")
        not in {
            "press_release",
            "news_story",
            "government_response",
            "drug_safety_update",
            "medical_safety_alert",
            "decision",
            "guidance",
            "research",
            "notice",
        }
    ):
        raise ValueError("No eligible official publication")
    body = obj["details"].get("body")
    stamp = (obj.get("public_updated_at") or obj.get("first_published_at") or "")[:10]
    if not isinstance(body, str) or date.fromisoformat(stamp) > cutoff:
        raise ValueError("Undated, future or unsupported publication")
    page = " ".join(BeautifulSoup(body, "html.parser").stripped_strings)
    if not page.strip():
        raise ValueError("Empty original")
    sha = digest(raw)
    (folder / (sha + ".json")).write_bytes(raw)
    return {
        **hit,
        "published": stamp,
        "first_published": obj.get("first_published_at"),
        "digest": sha,
        "title": obj["title"],
        "pages": [" ".join(page.split())],
        "archive_url": url,
    }


def discover_non_us(tasks, cutoff, folder):
    documents, trace, seen = [], [], set()
    for t in tasks:
        name = t["target"].split("/", 1)[1]
        for provider, query in [(british_hits, name), (web_hits, t["web_query"])]:
            log = {"provider": provider.__name__, "query": query, "target": t["target"], "results": []}
            trace.append(log)
            try:
                hits = provider(query)
            except (ValueError, KeyError, OSError, httpx.HTTPError) as e:
                log["error"] = str(e)[:180]
                continue
            for hit in hits:
                host = urlsplit(hit["url"]).hostname or ""
                row = {**hit}
                log["results"].append(row)
                if hit["url"] in seen:
                    row["decision"] = "already evaluated"
                    continue
                seen.add(hit["url"])
                try:
                    if host.endswith(".gov") or not (authority(host) or host == "www.gov.uk"):
                        raise ValueError("Outside the non-US official-source scope")
                    item = (british_original if host == "www.gov.uk" else fetch)(hit, cutoff, folder)
                    documents.append(item)
                    row.update(decision="pinned original", digest=item["digest"], published=item["published"])
                except (KeyError, TypeError, ValueError, OSError, httpx.HTTPError) as e:
                    row["decision"] = str(e)[:180]
    return documents, trace
