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