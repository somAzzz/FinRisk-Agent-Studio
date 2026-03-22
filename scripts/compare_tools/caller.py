"""Tool calling layer - calls both project tools and Claude Code."""

import asyncio
import re
import subprocess
import time
from abc import ABC, abstractmethod

from scripts.compare_tools.models import ToolResult


TIMEOUT_SECONDS = 60
ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def _strip_ansi(text: str) *********REMOVED********* str:
    """Strip ANSI escape codes from text."""
    return ANSI_ESCAPE.sub('', text)


class ToolCaller(ABC):
    """Abstract base for tool callers."""

    @abstractmethod
    def call_web_search(self, query: str) *********REMOVED********* ToolResult:
        """Call web_search tool."""
        pass

    @abstractmethod
    def call_web_fetch(self, url: str) *********REMOVED********* ToolResult:
        """Call web_fetch tool."""
        pass


class ProjectCaller(ToolCaller):
    """Calls project tools directly."""

    def call_web_search(self, query: str) *********REMOVED********* ToolResult:
        """Call project's web_search function."""
        start = time.monotonic()
        try:
            from src.tools.web_search import web_search
            output = web_search(query)
            duration = time.monotonic() - start
            return ToolResult(
                tool_name="project",
                output=output,
                duration_seconds=duration,
                success=True,
                error=None
            )
        except Exception as e:
            duration = time.monotonic() - start
            return ToolResult(
                tool_name="project",
                output="",
                duration_seconds=duration,
                success=False,
                error=str(e)
            )

    def call_web_fetch(self, url: str) *********REMOVED********* ToolResult:
        """Call project's web_fetch function."""
        start = time.monotonic()
        try:
            from src.tools.web_fetch import web_fetch_sync
            result = web_fetch_sync(url)
            duration = time.monotonic() - start
            # Convert WebFetchResult to string output
            if result.status == "success":
                output = f"# {result.title or 'Untitled'}\n\n{result.content}"
            else:
                output = f"Error: {result.error_code} - {result.error_message}"
            return ToolResult(
                tool_name="project",
                output=output,
                duration_seconds=duration,
                success=result.status == "success",
                error=result.error_code if result.status != "success" else None
            )
        except Exception as e:
            duration = time.monotonic() - start
            return ToolResult(
                tool_name="project",
                output="",
                duration_seconds=duration,
                success=False,
                error=str(e)
            )


class ClaudeCodeCaller(ToolCaller):
    """Calls Claude Code CLI via subprocess."""

    def call_web_search(self, query: str) *********REMOVED********* ToolResult:
        """Call Claude Code web_search via subprocess."""
        start = time.monotonic()
        try:
            result = subprocess.run(
                ["claude", "-m", f"web_search: {query}", "--output-format", "stream-json"],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS
            )
            duration = time.monotonic() - start

            if result.returncode != 0:
                # Fallback: try plain text
                return self._call_plain_text_fallback(
                    ["claude", "-m", f"web_search: {query}"],
                    "project",
                    start
                )

            # Parse JSON from stream-json output
            output = self._parse_stream_json(result.stdout)
            return ToolResult(
                tool_name="claude_code",
                output=output,
                duration_seconds=duration,
                success=True,
                error=None
            )
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start
            return ToolResult(
                tool_name="claude_code",
                output="",
                duration_seconds=duration,
                success=False,
                error="TIMEOUT"
            )
        except FileNotFoundError:
            duration = time.monotonic() - start
            return ToolResult(
                tool_name="claude_code",
                output="",
                duration_seconds=duration,
                success=False,
                error="CLAUDE_CLI_NOT_FOUND"
            )
        except Exception as e:
            duration = time.monotonic() - start
            return ToolResult(
                tool_name="claude_code",
                output="",
                duration_seconds=duration,
                success=False,
                error=str(e)
            )

    def call_web_fetch(self, url: str) *********REMOVED********* ToolResult:
        """Call Claude Code web_fetch via subprocess."""
        start = time.monotonic()
        try:
            result = subprocess.run(
                ["claude", "-m", f"web_fetch: {url}", "--output-format", "stream-json"],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS
            )
            duration = time.monotonic() - start

            if result.returncode != 0:
                return self._call_plain_text_fallback(
                    ["claude", "-m", f"web_fetch: {url}"],
                    "claude_code",
                    start
                )

            output = self._parse_stream_json(result.stdout)
            return ToolResult(
                tool_name="claude_code",
                output=output,
                duration_seconds=duration,
                success=True,
                error=None
            )
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start
            return ToolResult(
                tool_name="claude_code",
                output="",
                duration_seconds=duration,
                success=False,
                error="TIMEOUT"
            )
        except FileNotFoundError:
            duration = time.monotonic() - start
            return ToolResult(
                tool_name="claude_code",
                output="",
                duration_seconds=duration,
                success=False,
                error="CLAUDE_CLI_NOT_FOUND"
            )
        except Exception as e:
            duration = time.monotonic() - start
            return ToolResult(
                tool_name="claude_code",
                output="",
                duration_seconds=duration,
                success=False,
                error=str(e)
            )

    def _call_plain_text_fallback(
        self, cmd: list[str], tool_name: str, start: float
    ) *********REMOVED********* ToolResult:
        """Fallback to plain text output when stream-json fails."""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS
            )
            duration = time.monotonic() - start
            # Strip ANSI codes from output
            output = _strip_ansi(result.stdout)
            return ToolResult(
                tool_name=tool_name,
                output=output,
                duration_seconds=duration,
                success=result.returncode == 0,
                error=None if result.returncode == 0 else "FALLBACK_FAILED"
            )
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start
            return ToolResult(
                tool_name=tool_name,
                output="",
                duration_seconds=duration,
                success=False,
                error="TIMEOUT"
            )

    def _parse_stream_json(self, stdout: str) *********REMOVED********* str:
        """Parse stream-json output from Claude CLI."""
        # Each line is a JSON object with type and content
        # For tool results, we want the final output
        output_parts = []
        for line in stdout.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            try:
                import json
                obj = json.loads(line)
                if obj.get('type') == 'content' and 'text' in obj:
                    output_parts.append(obj['text'])
                elif obj.get('type') == 'result':
                    output_parts.append(str(obj.get('content', '')))
            except json.JSONDecodeError:
                # If it's not JSON, treat as plain text
                output_parts.append(line)
        return '\n'.join(output_parts) if output_parts else stdout