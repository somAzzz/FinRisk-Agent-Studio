import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

ERROR_SUGGESTIONS = {
    "BLACKLISTED_DOMAIN": "Use MarketExplorer (real browser) to access this URL.",
    "INVALID_URL": "Verify the URL is correct.",
    "TIMEOUT": "The site may be slow; try again later.",
    "CONNECTION_ERROR": "Check your connection.",
    "404_NOT_FOUND": "Try searching for alternative sources.",
    "403_FORBIDDEN": "Use MarketExplorer with real browser.",
    "PARSE_ERROR": "Use MarketExplorer for complex pages.",
    "UNKNOWN": "Report this issue.",
}

_ERROR_MESSAGES = {
    "BLACKLISTED_DOMAIN": "This domain is known to require JavaScript rendering.",
    "INVALID_URL": "Malformed URL provided.",
    "TIMEOUT": "Request exceeded 10 second timeout.",
    "CONNECTION_ERROR": "Could not connect to the server.",
    "404_NOT_FOUND": "Page not found (HTTP 404).",
    "403_FORBIDDEN": (
        "Access denied. This site may have anti-bot protection (Cloudflare, etc.)."
    ),
    "PARSE_ERROR": "Failed to parse HTML content.",
    "UNKNOWN": "An unexpected error occurred.",
}

_KNOWN_DYNAMIC_DOMAINS = [
    "twitter.com",
    "x.com",
    "tradingview.com",
    "app.uniswap.org",
    "coinbase.com",
    "bloomberg.com",
    "wsj.com",
]

MAX_CONTENT_SIZE = 100_000  # 100KB
TIMEOUT_SECONDS = 10

# HTTP status code constants
HTTP_NOT_FOUND = 404
HTTP_FORBIDDEN = 403
HTTP_BAD_REQUEST = 400


