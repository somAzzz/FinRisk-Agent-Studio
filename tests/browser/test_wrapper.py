import pytest
import asyncio
from src.browser.wrapper import BrowserWrapper, BrowserResult


@pytest.fixture
def wrapper():
    w = BrowserWrapper()
    yield w
    w.close()


def test_browser_result_structure():
    result = BrowserResult(success=True, content=None, screenshot=None, url="", error=None)
    assert result["success"] is True
    assert result["url"] == ""


@pytest.mark.asyncio
async def test_navigate_invalid_url():
    wrapper = BrowserWrapper()
    result = await wrapper.navigate("ftp://invalid-scheme.com")
    assert result["success"] is False
    assert result["error"] is not None
    wrapper.close()


@pytest.mark.asyncio
async def test_navigate_valid_url_scheme():
    """Test that navigate validates http/https scheme."""
    wrapper = BrowserWrapper()
    result = await wrapper.navigate("javascript:alert(1)")
    assert result["success"] is False
    assert "http" in result["error"].lower() or "scheme" in result["error"].lower()
    wrapper.close()
