from pathlib import Path

import pytest

from src.browser.playwright_wrapper import PlaywrightBrowserWrapper


class FakeLocator:
    def __init__(self, page: "FakePage") -> None:
        self.page = page
        self.first = self

    def click(self, timeout: int) -> None:
        self.page.actions.append(("click", timeout))

    def fill(self, text: str, timeout: int) -> None:
        self.page.actions.append(("fill", text, timeout))

    def inner_text(self, timeout: int) -> str:
        self.page.actions.append(("inner_text", timeout))
        return "Apple supplier risk evidence from a rendered page."

    def wait_for(self, timeout: int) -> None:
        self.page.actions.append(("wait_for", timeout))


class FakeTextLocator(FakeLocator):
    def __init__(self, page: "FakePage", text: str) -> None:
        super().__init__(page)
        self.text = text

    def click(self, timeout: int) -> None:
        self.page.actions.append(("click_text", self.text, timeout))


class FakePage:
    def __init__(self) -> None:
        self.url = "about:blank"
        self.actions: list[tuple] = []

    def goto(self, url: str, wait_until: str, timeout: int) -> None:
        self.url = url
        self.actions.append(("goto", url, wait_until, timeout))

    def title(self) -> str:
        return "Rendered Market Page"

    def locator(self, selector: str) -> FakeLocator:
        self.actions.append(("locator", selector))
        return FakeLocator(self)

    def get_by_text(self, text: str) -> FakeTextLocator:
        self.actions.append(("get_by_text", text))
        return FakeTextLocator(self, text)

    def evaluate(self, script: str, distance: int) -> None:
        self.actions.append(("evaluate", script, distance))

    def screenshot(self, path: str, full_page: bool) -> None:
        self.actions.append(("screenshot", path, full_page))
        Path(path).write_bytes(b"fake-png")

    def content(self) -> str:
        return "<html><body>fallback html</body></html>"


class FakeContext:
    def __init__(self) -> None:
        self.page = FakePage()
        self.closed = False

    def new_page(self) -> FakePage:
        return self.page

    def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self) -> None:
        self.context = FakeContext()
        self.closed = False

    def new_context(self) -> FakeContext:
        return self.context

    def close(self) -> None:
        self.closed = True


class FakeLauncher:
    def __init__(self) -> None:
        self.browser = FakeBrowser()
        self.launch_args: dict | None = None

    def launch(self, **kwargs) -> FakeBrowser:
        self.launch_args = kwargs
        return self.browser


class FakePlaywright:
    def __init__(self) -> None:
        self.chromium = FakeLauncher()
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class FakePlaywrightFactory:
    def __init__(self) -> None:
        self.playwright = FakePlaywright()

    def start(self) -> FakePlaywright:
        return self.playwright


@pytest.mark.asyncio
async def test_playwright_wrapper_navigate_snapshot_and_actions(monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_FETCH_ALLOW_PRIVATE", "1")
    factory = FakePlaywrightFactory()
    wrapper = PlaywrightBrowserWrapper(timeout=7, headless=True, playwright_factory=factory)

    result = await wrapper.navigate("https://example.com/market")
    snapshot = wrapper.get_snapshot()
    click_result = wrapper.click("text:accept all")
    type_result = wrapper.type("#query", "AAPL suppliers")
    scroll_result = wrapper.scroll("down", 250)
    wait_result = wrapper.wait_for("#results", timeout=3)
    screenshot_path = tmp_path / "page.png"
    screenshot_result = wrapper.screenshot(str(screenshot_path))

    assert result["success"] is True
    assert result["url"] == "https://example.com/market"
    assert snapshot["success"] is True
    assert "Rendered Market Page" in snapshot["content"]
    assert "supplier risk evidence" in snapshot["content"]
    assert click_result["success"] is True
    assert type_result["success"] is True
    assert scroll_result["success"] is True
    assert wait_result["success"] is True
    assert screenshot_result["success"] is True
    assert screenshot_result["screenshot"] == "ZmFrZS1wbmc="
    assert screenshot_path.exists()
    assert factory.playwright.chromium.launch_args == {"headless": True}

    wrapper.close()
    assert factory.playwright.chromium.browser.context.closed is True
    assert factory.playwright.chromium.browser.closed is True
    assert factory.playwright.stopped is True


@pytest.mark.asyncio
async def test_playwright_wrapper_rejects_invalid_scheme_without_launching():
    factory = FakePlaywrightFactory()
    wrapper = PlaywrightBrowserWrapper(playwright_factory=factory)

    result = await wrapper.navigate("file:///etc/passwd")
    wrapper.close()

    assert result["success"] is False
    assert "scheme" in result["error"].lower()
    assert factory.playwright.chromium.launch_args is None


@pytest.mark.asyncio
async def test_playwright_wrapper_rejects_private_urls(monkeypatch):
    monkeypatch.delenv("WEB_FETCH_ALLOW_PRIVATE", raising=False)
    factory = FakePlaywrightFactory()
    wrapper = PlaywrightBrowserWrapper(playwright_factory=factory)

    result = await wrapper.navigate("http://127.0.0.1:8080")
    wrapper.close()

    assert result["success"] is False
    assert "SSRF guard" in result["error"]
    assert factory.playwright.chromium.launch_args is None
