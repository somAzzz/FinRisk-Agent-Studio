# Browser Exploration Integration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate agent-browser CLI with FinText-LLM to enable LLM-driven web exploration for financial research.

**Architecture:** Python CLI wrapper (BrowserWrapper) + LLM agent (MarketExplorer) + checkpoint mechanism. agent-browser handles headless Chrome; Python wraps CLI and provides async execution, novelty detection, and checkpoint callbacks.

**Tech Stack:** Python 3.12, subprocess/asyncio, sentence-transformers, numpy, agent-browser CLI

---

## File Structure

```
src/
├── browser/                      # NEW
│   ├── __init__.py               # Exports BrowserWrapper, MarketExplorer, config
│   ├── config.py                 # BrowserConfig, ExplorationConfig dataclasses
│   ├── wrapper.py                # BrowserWrapper class (CLI wrapper)
│   └── explorer.py               # MarketExplorer class (LLM agent)
├── llm/
│   └── client.py                 # MODIFIED: add complete(), compute_embedding()
```

**Key interfaces:**
- `BrowserWrapper` - sync/async CLI wrapper returning `BrowserResult`
- `MarketExplorer` - async exploration with checkpoint callbacks
- `EdgarLLMClient.complete()` - general-purpose chat completion
- `EdgarLLMClient.compute_embedding()` - text embedding via sentence-transformers

---

## Chunk 1: Configuration Module

**Files:**
- Create: `src/browser/config.py`
- Test: `tests/browser/test_config.py` (create directory)

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p tests/browser
touch tests/browser/__init__.py
```

- [ ] **Step 2: Write failing test for BrowserConfig**

```python
# tests/browser/test_config.py
import pytest
from src.browser.config import BrowserConfig, ExplorationConfig

def test_browser_config_defaults():
    config = BrowserConfig()
    assert config.timeout == 30
    assert config.checkpoint_interval == 5
    assert config.max_steps == 20
    assert config.headless is True

def test_exploration_config_defaults():
    config = ExplorationConfig()
    assert config.novelty_threshold == 0.85
    assert config.no_new_findings_limit == 3
    assert config.error_rate_threshold == 0.5
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/browser/test_config.py -v`
Expected: FAIL - module not found

- [ ] **Step 4: Create minimal config.py**

```python
# src/browser/config.py
from dataclasses import dataclass

@dataclass
class BrowserConfig:
    timeout: int = 30
    checkpoint_interval: int = 5
    max_steps: int = 20
    headless: bool = True

@dataclass
class ExplorationConfig:
    novelty_threshold: float = 0.85
    no_new_findings_limit: int = 3
    error_rate_threshold: float = 0.5
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/browser/test_config.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/browser/config.py tests/browser/
git commit -m "feat(browser): add config dataclasses for browser module"
```

---

## Chunk 2: BrowserWrapper (CLI Wrapper)

**Files:**
- Create: `src/browser/wrapper.py`
- Test: `tests/browser/test_wrapper.py`
- Modify: `src/browser/__init__.py`

- [ ] **Step 1: Write failing test for BrowserWrapper basic operations**

```python
# tests/browser/test_wrapper.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/browser/test_wrapper.py -v`
Expected: FAIL - module not found

- [ ] **Step 3: Write minimal wrapper.py with BrowserResult and error handling**

```python
# src/browser/wrapper.py
import asyncio
import json
import subprocess
from typing import Any, TypedDict

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

    def close(self) *********REMOVED********* None:
        """Clean up browser resources."""
        if self._process:
            self._process.terminate()
            self._process = None
```

- [ ] **Step 3b: Run test to verify it fails on URL validation**

Run: `pytest tests/browser/test_wrapper.py::test_navigate_invalid_url -v`
Expected: PASS (URL validation works)

- [ ] **Step 4: Run full test suite to check current state**

Run: `pytest tests/browser/test_wrapper.py -v`
Expected: Some passes (URL validation), some may fail (CLI not installed)

- [ ] **Step 5: Add remaining wrapper methods (click, type, scroll, get_snapshot, screenshot, wait_for, execute_batch)**

```python
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
        import tempfile
        if path is None:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                path = f.name
        output = self._run_command("screenshot", "--path", path)
        import base64
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
```

