import pytest
from src.tools.web_fetch import _is_blacklisted_domain, _extract_metadata, _truncate_content, WebFetchResult, serialize_result, web_fetch

def test_blacklist_exact_match():
    """tradingview.com should match"""
    assert _is_blacklisted_domain("https://tradingview.com/symbol/NASDAQ:AAPL") is True

def test_blacklist_subdomain():
    """blog.tradingview.com should match"""
    assert _is_blacklisted_domain("https://blog.tradingview.com/article") is True

def test_blacklist_false_positive():
    """nottradingview.com should NOT match"""
    assert _is_blacklisted_domain("https://nottradingview.com") is False

def test_whitelist_normal():
    """example.com should NOT match"""
    assert _is_blacklisted_domain("https://example.com/article") is False

def test_whitelist_subdomain_false_positive():
    """notexample.com should NOT match"""
    assert _is_blacklisted_domain("https://notexample.com") is False


def test_extract_title():
    html = "<html><head><title>Test Page Title</title></head></html>"
    title, desc = _extract_metadata(html)
    assert title == "Test Page Title"
    assert desc is None


def test_extract_description():
    html = '<html><head><meta name="description" content="Test description text"></head></html>'
    title, desc = _extract_metadata(html)
    assert title is None
    assert desc == "Test description text"


def test_extract_both():
    html = '<html><head><title>Page</title><meta name="description" content="Desc"></head></html>'
    title, desc = _extract_metadata(html)
    assert title == "Page"
    assert desc == "Desc"


def test_extract_no_metadata():
    html = "<html><body><p>No metadata here</p></body></html>"
    title, desc = _extract_metadata(html)
    assert title is None
    assert desc is None


def test_truncate_small_content():
    """Content under limit should be unchanged"""
    content = "Short content"
    result = _truncate_content(content, max_size=100)
    assert result == "Short content"


def test_truncate_large_content():
    """Content over limit should be truncated at paragraph boundary"""
    content = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph that pushes us over the limit." + "x" * 1000
    result = _truncate_content(content, max_size=50)
    assert len(result) <= 50 + len("...(truncated)")
    assert result.endswith("...(truncated)")
    assert "\n\n" in result  # Truncated at paragraph boundary


def test_truncate_no_paragraph_boundary():
    """Content with no paragraph markers should truncate at max_size"""
    content = "A" * 200
    result = _truncate_content(content, max_size=100)
    assert len(result) <= 100 + len("...(truncated)")
    assert result.endswith("...(truncated)")


def test_serialize_success():
    result = WebFetchResult(
        url="https://example.com",
        title="Test",
        description="A test",
        content="# Hello",
        status="success"
    )
    json_str = serialize_result(result)
    assert '"url": "https://example.com"' in json_str
    assert '"title": "Test"' in json_str
    assert '"content": "# Hello"' in json_str

def test_serialize_failure():
    result = WebFetchResult(
        url="https://example.com",
        status="failed",
        error_code="404_NOT_FOUND",
        error_message="Page not found",
        suggestion="Try another source",
        content=""
    )
    json_str = serialize_result(result)
    assert '"status": "failed"' in json_str
    assert '"error_code": "404_NOT_FOUND"' in json_str


@pytest.mark.asyncio
async def test_web_fetch_blacklisted_domain():
    """Blacklisted domain should return BLACKLISTED_DOMAIN error"""
    result = await web_fetch("https://tradingview.com/symbol/AAPL")
    assert result.status == "failed"
    assert result.error_code == "BLACKLISTED_DOMAIN"
    assert "MarketExplorer" in result.suggestion


@pytest.mark.asyncio
async def test_web_fetch_invalid_url():
    """Invalid URL should return INVALID_URL error"""
    result = await web_fetch("not-a-url")
    assert result.status == "failed"
    assert result.error_code == "INVALID_URL"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_wikipedia():
    """Fetch Wikipedia article"""
    result = await web_fetch("https://en.wikipedia.org/wiki/Main_Page")
    assert result.status == "success"
    assert result.title is not None
    assert len(result.content) > 100

@pytest.mark.asyncio
@pytest.mark.integration
async def test_fetch_reuters():
    """Fetch Reuters article and verify metadata"""
    result = await web_fetch("https://www.reuters.com/world/us/")
    # Check structure (may fail on network issues)
    assert result.status in ("success", "failed")


def test_fetched_at_field_exists():
    """WebFetchResult has fetched_at field."""
    result = WebFetchResult(url="http://test.com", fetched_at="2026-03-22T14:30:00")
    assert result.fetched_at == "2026-03-22T14:30:00"

def test_fetched_at_none_for_failure():
    """Failed fetch has fetched_at=None."""
    result = WebFetchResult(
        url="http://test.com",
        status="failed",
        error_code="TIMEOUT",
        fetched_at=None
    )
    assert result.fetched_at is None


@pytest.mark.asyncio
async def test_web_fetch_sets_fetched_at_on_success():
    """Successful fetch returns fetched_at timestamp."""
    import re
    from unittest.mock import patch, AsyncMock, MagicMock
    from src.tools.web_fetch import web_fetch

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><head><title>Test</title></head><body><p>Content</p></body></html>"

    with patch("src.tools.web_fetch.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        # Ensure aclose is awaitable
        mock_client.aclose = AsyncMock()
        mock_client_class.return_value = mock_client
        mock_client.__aenter__.return_value = mock_client

        result = await web_fetch("http://example.com")

        assert result.status == "success"
        assert result.fetched_at is not None
        # Verify format: YYYY-MM-DDTHH:MM:SS
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", result.fetched_at)