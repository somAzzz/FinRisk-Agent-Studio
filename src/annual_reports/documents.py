"""Bounded acquisition and extraction for company IR documents."""

from __future__ import annotations

import base64
import hashlib
import io
import ipaddress
import os
import re
import socket
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from lxml import etree

from src.annual_reports.charts import chart_caption, chart_rows, chart_text

MAX_BYTES = 48 * 1024 * 1024
MAX_PAGES = 800


class DocumentError(ValueError):
    pass


@dataclass
class Page:
    number: int
    printed: str | None
    text: str
    method: str
    relationship_text: str = ""
    relationship_method: str = "native"
    ocr_reason: str | None = None


@dataclass
class Document:
    source: str
    sha256: str
    pages: list[Page]
    warnings: list[str] = field(default_factory=list)
    tagged_facts: list[dict] = field(default_factory=list)
    chart_rows: list[dict] = field(default_factory=list)


def download(url: str, *, discover_pdf: bool = True) -> tuple[bytes, str]:
    """Pin each connection to a validated public address, including redirects."""
    with httpx.Client(timeout=45, trust_env=False) as client:
        for _ in range(7):
            parts = urlsplit(url)
            if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
                raise DocumentError("An absolute public HTTP(S) URL is required")
            parsed = httpx.URL(url)
            addresses = socket.getaddrinfo(
                parts.hostname, parsed.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM
            )
            ips = [ipaddress.ip_address(row[4][0]) for row in addresses]
            if not ips or any(not ip.is_global or ip.is_multicast for ip in ips):
                raise DocumentError("Only publicly routable document hosts are supported")
            with client.stream(
                "GET",
                parsed.copy_with(host=str(ips[0])),
                headers={"Host": parsed.netloc.decode(), "User-Agent": "FinRisk/1.0", "Accept-Encoding": "identity"},
                extensions={"sni_hostname": parsed.raw_host.decode()},
            ) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers["location"])
                    continue
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_bytes(65536):
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise DocumentError("Document exceeds 48 MiB")
            payload = bytes(data)
            if (
                discover_pdf
                and not is_pdf(payload)
                and b"<html" in payload[:4096].lower()
                and b"xmlns:ix" not in payload[:8192].lower()
            ):
                links = BeautifulSoup(payload, "html.parser").select("a[href]")
                candidates = list(
                    dict.fromkeys(
                        urljoin(url, a["href"]) for a in links if urlsplit(a["href"]).path.lower().endswith(".pdf")
                    )
                )
                if len(candidates) != 1:
                    raise DocumentError(f"Choose a specific report PDF from this IR page: {candidates[:12]}")
                url, discover_pdf = candidates[0], False
                continue
            return payload, url
    raise DocumentError("Too many document redirects")


def is_pdf(data: bytes) -> bool:
    return b"%PDF-" in data[:1024]


