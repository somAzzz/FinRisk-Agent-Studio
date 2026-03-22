import json
import pytest
from src.tools.web_search import _extract_published_date, _format_search_output

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


def test_format_search_output_with_results():
    """JSON Envelope contains retrieved_at, query_used, time_range_applied, results."""
    results = [
        {"title": "Test Article", "href": "http://test.com/1", "body": "Mar 15, 2026 - Content here"},
        {"title": "Another", "href": "http://test.com/2", "body": "No date here"},
    ]
    output = _format_search_output(results, "test query", "m")

    data = json.loads(output)
    assert "retrieved_at" in data
    assert data["query_used"] == "test query"
    assert data["time_range_applied"] == "m"
    assert len(data["results"]) == 2
    assert data["results"][0]["title"] == "Test Article"
    assert data["results"][0]["url"] == "http://test.com/1"
    assert data["results"][0]["published_at"] == "2026-03-15"
    assert data["results"][1]["published_at"] is None

def test_format_search_output_empty():
    """Empty results returns envelope with empty results array."""
    output = _format_search_output([], "empty query", None)
    data = json.loads(output)
    assert data["results"] == []
    assert data["query_used"] == "empty query"
    assert data["time_range_applied"] is None

def test_format_search_output_body_truncated():
    """Body is truncated to 300 chars."""
    long_body = "x" * 500
    results = [{"title": "T", "href": "http://t.com", "body": long_body}]
    output = _format_search_output(results, "q", None)
    data = json.loads(output)
    assert len(data["results"][0]["body"]) == 300