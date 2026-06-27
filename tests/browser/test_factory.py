from src.browser.factory import build_browser_wrapper, selected_browser_backend
from src.browser.playwright_wrapper import PlaywrightBrowserWrapper
from src.browser.wrapper import BrowserWrapper


def test_default_browser_backend_is_playwright(monkeypatch):
    monkeypatch.delenv("BROWSER_BACKEND", raising=False)

    wrapper = build_browser_wrapper()

    assert selected_browser_backend() == "playwright"
    assert isinstance(wrapper, PlaywrightBrowserWrapper)
    wrapper.close()


def test_browser_backend_can_use_legacy_agent_browser(monkeypatch):
    monkeypatch.setenv("BROWSER_BACKEND", "agent-browser")

    wrapper = build_browser_wrapper()

    assert isinstance(wrapper, BrowserWrapper)
    wrapper.close()
