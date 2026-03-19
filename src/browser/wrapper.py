import asyncio
import base64
import json
import re
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
        self._current_url: str = ""

    def _strip_ansi(self, text: str) *********REMOVED********* str:
        """Remove ANSI escape sequences from text."""
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        return ansi_escape.sub("", text)

    def _run_command(self, *args: str) *********REMOVED********* tuple[bool, str, str]:
        """Run agent-browser command.

        Returns:
            (success, output, url)
        """
        result = subprocess.run(
            ["agent-browser"] + list(args),
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )
        output = result.stdout.strip()
        clean_output = self._strip_ansi(output)
        command = args[0] if args else ""

        # Success detection varies by command:
        # - open/goto/click/type/scroll: starts with ✓
        # - snapshot: output is accessibility tree, non-empty = success
        # - screenshot: non-empty = success
        if command == "snapshot":
            success = len(output) > 0
        elif command in ("screenshot", "pdf"):
            success = len(output) > 0 or result.returncode == 0
        else:
            success = clean_output.startswith("✓")

        # Get current URL
        url_result = subprocess.run(
            ["agent-browser", "get", "url"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        self._current_url = url_result.stdout.strip()
        return success, output, self._current_url

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
        success, output, current_url = self._run_command("open", url)
        if not success:
            # Extract URL from output if present
            url_match = re.search(r"https?://[^\s]+", output)
            extracted_url = url_match.group() if url_match else url
            return BrowserResult(
                success=False,
                content=None,
                screenshot=None,
                url=extracted_url,
                error=f"Navigation failed: {output[:200]}",
            )
        return BrowserResult(
            success=True,
            content=None,
            screenshot=None,
            url=current_url or url,
            error=None,
        )

    def click(self, selector: str) *********REMOVED********* BrowserResult:
        success, output, url = self._run_command("click", selector)
        if not success:
            return BrowserResult(
                success=False,
                content=None,
                screenshot=None,
                url=url,
                error=f"Click failed: {output[:200]}",
            )
        return BrowserResult(
            success=True,
            content=None,
            screenshot=None,
            url=url,
            error=None,
        )

    def type(self, selector: str, text: str) *********REMOVED********* BrowserResult:
        success, output, url = self._run_command("type", selector, text)
        if not success:
            return BrowserResult(
                success=False,
                content=None,
                screenshot=None,
                url=url,
                error=f"Type failed: {output[:200]}",
            )
        return BrowserResult(
            success=True,
            content=None,
            screenshot=None,
            url=url,
            error=None,
        )

    def scroll(self, direction: str, pixels: int = 500) *********REMOVED********* BrowserResult:
        success, output, url = self._run_command("scroll", direction, str(pixels))
        return BrowserResult(
            success=success,
            content=None,
            screenshot=None,
            url=url,
            error=None if success else output[:200],
        )

    def get_snapshot(self) *********REMOVED********* BrowserResult:
        """Returns AI-friendly accessibility tree."""
        success, output, url = self._run_command("snapshot")
        if not success:
            return BrowserResult(
                success=False,
                content=None,
                screenshot=None,
                url=url,
                error=f"Snapshot failed: {output[:200]}",
            )
        return BrowserResult(
            success=True,
            content=output,
            screenshot=None,
            url=url,
            error=None,
        )

    def screenshot(self, path: str | None = None) *********REMOVED********* BrowserResult:
        if path is None:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                path = f.name
        success, output, url = self._run_command("screenshot", path)
        screenshot_data = None
        if success:
            try:
                with open(path, "rb") as f:
                    screenshot_data = base64.b64encode(f.read()).decode()
            except Exception:
                pass
        return BrowserResult(
            success=success,
            content=None,
            screenshot=screenshot_data,
            url=url,
            error=None if success else output[:200],
        )

    def wait_for(self, selector: str, timeout: int = 10) *********REMOVED********* BrowserResult:
        success, output, url = self._run_command("wait", selector, str(timeout))
        return BrowserResult(
            success=success,
            content=None,
            screenshot=None,
            url=url,
            error=None if success else output[:200],
        )

    async def execute_batch(self, commands: list[dict]) *********REMOVED********* list[BrowserResult]:
        """Execute multiple commands in batch."""
        proc = await asyncio.create_subprocess_exec(
            "agent-browser", "batch",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate(input="\n".join(
            json.dumps(c) for c in commands
        ).encode())
        try:
            results = []
            for line in stdout.decode().strip().split("\n"):
                if line.strip():
                    results.append(BrowserResult(**json.loads(line)))
            return results
        except Exception:
            return [BrowserResult(success=False, content=None, screenshot=None, url="", error="Batch failed")]

    def close(self) *********REMOVED********* None:
        """Clean up browser resources."""
        subprocess.run(["agent-browser", "close"], capture_output=True, timeout=5)
        if self._process:
            self._process.terminate()
            self._process = None
