import pytest
from src.browser.sanitize import sanitize_snapshot, SENSITIVE_PATTERNS


def test_sanitize_ssn():
    text = "My SSN is 123-45-6789"
    result = sanitize_snapshot(text)
    assert "123-45-6789" not in result
    assert "[SSN]" in result


def test_sanitize_email():
    text = "Contact me at john.doe@example.com"
    result = sanitize_snapshot(text)
    assert "john.doe@example.com" not in result
    assert "[EMAIL]" in result


def test_sanitize_api_key():
    # OpenAI API keys are exactly 48 chars after "sk-"
    key_48_chars = "a" * 48
    text = f"API key: sk-{key_48_chars}"
    result = sanitize_snapshot(text)
    assert f"sk-{key_48_chars}" not in result
    assert "[API_KEY]" in result


def test_sanitize_phone():
    text = "Call me at 555-123-4567"
    result = sanitize_snapshot(text)
    assert "555-123-4567" not in result
    assert "[PHONE]" in result


def test_sanitize_credit_card():
    text = "Card: 1234 5678 9012 3456"
    result = sanitize_snapshot(text)
    assert "1234 5678 9012 3456" not in result
    assert "[CARD]" in result


def test_sanitize_slack_token():
    token = "xoxb-" + "a" * 20
    text = f"Slack token: {token}"
    result = sanitize_snapshot(text)
    assert token not in result
    assert "[TOKEN]" in result
