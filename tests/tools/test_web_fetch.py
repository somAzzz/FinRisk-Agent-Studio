import pytest
from src.tools.web_fetch import _is_blacklisted_domain, _extract_metadata

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