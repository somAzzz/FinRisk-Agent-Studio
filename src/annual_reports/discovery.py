"""Discover dated publications without exposing live search snippets to historical analysts."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from src.annual_reports.documents import Document, DocumentError, download, is_pdf, native_pages
from src.annual_reports.financials import identity
from src.tools.web_search import web_search


def site(doc):
    if doc.source.startswith(("http://", "https://")):
        return urlsplit(doc.source).hostname
    hosts = Counter(re.findall(r"\bwww\.[\w.-]+\.[a-z]{2,}(?=[/\s)])", "\n".join(p.text for p in doc.pages), re.I))
    return hosts.most_common(1)[0][0] if hosts else None


def links(url):
    data, resolved = download(url, discover_pdf=False)
    return [urljoin(resolved, a["href"]) for a in BeautifulSoup(data, "html.parser").select("a[href]")]


def issuer_catalog(host):
    home = links("https://" + host)
    hubs = set()
    for u in home:
        if urlsplit(u).hostname != host:
            continue
        match = re.search(r"/(?:publications|publikationen|financial-reports|finanzberichte|reports)(?:/|$)", u, re.I)
        if match:
            hubs.add(u[: match.end()].rstrip("/"))
    found = [u for u in home if urlsplit(u).path.lower().endswith(".pdf")]
    for hub in sorted(hubs)[:4]:
        found.extend(u for u in links(hub) if urlsplit(u).path.lower().endswith(".pdf"))
    return list(dict.fromkeys(found))


def discover(doc, queries, work: Path):
    host = site(doc)
    trace, candidates, admitted = [], {}, []
    if host:
        try:
            for u in issuer_catalog(host):
                candidates[u] = "issuer publications index"
        except (OSError, ValueError, httpx.HTTPError) as exc:
            trace.append({"step": "issuer_index", "error": type(exc).__name__})
    for q in queries:
        response = json.loads(web_search(q, max_results=5))
        urls = [r.get("url") or r.get("href") for r in response.get("results", [])]
        trace.append({"query": q, "found": urls, "search_error": response.get("error")})
        for u in urls:
            if u:
                candidates.setdefault(u, q)
    # Official Journal editions have permanent publication identifiers; follow these even on a mutable index.
    for landing in list(candidates)[:40]:
        if (urlsplit(landing).hostname or "").endswith(".europa.eu") and not landing.endswith(".pdf"):
            try:
                for act in links(landing):
                    if urlsplit(act).hostname == "eur-lex.europa.eu" and "uri=OJ:" in act and "/TXT/" in act:
                        edition = act.replace("/TXT/", "/TXT/PDF/") if "/PDF/" not in act else act
                        candidates.setdefault(edition, landing)
            except (OSError, ValueError, httpx.HTTPError):
                trace.append({"url": landing, "decision": "official index unavailable"})
    for url, origin in candidates.items():
        domain = urlsplit(url).hostname or ""
        if not (domain == host or domain.endswith((".gov", ".europa.eu", ".gov.uk", ".bund.de"))):
            trace.append({"url": url, "decision": "publisher authority not established"})
            continue
        try:
            journal = domain == "eur-lex.europa.eu" and "uri=OJ:" in url and "/PDF/" in url
            if not journal and not urlsplit(url).path.lower().endswith(".pdf"):
                trace.append({"url": url, "decision": "unversioned web page; excluded from replay"})
                continue
            data, resolved = download(url, discover_pdf=False)
            if urlsplit(resolved).hostname != domain or not is_pdf(data):
                raise DocumentError("Unexpected publication origin or format")
            digest = hashlib.sha256(data).hexdigest()
            candidate = Document(resolved, digest, native_pages(data))
            published = identity(candidate)["published_at"]
            # Require intrinsic publication evidence AND a version-specific publication URL.
            date_evidence = identity(candidate)["date_evidence"]
            if journal:
                text = candidate.pages[0].text
                masthead = re.search(
                    r"Official Journal of the European Union.{0,200}?(\d{1,2}\.\d{1,2}\.20\d{2})",
                    " ".join(text.split()),
                    re.I,
                )
                if masthead:
                    published = datetime.strptime(masthead[1], "%d.%m.%Y").date()
                    date_evidence = [masthead[0]]
            if not published or not (journal or re.search(r"20\d\d", urlsplit(resolved).path)):
                trace.append({"url": url, "decision": "no intrinsic publication date or version-specific URL"})
                continue
            (work / (digest + ".pdf")).write_bytes(data)
            admitted.append((candidate, published))
            trace.append(
                {
                    "url": resolved,
                    "origin": origin,
                    "decision": "dated edition",
                    "sha256": digest,
                    "published": published.isoformat(),
                    "date_evidence": date_evidence,
                }
            )
        except (OSError, ValueError, httpx.HTTPError) as exc:
            trace.append({"url": url, "decision": "unavailable", "error": type(exc).__name__})
    return admitted, trace
