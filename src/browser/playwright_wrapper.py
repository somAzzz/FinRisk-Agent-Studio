from __future__ import annotations

import asyncio
import base64
import os
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path
from typing import Any, Protocol

from src.browser.wrapper import BrowserResult
from src.security.url_guard import SSRFBlocked, validate_url


class _PlaywrightFactory(Protocol):
    def start(self) -> Any: ...


class PlaywrightBrowserWrapper:
    """Playwright-backed implementation of the browser wrapper interface.

    Playwright's sync API must stay outside the running asyncio event loop, so
    all browser operations run on one dedicated worker thread.
    """

    def __init__(
        self,
        timeout: int = 30,
        headless: bool = True,
        browser_type: str = "chromium",
        playwright_factory: _PlaywrightFactory | None = None,
    ) -> None:
        self.timeout = timeout
        self.headless = headless
        self.browser_type = browser_type
        self._playwright_factory = playwright_factory
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fintext-playwright")
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._context: Any | None = None
        self._page: Any | None = None
        self._current_url = ""
        self._closed = False

    async def navigate(self, url: str) -> BrowserResult:
        """Navigate to an http/https URL with SSRF validation."""
        validation_error = self._validate_url(url)
        if validation_error is not None:
            return validation_error
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self._executor, self._navigate_sync, url)
        except RuntimeError as exc:
            return self._error(f"Playwright browser unavailable: {exc}", url=url)

    def click(self, selector: str) -> BrowserResult:
        return self._call_sync(self._click_sync, selector)

    def type(self, selector: str, text: str) -> BrowserResult:
        return self._call_sync(self._type_sync, selector, text)

    def scroll(self, direction: str, pixels: int = 500) -> BrowserResult:
        return self._call_sync(self._scroll_sync, direction, pixels)

    def get_snapshot(self) -> BrowserResult:
        """Return an AI-friendly text snapshot of the current page."""
        return self._call_sync(self._snapshot_sync)

    def screenshot(self, path: str | None = None) -> BrowserResult:
        return self._call_sync(self._screenshot_sync, path)

    def wait_for(self, selector: str, timeout: int = 10) -> BrowserResult:
        return self._call_sync(self._wait_for_sync, selector, timeout)

    async def execute_batch(self, commands: list[dict[str, Any]]) -> list[BrowserResult]:
        results: list[BrowserResult] = []
        for command in commands:
            action = str(command.get("action", "")).lower()
            if action in {"navigate", "open", "goto"}:
                results.append(await self.navigate(str(command.get("url", ""))))
            elif action == "click":
                results.append(self.click(str(command.get("selector", ""))))
            elif action == "type":
                results.append(self.type(str(command.get("selector", "")), str(command.get("text", ""))))
            elif action == "scroll":
                results.append(self.scroll(str(command.get("direction", "down")), int(command.get("pixels", 500))))
            elif action == "snapshot":
                results.append(self.get_snapshot())
            elif action == "screenshot":
                path = command.get("path")
                results.append(self.screenshot(str(path) if path else None))
            else:
                results.append(self._error(f"Unsupported browser batch action: {action}"))
        return results

    def close(self) -> None:
        if self._closed:
            return
        with suppress(Exception):
            self._executor.submit(self._close_sync).result(timeout=self.timeout + 5)
        self._closed = True
        self._executor.shutdown(wait=True, cancel_futures=True)

    def _navigate_sync(self, url: str) -> BrowserResult:
        page, error = self._ensure_page()
        if page is None:
            return self._error(error or "Playwright page unavailable", url=url)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
            final_url = getattr(page, "url", "") or url
            final_validation_error = self._validate_url(final_url)
            if final_validation_error is not None:
                self._current_url = final_url
                return final_validation_error
            self._current_url = final_url
        except Exception as exc:
            return self._error(f"Navigation failed: {exc}", url=url)
        return self._ok(url=url)

    def _click_sync(self, selector: str) -> BrowserResult:
        page, error = self._ensure_page()
        if page is None:
            return self._error(error or "Playwright page unavailable")
        try:
            if selector.startswith("text:"):
                page.get_by_text(selector.split(":", 1)[1]).click(timeout=self.timeout * 1000)
            else:
                page.locator(selector).first.click(timeout=self.timeout * 1000)
            self._current_url = getattr(page, "url", "") or self._current_url
        except Exception as exc:
            return self._error(f"Click failed: {exc}")
        return self._ok()

    def _type_sync(self, selector: str, text: str) -> BrowserResult:
        page, error = self._ensure_page()
        if page is None:
            return self._error(error or "Playwright page unavailable")
        try:
            page.locator(selector).first.fill(text, timeout=self.timeout * 1000)
            self._current_url = getattr(page, "url", "") or self._current_url
        except Exception as exc:
            return self._error(f"Type failed: {exc}")
        return self._ok()

    def _scroll_sync(self, direction: str, pixels: int = 500) -> BrowserResult:
        page, error = self._ensure_page()
        if page is None:
            return self._error(error or "Playwright page unavailable")
        distance = -abs(pixels) if direction.lower() == "up" else abs(pixels)
        try:
            page.evaluate("distance => window.scrollBy(0, distance)", distance)
            self._current_url = getattr(page, "url", "") or self._current_url
        except Exception as exc:
            return self._error(f"Scroll failed: {exc}")
        return self._ok()

    def _snapshot_sync(self) -> BrowserResult:
        page, error = self._ensure_page()
        if page is None:
            return self._error(error or "Playwright page unavailable")
        try:
            title = page.title()
            self._current_url = getattr(page, "url", "") or self._current_url
            content = page.locator("body").inner_text(timeout=min(self.timeout * 1000, 5000))
            snapshot = f"# {title}\n\nURL: {self._current_url}\n\n{content}"
        except Exception as exc:
            try:
                snapshot = page.content()
                self._current_url = getattr(page, "url", "") or self._current_url
            except Exception:
                return self._error(f"Snapshot failed: {exc}")
        return BrowserResult(
            success=True,
            content=snapshot,
            screenshot=None,
            url=self._current_url,
            error=None,
        )

    def _screenshot_sync(self, path: str | None = None) -> BrowserResult:
        page, error = self._ensure_page()
        if page is None:
            return self._error(error or "Playwright page unavailable")
        remove_after_read = path is None
        if path is None:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                path = temp_file.name
        try:
            page.screenshot(path=path, full_page=True)
            screenshot_data = base64.b64encode(Path(path).read_bytes()).decode()
            self._current_url = getattr(page, "url", "") or self._current_url
        except Exception as exc:
            return self._error(f"Screenshot failed: {exc}")
        finally:
            if remove_after_read and path:
                Path(path).unlink(missing_ok=True)
        return BrowserResult(
            success=True,
            content=None,
            screenshot=screenshot_data,
            url=self._current_url,
            error=None,
        )

    def _wait_for_sync(self, selector: str, timeout: int = 10) -> BrowserResult:
        page, error = self._ensure_page()
        if page is None:
            return self._error(error or "Playwright page unavailable")
        try:
            page.locator(selector).first.wait_for(timeout=timeout * 1000)
            self._current_url = getattr(page, "url", "") or self._current_url
        except Exception as exc:
            return self._error(f"Wait failed: {exc}")
        return self._ok()

    def _ensure_page(self) -> tuple[Any | None, str | None]:
        if self._page is not None:
            return self._page, None
        try:
            self._playwright = self._start_playwright()
            launcher = getattr(self._playwright, self.browser_type)
            self._browser = launcher.launch(headless=self.headless)
            self._context = self._browser.new_context()
            self._page = self._context.new_page()
        except Exception as exc:
            self._close_sync()
            return None, (
                f"Playwright browser unavailable: {exc}. "
                "Run `uv run playwright install chromium` once to install browser binaries."
            )
        return self._page, None

    def _start_playwright(self) -> Any:
        if self._playwright_factory is not None:
            return self._playwright_factory.start()
        from playwright.sync_api import sync_playwright

        return sync_playwright().start()

    def _close_sync(self) -> None:
        for resource in (self._context, self._browser):
            if resource is None:
                continue
            with suppress(Exception):
                resource.close()
        if self._playwright is not None:
            with suppress(Exception):
                self._playwright.stop()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    def _call_sync(self, operation: Callable[..., BrowserResult], *args: Any) -> BrowserResult:
        if self._closed:
            return self._error("Playwright browser is closed")
        try:
            return self._executor.submit(operation, *args).result(timeout=self.timeout + 5)
        except Exception as exc:
            return self._error(f"Playwright browser operation failed: {exc}")

    def _validate_url(self, url: str) -> BrowserResult | None:
        if not url.startswith(("http://", "https://")):
            return BrowserResult(
                success=False,
                content=None,
                screenshot=None,
                url="",
                error=f"Invalid URL scheme: {url}. Must start with http:// or https://",
            )
        if os.environ.get("WEB_FETCH_ALLOW_PRIVATE") == "1":
            return None
        try:
            validate_url(url)
        except SSRFBlocked as exc:
            return BrowserResult(
                success=False,
                content=None,
                screenshot=None,
                url=url,
                error=f"SSRF guard: {exc.reason} ({exc.host})",
            )
        return None

    def _ok(self, *, url: str | None = None) -> BrowserResult:
        return BrowserResult(
            success=True,
            content=None,
            screenshot=None,
            url=self._current_url or url or "",
            error=None,
        )

    def _error(self, error: str, *, url: str | None = None) -> BrowserResult:
        return BrowserResult(
            success=False,
            content=None,
            screenshot=None,
            url=url or self._current_url,
            error=error,
        )


__all__ = ["PlaywrightBrowserWrapper"]
