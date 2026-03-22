import pytest
from src.tools.web_search import _extract_published_date

def test_extract_from_date_field():
    """DDGS result with date field returns that date."""
    result = {"title": "Test", "href": "http://test.com", "body": "Some text", "date": "2026-03-15"}
    assert _extract_published_date(result) == "2026-03-15"

def test_extract_from_body_march_format():
    """Date embedded in body like 'Mar 15, 2026'."""
    result = {"title": "Test", "href": "http://test.com", "body": "Mar 15, 2026 - Article about stuff"}
    assert _extract_published_date(result) == "2026-03-15"

def test_extract_from_body_march_no_comma():
    """Date embedded like 'March 15 2026'."""
    result = {"title": "Test", "href": "http://test.com", "body": "March 15 2026 - News story"}
    assert _extract_published_date(result) == "2026-03-15"

def test_extract_from_body_iso_format():
    """Date embedded like '2026-03-15'."""
    result = {"title": "Test", "href": "http://test.com", "body": "Updated 2026-03-15 by admin"}
    assert _extract_published_date(result) == "2026-03-15"

def test_extract_from_body_day_month_year():
    """Date embedded like '15 March 2026'."""
    result = {"title": "Test", "href": "http://test.com", "body": "Posted 15 March 2026"}
    assert _extract_published_date(result) == "2026-03-15"

def test_no_date_found():
    """No date in date field or body returns None."""
    result = {"title": "Test", "href": "http://test.com", "body": "No date here"}
    assert _extract_published_date(result) is None