- [ ] **Step 6: Update __init__.py**

```python
# src/browser/__init__.py
from src.browser.config import BrowserConfig, ExplorationConfig
from src.browser.wrapper import BrowserWrapper, BrowserResult

__all__ = ["BrowserConfig", "ExplorationConfig", "BrowserWrapper", "BrowserResult"]
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/browser/test_wrapper.py -v`
Expected: PASS (with skipped tests if CLI not installed)

- [ ] **Step 8: Commit**

```bash
git add src/browser/wrapper.py src/browser/config.py src/browser/__init__.py tests/browser/
git commit -m "feat(browser): add BrowserWrapper CLI wrapper"
```

---

## Chunk 3: Extend EdgarLLMClient

**Files:**
- Modify: `src/llm/client.py`
- Test: `tests/llm/test_client.py`

- [ ] **Step 1: Write failing test for new methods**

```python
# tests/llm/test_client.py (add to existing or create)
import pytest
from src.llm.client import EdgarLLMClient

def test_complete_method_exists():
    client = EdgarLLMClient()
    assert hasattr(client, "complete")
    assert callable(client.complete)

def test_compute_embedding_method_exists():
    client = EdgarLLMClient()
    assert hasattr(client, "compute_embedding")
    assert callable(client.compute_embedding)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/llm/test_client.py::test_complete_method_exists -v`
Expected: FAIL - method not found

- [ ] **Step 3: Add complete() and compute_embedding() to EdgarLLMClient**

Add these methods to `src/llm/client.py`:

```python
def complete(
    self,
    prompt: str,
    system: str | None = None,
    max_tokens: int = 2048,
    temperature: float = 0.3,
) *********REMOVED********* str:
    """General-purpose chat completion for browser exploration."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    response = self.client.chat.completions.create(
        model=self.model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content

def compute_embedding(self, text: str) *********REMOVED********* list[float]:
    """Compute text embedding for novelty detection.

    Uses sentence-transformers/all-MiniLM-L6-v2 for fast, local embedding.
    """
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")
    return model.encode(text).tolist()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/llm/test_client.py::test_complete_method_exists tests/llm/test_client.py::test_compute_embedding_method_exists -v`
Expected: PASS

- [ ] **Step 5: Add sentence-transformers to dependencies in pyproject.toml**

```toml
dependencies = [
    # ... existing ...
    "sentence-transformers>=3.0.0",
]
```

- [ ] **Step 6: Commit**

```bash
git add src/llm/client.py pyproject.toml
git commit -m "feat(llm): add complete() and compute_embedding() for browser exploration"
```

---

## Chunk 4: MarketExplorer (LLM Agent)

**Files:**
- Create: `src/browser/explorer.py`
- Test: `tests/browser/test_explorer.py`
- Modify: `src/browser/__init__.py`

- [ ] **Step 1: Write failing test for MarketExplorer**

```python
# tests/browser/test_explorer.py
import pytest
from datetime import datetime
from src.browser.explorer import Finding, ExplorationState, MarketExplorer
from src.browser.wrapper import BrowserWrapper

def test_finding_dataclass():
    f = Finding(
        url="https://example.com",
        content_hash="abc123",
        summary="Test summary",
        timestamp=datetime.now(),
        source_type="news",
    )
    assert f.url == "https://example.com"
    assert f.source_type == "news"

def test_exploration_state_dataclass():
    state = ExplorationState(
        goal="Test exploration",
        findings=[],
        visited_urls=set(),
        current_step=0,
        last_discovery=datetime.now(),
    )
    assert state.goal == "Test exploration"
    assert len(state.findings) == 0

@pytest.mark.asyncio
async def test_market_explorer_init():
    wrapper = BrowserWrapper()
    from src.llm.client import EdgarLLMClient
    client = EdgarLLMClient()
    explorer = MarketExplorer(client, wrapper)
    assert explorer.llm_client is not None
    assert explorer.wrapper is not None
    wrapper.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/browser/test_explorer.py -v`
Expected: FAIL - module not found

- [ ] **Step 3: Create explorer.py with Finding, ExplorationState, MarketExplorer**

