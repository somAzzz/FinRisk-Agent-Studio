from dataclasses import dataclass
from typing import Literal

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
    "403_FORBIDDEN": "Access denied. This site may have anti-bot protection (Cloudflare, etc.).",
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


def _is_blacklisted_domain(url: str) *********REMOVED********* bool:
    """Returns True if URL domain equals or ends with . + known dynamic domain."""
    from urllib.parse import urlparse

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


def _extract_metadata(html: str) *********REMOVED********* tuple[str | None, str | None]:
    """Extract title and description from raw HTML using BeautifulSoup."""
    from bs4 import BeautifulSoup

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


def _truncate_content(content: str, max_size: int = MAX_CONTENT_SIZE) *********REMOVED********* str:
    """Truncate content at last paragraph boundary if > max_size."""
    if len(content) <= max_size:
        return content

    # Try to truncate at paragraph boundary (\n\n)
    truncated = content[:max_size]
    last_paragraph = truncated.rfind("\n\n")
    if last_paragraph > max_size // 2:
        truncated = truncated[:last_paragraph]

    return truncated + "...(truncated)"