def _is_blacklisted_domain(url: str) -> bool:
    """Returns True if URL domain equals or ends with . + known dynamic domain."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
    except Exception:
        return False

    for blacklisted in _KNOWN_DYNAMIC_DOMAINS:
        if domain == blacklisted or domain.endswith("." + blacklisted):
            return True
    return False


@dataclass
class WebFetchResult:
    url: str
    title: str | None = None
    description: str | None = None
    content: str = ""
    status: Literal["success", "failed"] = "success"
    error_code: str | None = None
    error_message: str | None = None
    suggestion: str | None = None
    fetched_at: str | None = None  # ISO timestamp for success, None for failures


def serialize_result(result: WebFetchResult) -> str:
    """Serialize result to JSON string for LLM tool call response."""
    return json.dumps(asdict(result))


def _extract_metadata(html: str) -> tuple[str | None, str | None]:
    """Extract title and description from raw HTML using BeautifulSoup."""
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return None, None

    title = None
    description = None

    # Extract title
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text().strip()

    # Extract meta description
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc and meta_desc.get("content"):
        description = meta_desc["content"].strip()

    return title, description


def _truncate_content(content: str, max_size: int = MAX_CONTENT_SIZE) -> str:
    """Truncate content at last paragraph boundary if > max_size."""
    if len(content) <= max_size:
        return content

    # Try to truncate at paragraph boundary (\n\n)
    truncated = content[:max_size]
    last_paragraph = truncated.rfind("\n\n")
    if last_paragraph > max_size // 2:
        truncated = truncated[:last_paragraph]

    return truncated + "...(truncated)"


def _check_http_status(status_code: int, url: str) -> WebFetchResult | None:
    """Check HTTP status and return error result if applicable, else None."""
    if status_code == HTTP_NOT_FOUND:
        return WebFetchResult(
            url=url,
            status="failed",
            error_code="404_NOT_FOUND",
            error_message=_ERROR_MESSAGES["404_NOT_FOUND"],
            suggestion=ERROR_SUGGESTIONS["404_NOT_FOUND"],
        )
    if status_code == HTTP_FORBIDDEN:
        return WebFetchResult(
            url=url,
            status="failed",
            error_code="403_FORBIDDEN",
            error_message=_ERROR_MESSAGES["403_FORBIDDEN"],
            suggestion=ERROR_SUGGESTIONS["403_FORBIDDEN"],
        )
    if status_code >= HTTP_BAD_REQUEST:
        return WebFetchResult(
            url=url,
            status="failed",
            error_code="UNKNOWN",
            error_message=f"HTTP error {status_code}",
            suggestion=ERROR_SUGGESTIONS["UNKNOWN"],
        )
    return None


async def web_fetch(url: str) -> WebFetchResult:
    """Fetch URL content and return metadata + Markdown (async)."""
    # 1. Check blacklist
    if _is_blacklisted_domain(url):
        return WebFetchResult(
            url=url,
            status="failed",
            error_code="BLACKLISTED_DOMAIN",
            error_message=_ERROR_MESSAGES["BLACKLISTED_DOMAIN"],
            suggestion=ERROR_SUGGESTIONS["BLACKLISTED_DOMAIN"],
        )

    # 2. Validate URL
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("Invalid URL")
    except Exception:
        return WebFetchResult(
            url=url,
            status="failed",
            error_code="INVALID_URL",
            error_message=_ERROR_MESSAGES["INVALID_URL"],
            suggestion=ERROR_SUGGESTIONS["INVALID_URL"],
        )

    # 3. Fetch via httpx - handle network errors with consolidated exception
    client = httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
    error_result: WebFetchResult | None = None
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Bot/0.1)",
            "Accept-Language": "en-US,en;q=0.9",
        }
        response = await client.get(url, headers=headers)
    except httpx.TimeoutException:
        error_result = WebFetchResult(
            url=url,
            status="failed",
            error_code="TIMEOUT",
            error_message=_ERROR_MESSAGES["TIMEOUT"],
            suggestion=ERROR_SUGGESTIONS["TIMEOUT"],
        )
    except httpx.ConnectError:
        error_result = WebFetchResult(
            url=url,
            status="failed",
            error_code="CONNECTION_ERROR",
            error_message=_ERROR_MESSAGES["CONNECTION_ERROR"],
            suggestion=ERROR_SUGGESTIONS["CONNECTION_ERROR"],
        )
    except Exception:
        error_result = WebFetchResult(
            url=url,
            status="failed",
            error_code="CONNECTION_ERROR",
            error_message=_ERROR_MESSAGES["CONNECTION_ERROR"],
            suggestion=ERROR_SUGGESTIONS["CONNECTION_ERROR"],
        )
    finally:
        await client.aclose()

    if error_result is not None:
        return error_result

    # 4. Check HTTP status
    error_result = _check_http_status(response.status_code, url)
    if error_result is not None:
        return error_result

    # 5. Extract metadata before processing
    title, description = _extract_metadata(response.text)

    # 6. Convert to Markdown via trafilatura
    try:
        markdown_content = trafilatura.extract(
            response.text,
            output_format="markdown",
            include_links=True
        )
        if not markdown_content:
            # trafilatura returns None for non-article pages
            markdown_content = ""
    except Exception:
        return WebFetchResult(
            url=url,
            status="failed",
            error_code="PARSE_ERROR",
            error_message=_ERROR_MESSAGES["PARSE_ERROR"],
            suggestion=ERROR_SUGGESTIONS["PARSE_ERROR"],
        )

    # 7. Truncate if needed
    content = _truncate_content(markdown_content, MAX_CONTENT_SIZE)

    return WebFetchResult(
        url=url,
        title=title,
        description=description,
        content=content,
        status="success",
        fetched_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
    )


def web_fetch_sync(url: str) -> WebFetchResult:
    """Synchronous wrapper for non-async contexts."""
    return asyncio.run(web_fetch(url))


WEB_FETCH_TOOL = {
    "name": "web_fetch",
    "description": (
        "Fetch URL content for RAG. Returns metadata + Markdown. "
        "Use for static pages. For JS-heavy sites, expect failure "
        "and use MarketExplorer instead."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "URL to fetch"}},
        "required": ["url"],
    },
}