```python
# src/browser/explorer.py
import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from src.llm.client import EdgarLLMClient
from src.browser.wrapper import BrowserWrapper
from src.browser.config import BrowserConfig, ExplorationConfig

@dataclass
class Finding:
    url: str
    content_hash: str
    summary: str
    timestamp: datetime
    source_type: str = "other"  # news | financial | regulatory | other

@dataclass
class ExplorationState:
    goal: str
    findings: list[Finding] = field(default_factory=list)
    visited_urls: set[str] = field(default_factory=set)
    current_step: int = 0
    last_discovery: datetime = field(default_factory=datetime.now)

class MarketExplorer:
    def __init__(
        self,
        llm_client: EdgarLLMClient,
        wrapper: BrowserWrapper,
        browser_config: BrowserConfig | None = None,
        exploration_config: ExplorationConfig | None = None,
    ):
        self.llm_client = llm_client
        self.wrapper = wrapper
        self.browser_config = browser_config or BrowserConfig()
        self.exploration_config = exploration_config or ExplorationConfig()
        self._recent_embeddings: list[list[float]] = []

    def _compute_hash(self, text: str) *********REMOVED********* str:
        """Compute SHA256 hash of text (first 10KB)."""
        return hashlib.sha256(text[:10240].encode()).hexdigest()

    def _compute_similarity(self, a: list[float], b: list[float]) *********REMOVED********* float:
        """Compute cosine similarity between two vectors."""
        import numpy as np
        a_arr = np.array(a)
        b_arr = np.array(b)
        return np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr))

    async def explore(
        self,
        goal: str,
        checkpoint_callback: Callable[[ExplorationState], bool] | None = None,
    ) *********REMOVED********* ExplorationState:
        """Execute exploration goal.

        Args:
            goal: Exploration objective
            checkpoint_callback: Returns True to continue, False to stop.
                Called every checkpoint_interval steps.

        Returns:
            ExplorationState with findings and metadata
        """
        state = ExplorationState(goal=goal)

        system_prompt = """You are a financial research assistant. Given an exploration goal,
explore web pages to find relevant information. Use the browser tools to navigate,
read content, and make decisions about what to explore next.

Respond with your next action in JSON format:
{"action": "navigate|click|type|scroll|snapshot|stop", "args": {...}}

When you have gathered enough information, respond with:
{"action": "stop", "reason": "summary of findings"}"""

        while state.current_step < self.browser_config.max_steps:
            state.current_step += 1

            # Get current page content
            snapshot_result = self.wrapper.get_snapshot()
            if not snapshot_result["success"]:
                continue

            content = snapshot_result.get("content", "")
            if not content:
                continue

            # Check for duplicates via hash
            content_hash = self._compute_hash(content)
            if content_hash in {f.content_hash for f in state.findings}:
                continue

            # Generate summary using LLM
            summary = self.llm_client.complete(
                prompt=f"Summarize this page briefly (2-3 sentences):\n\n{content[:5000]}",
                system="You are a financial analyst. Provide concise summaries.",
                max_tokens=256,
            )

            # Check novelty via embedding
            embedding = self.llm_client.compute_embedding(summary)
            is_new = True
            for recent_emb in self._recent_embeddings[-3:]:
                if self._compute_similarity(embedding, recent_emb) >= self.exploration_config.novelty_threshold:
                    is_new = False
                    break

            if is_new:
                finding = Finding(
                    url=snapshot_result.get("url", ""),
                    content_hash=content_hash,
                    summary=summary,
                    timestamp=datetime.now(),
                )
                state.findings.append(finding)
                state.last_discovery = datetime.now()
                self._recent_embeddings.append(embedding)

            # Check stopping conditions
            steps_since_discovery = state.current_step - len(state.findings)
            if steps_since_discovery >= self.exploration_config.no_new_findings_limit:
                break

            # Checkpoint
            if checkpoint_callback and state.current_step % self.browser_config.checkpoint_interval == 0:
                if not checkpoint_callback(state):
                    break

            # Random delay to respect rate limits
            import random
            await asyncio.sleep(random.uniform(1, 3))

        return state
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/browser/test_explorer.py -v`
Expected: PASS

- [ ] **Step 5: Update __init__.py**