def _poppler(args: list[str], data: bytes | None = None) -> bytes:
    try:
        return subprocess.run(args, input=data, capture_output=True, check=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise DocumentError(f"{args[0]} failed to process the PDF") from exc


def native_pages(data: bytes) -> list[Page]:
    if len(data) > MAX_BYTES or not is_pdf(data):
        raise DocumentError("A valid PDF of at most 48 MiB is required")
    info = _poppler(["pdfinfo", "-"], data)
    count = re.search(rb"(?m)^Pages:\s+(\d+)", info)
    if not count or not 0 < int(count[1]) <= MAX_PAGES:
        raise DocumentError("Unsupported PDF page count")
    raw = _poppler(["pdftotext", "-raw", "-enc", "UTF-8", "-", "-"], data).decode().split("\f")
    pages = []
    for n, text in enumerate(raw[: int(count[1])], 1):
        # Infer a printed folio only when isolated next to the page boundary.
        lines = text.strip().splitlines()
        printed = next((x.strip() for x in lines[-1:] if re.fullmatch(r"[1-9]\d{0,3}", x.strip())), None)
        if len(lines) > 1 and re.search(r"(?i)(geschäftsbericht|annual report)", lines[0]) and lines[1].isdigit():
            printed = lines[1]
        pages.append(Page(n, printed, text.strip(), "native"))
    # Some cover/summary folios appear at the top of the native reading order.
    for index, page in enumerate(pages):
        if page.printed is None and 0 < index < len(pages) - 1:
            left, right = pages[index - 1].printed, pages[index + 1].printed
            if left and right and int(right) == int(left) + 2:
                candidate = str(int(left) + 1)
                if candidate in page.text.splitlines()[:4]:
                    page.printed = candidate
    return pages


def render_page(path: Path, page: int) -> bytes:
    return _poppler(
        ["pdftoppm", "-f", str(page), "-l", str(page), "-scale-to", "2200", "-singlefile", "-png", str(path)]
    )


def ocr_page(path: Path, page: int) -> str:
    image = render_page(path, page)
    content = [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(image).decode()}},
        {
            "type": "text",
            "text": "Transcribe the complete document page including tables, units and chart labels.",
        },
    ]
    url = os.getenv("OCR_BASE_URL", "http://127.0.0.1:8001/v1").rstrip("/")
    response = httpx.post(
        url + "/chat/completions",
        timeout=240,
        json={
            "model": os.getenv("OCR_MODEL", "Xiaomi-OCR-0"),
            "temperature": 0,
            "max_tokens": 10000,
            "messages": [{"role": "user", "content": content}],
        },
    )
    response.raise_for_status()
    choice = response.json()["choices"][0]
    if choice["finish_reason"] != "stop" or not choice["message"]["content"].strip():
        raise DocumentError("Incomplete OCR output")
    return choice["message"]["content"].strip()


