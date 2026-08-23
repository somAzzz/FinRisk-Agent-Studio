import asyncio
import hashlib
import random
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Protocol

import numpy as np

from src.browser.config import BrowserConfig, ExplorationConfig
from src.browser.factory import build_browser_wrapper
from src.browser.models import BrowserAction


class BrowserAgentClient(Protocol):
    """Async model boundary required by the browser state machine."""

    async def summarize(self, content: str) -> str: ...

    async def explore(
        self,
        *,
        goal: str,
        visited_urls: list[str],
        recent_findings: list[tuple[str, str]],
        session: Any,
        max_steps: int,
    ) -> Any: ...


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


# Consent-related patterns to detect and handle
CONSENT_PATTERNS = [
    r"cookie",
    r"consent",
    r"datenschutz",
    r"privacy",
    r"gdpr",
    r"accept",
    r"reject",
    r"agree",
]

# Verification/CAPTCHA page patterns - these should be skipped
VERIFICATION_PATTERNS = [
    r"datadome",
    r"recaptcha",
    r"hcaptcha",
    r"cloudflare",
    r"are you human",
    r"verify you",
    r"captcha",
    r"security check",
    r"access denied",
    r"blocked",
    r"403 forbidden",
    r"ray id",
    r"cloudflare security",
    r"DDOS-GUARD",
]

# URLs that commonly trigger verification
VERIFICATION_DOMAINS = [
    "consent.yahoo.com",
    "google.com/sorry",
    "investor.apple.com",
]


class PageType:
    """Classification of page types during exploration."""
    CONTENT = "content"
    CONSENT = "consent"
    VERIFICATION = "verification"
    ERROR = "error"


