import asyncio
import base64
import json
import subprocess
import tempfile
from typing import Any, TypedDict

from src.browser.config import BrowserConfig


class BrowserResult(TypedDict):
    success: bool
    content: str | None
    screenshot: str | None
    url: str
    error: str | None


class BrowserWrapper:
    def __init__(
        self,
        timeout: int = 30,
        headless: bool = True,
    ):
        self.timeout = timeout
        self.headless = headless
        self._process: subprocess.Popen | None = None

    def _run_command(self, *args: str) *********REMOVED********* dict[str, Any]:
        """Run agent-browser command and parse JSON output."""
        result = subprocess.run(
            ["agent-browser"] + list(args),
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"success": False, "error": f"Invalid JSON: {result.stdout[:200]}", "data": {}}

    async def navigate(self, url: str) *********REMOVED********* BrowserResult:
        """Navigate to URL."""
        if not url.startswith(("http://", "https://")):
            return BrowserResult(
                success=False,
                content=None,
                screenshot=None,
                url="",
                error=f"Invalid URL scheme: {url}. Must start with http:// or https://",
            )
        output = self._run_command("goto", url)
        return BrowserResult(
            success=output.get("success", False),
            content=None,
            screenshot=None,
            url=output.get("data", {}).get("url", url),
            error=output.get("error"),
        )

    def click(self, selector: str) *********REMOVED********* BrowserResult:
        output = self._run_command("click", selector)
        return BrowserResult(
            success=output.get("success", False),
            content=None,
            screenshot=None,
            url=output.get("data", {}).get("url", ""),
            error=output.get("error"),
        )

    def type(self, selector: str, text: str) *********REMOVED********* BrowserResult:
        output = self._run_command("type", selector, text)
        return BrowserResult(
            success=output.get("success", False),
            content=None,
            screenshot=None,
            url=output.get("data", {}).get("url", ""),
            error=output.get("error"),
        )

    def scroll(self, direction: str, pixels: int = 500) *********REMOVED********* BrowserResult:
        output = self._run_command("scroll", direction, str(pixels))
        return BrowserResult(
            success=output.get("success", False),
            content=None,
            screenshot=None,
            url="",
            error=output.get("error"),
        )

    def get_snapshot(self) *********REMOVED********* BrowserResult:
        """Returns AI-friendly accessibility tree as markdown."""
        output = self._run_command("snapshot")
        return BrowserResult(
            success=output.get("success", False),
            content=output.get("data", {}).get("content", ""),
            screenshot=None,
            url=output.get("data", {}).get("url", ""),
            error=output.get("error"),
        )

    def screenshot(self, path: str | None = None) *********REMOVED********* BrowserResult:
        if path is None:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                path = f.name
        output = self._run_command("screenshot", "--path", path)
        screenshot_data = None
        if output.get("success") and path:
            try:
                with open(path, "rb") as f:
                    screenshot_data = base64.b64encode(f.read()).decode()
            except Exception:
                pass
        return BrowserResult(
            success=output.get("success", False),
            content=None,
            screenshot=screenshot_data,
            url=output.get("data", {}).get("url", ""),
            error=output.get("error"),
        )

    def wait_for(self, selector: str, timeout: int = 10) *********REMOVED********* BrowserResult:
        output = self._run_command("wait", selector, str(timeout))
        return BrowserResult(
            success=output.get("success", False),
            content=None,
            screenshot=None,
            url="",
            error=output.get("error"),
        )

    async def execute_batch(self, commands: list[dict]) *********REMOVED********* list[BrowserResult]:
        """Execute multiple commands in batch via stdin JSON."""
        proc = await asyncio.create_subprocess_exec(
            "agent-browser", "batch",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate(input=json.dumps(commands).encode())
        try:
            results = json.loads(stdout.decode())
            return [BrowserResult(**r) for r in results]
        except Exception as e:
            return [BrowserResult(success=False, content=None, screenshot=None, url="", error=str(e))]

    def close(self) *********REMOVED********* None:
        """Clean up browser resources."""
        if self._process:
            self._process.terminate()
            self._process = None