def _inline_xbrl(data: bytes) -> tuple[list[Page], list[dict]]:
    try:
        root = etree.fromstring(data, etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError as exc:
        raise DocumentError("Expected PDF or well-formed inline XBRL XHTML") from exc
    if root.getroottree().docinfo.doctype and b"<!ENTITY" in data.upper():
        raise DocumentError("External document entities are unsupported")
    ix = {"ix": "http://www.xbrl.org/2013/inlineXBRL"}
    contexts = {e.get("id"): " ".join(e.itertext()).split() for e in root.xpath("//*[local-name()='context']")}
    units = {e.get("id"): " ".join(e.itertext()).split() for e in root.xpath("//*[local-name()='unit']")}
    facts = [
        {
            "concept": e.get("name"),
            "raw": "".join(e.itertext()).strip(),
            "context": contexts.get(e.get("contextRef")),
            "unit": units.get(e.get("unitRef")),
            "scale": e.get("scale", "0"),
            "sign": e.get("sign", ""),
            "format": e.get("format"),
            "id": e.get("id"),
            "context_id": e.get("contextRef"),
        }
        for e in root.xpath("//ix:nonFraction", namespaces=ix)
    ]
    for fact in facts:
        fmt = (fact["format"] or "").split(":")[-1].lower()
        raw = "".join(fact["raw"].split())
        if fmt in {"num-comma-decimal", "numcommadecimal"}:
            raw = raw.replace(".", "").replace(",", ".")
        elif fmt in {"num-dot-decimal", "numdotdecimal"}:
            raw = raw.replace(",", "")
        elif fmt:
            raw = ""
        try:
            value = Decimal(raw)
            scale = int(fact["scale"])
            if not value.is_finite() or abs(scale) > 100 or fact["sign"] not in ("", "-"):
                raise ValueError
            fact["value"] = str(value.scaleb(scale) * (-1 if fact["sign"] else 1))
        except (ValueError, InvalidOperation):
            fact["value"] = None
    if not facts:
        raise DocumentError("No inline XBRL monetary or numeric facts found")
    body = root.xpath("//*[local-name()='body']")
    text = " ".join(" ".join(body[0].itertext()).split()) if body else ""
    return [Page(1, None, text, "inline_xbrl")], facts


def percentages(text: str) -> set[str]:
    return {
        v.replace(" ", "").replace("\u2212", "-").replace("\u2013", "-")
        for v in re.findall(r"[+\u2212\u2013-]?\d+(?:[.,]\d+)*\s*%", text)
    }


def ocr_trigger(text: str, has_large_image: bool) -> str | None:
    if len(text.strip()) < 12:
        return "empty_text_layer"
    if text.count("\ufffd") >= max(3, len(text) // 100):
        return "damaged_text_layer"
    if has_large_image and len(text.split()) < 30:
        return "sparse_text_over_image"
    return None


def prefers_layout(text):
    lines = text.splitlines()
    return (
        sum(len(re.findall(r"(?<!\w)\d[\d,.]*", line)) >= 5 for line in lines) >= 3
        or sum(line.lstrip().startswith(("•", "▪")) for line in lines) >= 10
        or ("Scope" in text and re.search(r"[\u2019']s [A-Z0-9-]{1,8}(?:, [A-Z0-9-]{1,8}){2,}", text) is not None)
    )


def large_image_pages(path):
    listing = _poppler(["pdfimages", "-list", str(path)]).decode().splitlines()
    pages = set()
    for line in listing:
        fields = line.split()
        if (
            len(fields) > 4
            and fields[0].isdigit()
            and fields[2] == "image"
            and int(fields[3]) >= 600
            and int(fields[4]) >= 300
        ):
            pages.add(int(fields[0]))
    return pages


def extract(data: bytes, source: str, force_ocr: set[int] | None = None) -> Document:
    if not data or len(data) > MAX_BYTES:
        raise DocumentError("Empty or oversized report")
    doc = Document(source, hashlib.sha256(data).hexdigest(), [])
    if not is_pdf(data):
        if data.startswith(b"PK"):
            if not zipfile.is_zipfile(io.BytesIO(data)):
                raise DocumentError("Invalid ESEF archive")
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                files = [item for item in archive.infolist() if item.filename.lower().endswith((".xhtml", ".html"))]
                if len(files) != 1 or files[0].file_size > MAX_BYTES:
                    raise DocumentError("Supply one ESEF XHTML report of at most 48 MiB")
                try:
                    data = archive.read(files[0])
                except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
                    raise DocumentError("Unreadable or encrypted ESEF report") from exc
        doc.pages, doc.tagged_facts = _inline_xbrl(data)
        return doc
    doc.pages = native_pages(data)
    forced = force_ocr or set()
    if forced.difference(p.number for p in doc.pages):
        raise DocumentError("Requested OCR page outside physical PDF page range")
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "source.pdf"
        path.write_bytes(data)
        sparse = any(
            len(p.text.strip()) >= 12 and len(p.text.split()) < 30 and p.number not in forced for p in doc.pages
        )
        images = large_image_pages(path) if sparse else set()
        for page in doc.pages:
            if prefers_layout(page.text):
                n = str(page.number)
                layout_text = (
                    _poppler(["pdftotext", "-f", n, "-l", n, "-layout", str(path), "-"]).decode().strip("\f\n")
                )
                if layout_text.strip():
                    page.relationship_text = layout_text
                    page.relationship_method = "layout"
            rows = []
            if len(percentages(page.text)) >= 2 and any(chart_caption(line) for line in page.text.splitlines()):
                n = str(page.number)
                layout = _poppler(["pdftotext", "-f", n, "-l", n, "-bbox-layout", str(path), "-"])
                rows = chart_rows(layout, render_page(path, page.number), page.number, page.printed)
                doc.chart_rows.extend(rows)
            page.ocr_reason = "explicit" if page.number in forced else ocr_trigger(page.text, page.number in images)
            if page.ocr_reason:
                try:
                    text = ocr_page(path, page.number)
                    if rows and not (percentages(chart_text(rows)) & percentages(text)):
                        text += "\n[PDF chart layout]\n" + chart_text(rows)
                    if page.text:
                        # Charts can be omitted by whole-page OCR. Retain native numbers and surface disagreement.
                        missing = sorted(percentages(page.text) - percentages(text))
                        if missing:
                            doc.warnings.append(f"PDF page {page.number}: native percentages missing in OCR: {missing}")
                    page.method = "native+ocr" if page.text else "ocr"
                    page.relationship_text = text
                    page.relationship_method = "ocr"
                    page.text = page.text + "\n[OCR transcription]\n" + text if page.text else text
                except (ValueError, httpx.HTTPError, KeyError, IndexError) as exc:
                    doc.warnings.append(f"PDF page {page.number}: OCR unavailable ({type(exc).__name__})")
    if not any(p.text.strip() for p in doc.pages):
        raise DocumentError("No readable native or OCR text")
    return doc
