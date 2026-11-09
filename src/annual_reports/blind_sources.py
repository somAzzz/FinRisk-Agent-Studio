"""Discover primary publications from graph-derived terms. Search metadata is never evidence."""

import hashlib
import json
import re
from datetime import date, timedelta
from urllib.parse import urlencode, urlsplit

import httpx
from bs4 import BeautifulSoup

from src.tools.web_search import web_search

from .documents import download, is_pdf, native_pages


def digest(data):
    return hashlib.sha256(data).hexdigest()


def register_hits(term, cutoff):
    params = {
        "conditions[term]": term,
        "conditions[publication_date][gte]": str(cutoff - timedelta(days=365)),
        "conditions[publication_date][lte]": str(cutoff),
        "order": "newest",
        "per_page": 4,
    }
    endpoint = "https://www.federalregister.gov/api/v1/documents.json?" + urlencode(params)
    data, _ = download(endpoint, discover_pdf=False)
    listing = json.loads(data)
    if not isinstance(listing.get("results"), list):
        if listing.get("count") == 0:
            return []
        raise ValueError("Registry did not return a document list")
    return [
        {
            "url": r["pdf_url"],
            "published": r["publication_date"],
            "locator": r["document_number"],
            "canonical": r["html_url"],
            "title": r["title"],
        }
        for r in listing["results"]
        if r.get("pdf_url")
    ]


def web_hits(term):
    response = json.loads(web_search(term, max_results=4))
    if response.get("error"):
        raise ValueError(response["error"][:200])
    return [{"url": item["url"], "title": item["title"]} for item in response["results"] if item.get("url")]


def authority(host):
    return host.endswith((".gov", ".gov.uk", ".gc.ca", ".europa.eu", ".gouv.fr", ".bund.de"))


def register_pages(pages, identifier):
    """Keep the numbered article and physical page coordinates, excluding neighbouring notices."""
    if not re.fullmatch(r"[A-Za-z0-9]+-\d+", identifier):
        raise ValueError("Invalid registry identifier")
    # The printed docket number can use different Unicode dash characters.
    marker = re.compile(r"\[FR Doc\.\s*([A-Za-z0-9]+[-\u2013\u2014\u2011]\d+)\s+Filed", re.I)
    text = "\f".join(pages)
    start = 0
    for m in marker.finditer(text):
        if re.sub(r"[\u2013\u2014\u2011]", "-", m[1]) == identifier:
            end = m.start()
            result = []
            position = 0
            for page in pages:
                left, right = max(0, start - position), min(len(page), end - position)
                result.append(page[left:right] if left < right else "")
                position += len(page) + 1
            return result
        start = m.end()
    raise ValueError("Document identifier missing from original")


def fetch(hit, cutoff, folder):
    host = urlsplit(hit["url"]).hostname or ""
    if not authority(host):
        raise ValueError("Independent primary publisher not established")
    if host == "www.sec.gov" and "/Archives/edgar/" in urlsplit(hit["url"]).path:
        raise ValueError("Issuer filing requires issuer-disclosure provenance")
    raw, resolved = download(hit["url"], discover_pdf=False)
    if not authority(urlsplit(resolved).hostname or ""):
        raise ValueError("Unexpected redirect publisher")
    stamp = hit.get("published")
    if is_pdf(raw):
        pages = [p.text for p in native_pages(raw)]
        if not stamp or not hit.get("locator"):
            raise ValueError("PDF lacks a dated official catalogue record")
        # The Federal Register PDF must bear the exact document identifier.
        pages = register_pages(pages, hit["locator"])
        fmt = "pdf"
    else:
        soup = BeautifulSoup(raw, "html.parser")
        meta = soup.select_one(
            'meta[property="article:published_time"],meta[name="DC.date.issued"],meta[itemprop="datePublished"]'
        )
        if not meta:
            raise ValueError("No explicit publication metadata")
        stamp = meta.get("content", "")[:10]
        body = soup.select_one("article") or soup.select_one("main")
        if not body:
            raise ValueError("No identifiable article body")
        for tag in body.select("nav, aside, footer, script, style"):
            tag.decompose()
        pages = [body.get_text(" ", strip=True)]
        fmt = "html"
    if date.fromisoformat(stamp) > cutoff:
        raise ValueError("Outside observation cutoff")
    sha = digest(raw)
    (folder / f"{sha}.{fmt}").write_bytes(raw)
    return {**hit, "url": resolved, "published": stamp, "digest": sha, "pages": [" ".join(p.split()) for p in pages]}


def discover(tasks, cutoff, folder):
    documents, trace, seen = [], [], set()
    for task in tasks:
        providers = [(web_hits, task["web_query"])]
        if task["us_regulatory_relevance"]:
            providers.insert(0, (register_hits, task["registry_term"]))
        for provider, query in providers:
            log = {"provider": provider.__name__, "query": query, "target": task["target"], "results": []}
            trace.append(log)
            try:
                hits = register_hits(query, cutoff) if provider == register_hits else web_hits(query)
            except (ValueError, httpx.HTTPError, OSError) as exc:
                log["error"] = str(exc)[:220]
                continue
            for hit in hits:
                row = {"url": hit["url"], "title": hit["title"]}
                log["results"].append(row)
                if hit["url"] in seen:
                    row["decision"] = "already evaluated"
                    continue
                seen.add(hit["url"])
                try:
                    item = fetch(hit, cutoff, folder)
                    documents.append(item)
                    row["decision"] = "pinned original"
                except (ValueError, httpx.HTTPError, OSError) as exc:
                    row["decision"] = str(exc)[:180]
    return documents, trace