class MarketExplorer:
    # Default financial news sources
    DEFAULT_SOURCES: ClassVar[list[str]] = [
        "https://finance.yahoo.com",
        "https://www.reuters.com",
        "https://www.cnbc.com",
    ]

    def __init__(
        self,
        llm_client: BrowserAgentClient | None = None,
        wrapper: Any | None = None,
        browser_config: BrowserConfig | None = None,
        exploration_config: ExplorationConfig | None = None,
    ):
        if llm_client is None:
            from src.ai.browser_client import build_browser_client

            llm_client = build_browser_client()
        self.llm_client = llm_client
        self.browser_config = browser_config or BrowserConfig()
        self.wrapper = wrapper or build_browser_wrapper(browser_config=self.browser_config)
        self.exploration_config = exploration_config or ExplorationConfig()
        self._recent_embeddings: list[list[float]] = []

    def _compute_hash(self, text: str) -> str:
        """Compute SHA256 hash of text (first 10KB)."""
        return hashlib.sha256(text[:10240].encode()).hexdigest()

    def _compute_similarity(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        a_arr = np.array(a)
        b_arr = np.array(b)
        return np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr))

    def _classify_source(self, url: str) -> str:
        """Classify the source type based on URL."""
        url_lower = url.lower()
        if any(x in url_lower for x in ["news", "article", "blog"]):
            return "news"
        elif any(x in url_lower for x in ["finance", "stock", "market", "earnings"]):
            return "financial"
        elif any(x in url_lower for x in ["sec.gov", "regulatory", "government"]):
            return "regulatory"
        return "other"

    def _classify_page(self, url: str, content: str) -> PageType:
        """Classify what type of page this is."""
        url_lower = url.lower()
        content_lower = content.lower()

        # Check URL against known verification domains
        for domain in VERIFICATION_DOMAINS:
            if domain in url_lower:
                return PageType.VERIFICATION

        # Check content for verification patterns
        verification_count = sum(
            1 for p in VERIFICATION_PATTERNS if re.search(p, content_lower)
        )
        if verification_count >= 1:
            return PageType.VERIFICATION

        # Check for consent patterns
        consent_count = sum(
            1 for p in CONSENT_PATTERNS if re.search(p, content_lower)
        )
        if consent_count >= 2:
            return PageType.CONSENT

        return PageType.CONTENT

    def _is_consent_page(self, content: str) -> bool:
        """Check if page content is a consent/cookie dialog."""
        content_lower = content.lower()
        pattern_count = sum(1 for p in CONSENT_PATTERNS if re.search(p, content_lower))
        return pattern_count >= 2

    def _is_verification_page(self, url: str, content: str) -> bool:
        """Check if page is a verification/CAPTCHA page."""
        url_lower = url.lower()
        content_lower = content.lower()

        # Check URL domains
        for domain in VERIFICATION_DOMAINS:
            if domain in url_lower:
                return True

        # Check content patterns
        verification_count = sum(
            1 for p in VERIFICATION_PATTERNS if re.search(p, content_lower)
        )
        return verification_count >= 1

    async def _handle_consent_page(self) -> bool:
        """Attempt to handle consent/cookie dialogs. Returns True if handled."""
        snapshot = self.wrapper.get_snapshot()
        if not snapshot.get("success"):
            return False

        content = snapshot.get("content", "")
        if not self._is_consent_page(content):
            return False

        # Try to find and click "Accept All" or similar button
        lines = content.split("\n")
        for line in lines:
            line_lower = line.lower()
            if "button" in line_lower and (
                "accept" in line_lower or "agree" in line_lower or "alle" in line_lower or "akzeptieren" in line_lower
            ):
                ref_match = re.search(r"\[ref=([^\]]+)\]", line)
                if ref_match:
                    ref = ref_match.group(1)
                    result = self.wrapper.click(ref)
                    if result.get("success"):
                        await asyncio.sleep(1)
                        return True

        # Try clicking by text pattern
        accept_texts = ["accept all", "accept", "agree", "alle akzeptieren", "accept all cookies"]
        for text in accept_texts:
            result = self.wrapper.click(f"text:{text}")
            if result.get("success"):
                await asyncio.sleep(1)
                return True

        return False

    async def _process_page(self, state: ExplorationState) -> bool:  # noqa: PLR0911
        """Process current page and extract findings. Returns True if new finding."""
        snapshot_result = self.wrapper.get_snapshot()
        if not snapshot_result["success"]:
            return False

        content = snapshot_result.get("content", "")
        if not content:
            return False

        url = snapshot_result.get("url", "")
        if url and url not in state.visited_urls:
            state.visited_urls.add(url)

        # Classify the page
        page_type = self._classify_page(url, content)

        if page_type == PageType.VERIFICATION:
            # Skip verification pages
            return False

        if page_type == PageType.CONSENT:
            # Try to handle consent page
            consent_handled = await self._handle_consent_page()
            if consent_handled:
                await asyncio.sleep(1)
                # Try to get fresh content after dismissing consent
                fresh_snapshot = self.wrapper.get_snapshot()
                if fresh_snapshot.get("success"):
                    content = fresh_snapshot.get("content", "")
                    # Re-classify
                    if not self._is_consent_page(content):
                        page_type = PageType.CONTENT

        # Process content if we have meaningful content
        if len(content) < 100:
            return False

        content_hash = self._compute_hash(content)
        if content_hash in {f.content_hash for f in state.findings}:
            return False

        # Generate summary using structured output
        summary_text = await self.llm_client.summarize(content)

        # Check novelty via embedding (use sentence-transformers directly)
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer("all-MiniLM-L6-v2")
            embedding_vec = model.encode(summary_text).tolist()
        except Exception:
            embedding_vec = [0.0] * 384

        is_new = True
        for recent_emb in self._recent_embeddings[-3:]:
            if self._compute_similarity(embedding_vec, recent_emb) >= self.exploration_config.novelty_threshold:
                is_new = False
                break

        if is_new:
            finding = Finding(
                url=url,
                content_hash=content_hash,
                summary=summary_text,
                timestamp=datetime.now(),
                source_type=self._classify_source(url),
            )
            state.findings.append(finding)
            state.last_discovery = datetime.now()
            self._recent_embeddings.append(embedding_vec)
            return True

        return False

    def _is_blocked_url(self, url: str) -> bool:
        """Check if URL is in the blocked list."""
        url_lower = url.lower()
        blocked_domains = (
            "consent.yahoo.com",
            "google.com/sorry",
            "investor.apple.com",
        )
        return any(domain in url_lower for domain in blocked_domains)

    def _build_search_url(self, query: str) -> str:
        """Build a search URL from a query."""
        # Use CNBC search (Yahoo Finance redirects to consent.yahoo.com)
        encoded_query = query.replace(" ", "+")
        return f"https://www.cnbc.com/search/?query={encoded_query}"

    async def _execute_action(self, action: dict) -> bool:  # noqa: PLR0911
        """Execute an action. Returns True if successful."""
        action_type = action.get("action", "")

        if action_type == "search":
            query = action.get("query", "")
            if query:
                url = self._build_search_url(query)
                result = await self.wrapper.navigate(url)
                return result.get("success", False)
            return False

        if action_type == "navigate":
            url = action.get("url", "")
            if url:
                # Check if URL is blocked
                if self._is_blocked_url(url):
                    return False
                result = await self.wrapper.navigate(url)
                return result.get("success", False)

        elif action_type == "click":
            selector = action.get("selector", "")
            if selector:
                result = self.wrapper.click(selector)
                return result.get("success", False)

        elif action_type == "scroll":
            result = self.wrapper.scroll("down", 500)
            return result.get("success", False)

        elif action_type == "stop":
            return False

        return False

    async def explore(
        self,
        goal: str,
        checkpoint_callback: Callable[[ExplorationState], bool] | None = None,
        initial_urls: list[str] | None = None,
    ) -> ExplorationState:
        """Execute exploration goal."""
        state = ExplorationState(goal=goal)
        error_count = 0
        total_ops = 0

        # Initial navigation
        urls_to_visit = initial_urls or self.DEFAULT_SOURCES
        for url in urls_to_visit[:3]:
            if state.current_step >= self.browser_config.max_steps:
                break
            await self.wrapper.navigate(url)
            state.current_step += 1
            total_ops += 1
            await asyncio.sleep(random.uniform(1, 2))

            await self._handle_consent_page()
            await asyncio.sleep(0.5)

            if await self._process_page(state):
                state.last_discovery = datetime.now()

        # Pydantic AI owns the remaining decide -> tool -> observe loop. The
        # session keeps browser safety and project stop policies deterministic.
        remaining_steps = self.browser_config.max_steps - state.current_step
        if remaining_steps > 0:
            session = _ExplorerToolSession(
                explorer=self,
                state=state,
                checkpoint_callback=checkpoint_callback,
                total_ops=total_ops,
                error_count=error_count,
            )
            await self.llm_client.explore(
                goal=state.goal,
                visited_urls=list(state.visited_urls)[:5],
                recent_findings=[
                    (finding.summary, finding.url)
                    for finding in state.findings[-3:]
                ],
                session=session,
                max_steps=remaining_steps,
            )

        return state


