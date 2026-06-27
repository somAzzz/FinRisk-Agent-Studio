from __future__ import annotations

import os
from typing import Any

from src.browser.config import BrowserConfig
from src.browser.playwright_wrapper import PlaywrightBrowserWrapper
from src.browser.wrapper import BrowserWrapper


def selected_browser_backend() -> str:
    return os.environ.get("BROWSER_BACKEND", "playwright").strip().lower()


def build_browser_wrapper(*, browser_config: BrowserConfig | None = None) -> Any:
    config = browser_config or BrowserConfig()
    backend = selected_browser_backend()
    if backend in {"agent-browser", "agent_browser"}:
        return BrowserWrapper(timeout=config.timeout, headless=config.headless)
    return PlaywrightBrowserWrapper(timeout=config.timeout, headless=config.headless)


__all__ = ["build_browser_wrapper", "selected_browser_backend"]