```python
# src/browser/__init__.py
from src.browser.config import BrowserConfig, ExplorationConfig
from src.browser.wrapper import BrowserWrapper, BrowserResult
from src.browser.explorer import Finding, ExplorationState, MarketExplorer

__all__ = [
    "BrowserConfig",
    "ExplorationConfig",
    "BrowserWrapper",
    "BrowserResult",
    "Finding",
    "ExplorationState",
    "MarketExplorer",
]
```

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/browser/ tests/llm/test_client.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/browser/explorer.py src/browser/__init__.py tests/browser/test_explorer.py
git commit -m "feat(browser): add MarketExplorer LLM agent with novelty detection"
```

---

## Chunk 5: Sensitive Data Filter & Utilities

**Files:**
- Create: `src/browser/sanitize.py`
- Test: `tests/browser/test_sanitize.py`
- Modify: `src/browser/explorer.py` (use sanitize)

- [ ] **Step 1: Write failing test for sanitize**

```python
# tests/browser/test_sanitize.py
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
    text = "API key: sk-1234567890abcdefghijklmnopqrstuvwxyz"
    result = sanitize_snapshot(text)
    assert "sk-1234567890abcdef" not in result
    assert "[API_KEY]" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/browser/test_sanitize.py -v`
Expected: FAIL - module not found

- [ ] **Step 3: Create sanitize.py**

```python
# src/browser/sanitize.py
import re

SENSITIVE_PATTERNS = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "[SSN]"),
    (r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b", "[CARD]"),
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[EMAIL]"),
    (r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b", "[PHONE]"),
    (r"sk-[A-Za-z0-9]{48}", "[API_KEY]"),
    (r"xox[baprs]-[A-Za-z0-9]{10,}", "[TOKEN]"),
]

def sanitize_snapshot(text: str) *********REMOVED********* str:
    """Remove sensitive data patterns from page snapshots."""
    for pattern, replacement in SENSITIVE_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/browser/test_sanitize.py -v`
Expected: PASS

- [ ] **Step 5: Integrate sanitize into explorer**

In `explorer.py`, update the `explore()` method to call sanitize before processing:
```python
# In explore() method, after get_snapshot():
content = sanitize_snapshot(snapshot_result.get("content", ""))
```

- [ ] **Step 6: Commit**

```bash
git add src/browser/sanitize.py tests/browser/test_sanitize.py
git commit -m "feat(browser): add sensitive data sanitization"
```

---

## Chunk 6: Integration Test

**Files:**
- Create: `tests/browser/test_integration.py`

- [ ] **Step 1: Write integration test (requires agent-browser CLI)**

```python
# tests/browser/test_integration.py
import pytest
import asyncio
from src.browser import BrowserWrapper, MarketExplorer
from src.llm.client import EdgarLLMClient

@pytest.mark.skipif(
    asyncio.get_event_loop().run_until_complete(_check_agent_browser()) is False,
    reason="agent-browser CLI not installed"
)
@pytest.mark.asyncio
async def test_end_to_end_exploration():
    wrapper = BrowserWrapper()
    client = EdgarLLMClient()
    explorer = MarketExplorer(client, wrapper)

    checkpoint_calls = []
    def checkpoint_handler(state):
        checkpoint_calls.append(state.current_step)
        return len(checkpoint_calls) < 2  # Stop after 2 checkpoints

    result = await explorer.explore(
        goal="Find information about Apple's latest earnings",
        checkpoint_callback=checkpoint_handler,
    )

    assert result.goal == "Find information about Apple's latest earnings"
    assert result.current_step > 0
    assert len(checkpoint_calls) >= 1

    wrapper.close()

async def _check_agent_browser():
    import shutil
    return shutil.which("agent-browser") is not None
```

- [ ] **Step 2: Commit**

```bash
git add tests/browser/test_integration.py
git commit -m "test(browser): add integration test for end-to-end exploration"
```

---

## Summary

| Chunk | Tasks | Files Created/Modified |
|-------|-------|------------------------|
| 1 | Config dataclasses | config.py, test_config.py |
| 2 | BrowserWrapper CLI wrapper | wrapper.py, test_wrapper.py |
| 3 | LLM client extension | client.py (modified) |
| 4 | MarketExplorer agent | explorer.py, test_explorer.py |
| 5 | Sanitize utilities | sanitize.py, test_sanitize.py |
| 6 | Integration test | test_integration.py |