@dataclass(slots=True)
class _ExplorerToolSession:
    """Apply Pydantic AI tool calls through existing browser guardrails."""

    explorer: MarketExplorer
    state: ExplorationState
    checkpoint_callback: Callable[[ExplorationState], bool] | None
    total_ops: int = 0
    error_count: int = 0
    stopped_reason: str | None = None

    async def execute(self, action: BrowserAction) -> dict[str, Any]:
        if self.stopped_reason is not None:
            return self._observation(success=False)
        if action.action == "stop":
            self.stopped_reason = "model_finished"
            return self._observation(success=True)
        if self.state.current_step >= self.explorer.browser_config.max_steps:
            self.stopped_reason = "step_limit"
            return self._observation(success=False)

        self.state.current_step += 1
        self.total_ops += 1
        success = await self.explorer._execute_action(
            action.model_dump(mode="python")
        )
        if not success:
            self.error_count += 1

        await asyncio.sleep(random.uniform(1, 3))
        await self.explorer._handle_consent_page()
        await asyncio.sleep(0.5)

        if action.action in {
            "navigate",
            "click",
            "scroll",
        } and await self.explorer._process_page(self.state):
            self.state.last_discovery = datetime.now()

        self._apply_stop_policies()
        return self._observation(success=success)

    def _apply_stop_policies(self) -> None:
        if self.state.current_step >= self.explorer.browser_config.max_steps:
            self.stopped_reason = "step_limit"
            return
        if (
            self.total_ops >= 5
            and self.error_count / self.total_ops
            > self.explorer.exploration_config.error_rate_threshold
        ):
            self.stopped_reason = "blocked"
            return
        steps_since_discovery = self.state.current_step - len(self.state.findings)
        if (
            steps_since_discovery
            >= self.explorer.exploration_config.no_new_findings_limit
        ):
            self.stopped_reason = "enough_evidence"
            return
        if (
            self.checkpoint_callback
            and self.state.current_step
            % self.explorer.browser_config.checkpoint_interval
            == 0
            and not self.checkpoint_callback(self.state)
        ):
            self.stopped_reason = "checkpoint"

    def _observation(self, *, success: bool) -> dict[str, Any]:
        return {
            "success": success,
            "current_step": self.state.current_step,
            "visited_urls": sorted(self.state.visited_urls)[-5:],
            "recent_findings": [
                {"url": finding.url, "summary": finding.summary}
                for finding in self.state.findings[-3:]
            ],
            "stop_recommended": self.stopped_reason is not None,
            "stop_reason": self.stopped_reason,
        }
