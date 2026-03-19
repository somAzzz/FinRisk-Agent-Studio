import asyncio
import hashlib
import json
import random
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import numpy as np

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


class MarketExplorer:
    # Default financial news sources
    DEFAULT_SOURCES = [
        "https://finance.yahoo.com",
        "https://www.reuters.com",
        "https://www.cnbc.com",
    ]

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
        a_arr = np.array(a)
        b_arr = np.array(b)
        return np.dot(a_arr, b_arr) / (np.linalg.norm(a_arr) * np.linalg.norm(b_arr))

    def _classify_source(self, url: str) *********REMOVED********* str:
        """Classify the source type based on URL."""
        url_lower = url.lower()
        if any(x in url_lower for x in ["news", "article", "blog"]):
            return "news"
        elif any(x in url_lower for x in ["finance", "stock", "market", "earnings"]):
            return "financial"
        elif any(x in url_lower for x in ["sec.gov", "regulatory", "government"]):
            return "regulatory"
        return "other"

    def _is_consent_page(self, content: str) *********REMOVED********* bool:
        """Check if page content is a consent/cookie dialog."""
        content_lower = content.lower()
        pattern_count = sum(1 for p in CONSENT_PATTERNS if re.search(p, content_lower))
        return pattern_count >= 2

    async def _handle_consent_page(self) *********REMOVED********* bool:
        """Attempt to handle consent/cookie dialogs. Returns True if handled."""
        snapshot = self.wrapper.get_snapshot()
        if not snapshot.get("success"):
            return False

        content = snapshot.get("content", "")
        if not self._is_consent_page(content):
            return False

        # Try to find and click "Accept All" or similar button
        # Look for buttons with accept/reject patterns
        lines = content.split("\n")
        for line in lines:
            line_lower = line.lower()
            if "button" in line_lower and ("accept" in line_lower or "agree" in line_lower or "alle" in line_lower or "akzeptieren" in line_lower):
                # Extract ref from line like: - button "Accept All" [ref=e5]
                ref_match = re.search(r"\[ref=([^\]]+)\]", line)
                if ref_match:
                    ref = ref_match.group(1)
                    result = self.wrapper.click(ref)
                    if result.get("success"):
                        await asyncio.sleep(1)
                        return True

        # Try clicking by text pattern
        # Common accept button texts
        accept_texts = ["accept all", "accept", "agree", "alle akzeptieren", "accept all cookies"]
        for text in accept_texts:
            result = self.wrapper.click(f'text:{text}')
            if result.get("success"):
                await asyncio.sleep(1)
                return True

        return False

    def _strip_thinking(self, text: str) *********REMOVED********* str:
        """Remove thinking process blocks from text."""
        lines = text.split("\n")
        filtered_lines = []
        skip_block = False
        for line in lines:
            if "Thinking Process:" in line or "**Analyze" in line:
                skip_block = True
                continue
            if skip_block:
                # Look for lines that might be the actual response
                if line.strip().startswith('"summary"') or line.strip().startswith("}"):
                    skip_block = False
                elif line.strip().startswith("Apple") or line.strip().startswith("The"):
                    # This looks like actual content, not thinking
                    skip_block = False
                    filtered_lines.append(line)
                    continue
                continue
            filtered_lines.append(line)
        return "\n".join(filtered_lines)

    def _extract_summary_from_thinking(self, text: str) *********REMOVED********* str | None:
        """Try to extract summary from thinking block if JSON parsing fails."""
        # Look for patterns like: Draft: "Apple..." or Summary: "..."
        patterns = [
            r'Draft:\s*"([^"]+)"',
            r'Summary:\s*"([^"]+)"',
            r'summary["\s:]+([^,}]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()[:200]
        return None

    def _extract_json(self, text: str) *********REMOVED********* dict | None:
        """Extract JSON object from text, handling thinking blocks."""
        # First try direct JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON in the text
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                result = json.loads(json_match.group())
                if "summary" in result:
                    return result
            except json.JSONDecodeError:
                pass

        return None

    async def _process_page(self, state: ExplorationState) *********REMOVED********* bool:
        """Process current page and extract findings. Returns True if new finding."""
        # First check if this is a consent page and handle it
        consent_handled = await self._handle_consent_page()
        if consent_handled:
            await asyncio.sleep(0.5)

        snapshot_result = self.wrapper.get_snapshot()
        if not snapshot_result["success"]:
            return False

        content = snapshot_result.get("content", "")
        if not content:
            return False

        url = snapshot_result.get("url", "")
        if url and url not in state.visited_urls:
            state.visited_urls.add(url)

        # Skip consent/cookie pages after handling
        if self._is_consent_page(content) and consent_handled:
            return False

        content_hash = self._compute_hash(content)
        if content_hash in {f.content_hash for f in state.findings}:
            return False

        # Generate summary using LLM
        summary = self.llm_client.complete(
            prompt=f"""You are a financial analyst. Summarize this page in 2-3 sentences.

Page content:
{content[:5000]}

/no_think

Respond with ONLY a JSON object in this exact format, no other text:
{{"summary": "your 2-3 sentence summary here"}}""",
            system="You are a financial analyst. Respond with ONLY valid JSON.",
            max_tokens=256,
        )

        # Strip thinking process from response
        clean_summary = self._strip_thinking(summary)

        # Parse structured response
        summary_json = self._extract_json(clean_summary)
        if summary_json:
            summary_text = summary_json.get("summary", clean_summary[:200])
        else:
            # Try to extract from thinking block
            summary_text = self._extract_summary_from_thinking(summary) or clean_summary[:200]

        # Check novelty via embedding
        embedding = self.llm_client.compute_embedding(summary_text)
        is_new = True
        for recent_emb in self._recent_embeddings[-3:]:
            if self._compute_similarity(embedding, recent_emb) >= self.exploration_config.novelty_threshold:
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
            self._recent_embeddings.append(embedding)
            return True

        return False

    async def _llm_decide_action(self, state: ExplorationState) *********REMOVED********* dict | None:
        """Ask LLM what to do next. Returns action dict or None to stop."""
        visited_list = list(state.visited_urls)[:5]
        recent_findings = [(f.summary, f.url) for f in state.findings[-3:]]

        prompt = f"""Goal: {state.goal}

Visited URLs: {visited_list}
Recent findings: {recent_findings}

/no_think

You are a web browsing assistant. Decide your next action.

Respond with ONLY a JSON object in this exact format:
{{"thought": "brief reasoning (max 50 chars)", "action": "navigate|click|scroll|stop", "url": "...", "selector": "..."}}

Rules:
- "navigate": provide url (e.g., "https://finance.yahoo.com/news/apple")
- "click": provide selector (e.g., "text:Learn more" or "@e5")
- "scroll": no url/selector needed
- "stop": when you have gathered sufficient information
- Focus on financial news, earnings, market analysis
- Skip consent/cookie dialogs - they are handled automatically"""

        try:
            response = self.llm_client.complete(
                prompt=prompt,
                system="You are a web browsing assistant. Respond with ONLY valid JSON.",
                max_tokens=512,
                temperature=0.3,
            )
            # Parse JSON response
            json_match = re.search(r"\{[\s\S]*\}", response)
            if json_match:
                return json.loads(json_match.group())
        except Exception:
            pass
        return None

    async def _execute_action(self, action: dict) *********REMOVED********* bool:
        """Execute an action. Returns True if successful."""
        action_type = action.get("action", "")

        if action_type == "navigate":
            url = action.get("url", "")
            if url:
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
    ) *********REMOVED********* ExplorationState:
        """Execute exploration goal.

        Args:
            goal: Exploration objective
            checkpoint_callback: Returns True to continue, False to stop.
                Called every checkpoint_interval steps.
            initial_urls: Starting URLs to navigate to (default: DEFAULT_SOURCES)

        Returns:
            ExplorationState with findings and metadata
        """
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

            # Handle consent page if present
            await self._handle_consent_page()
            await asyncio.sleep(0.5)

            # Process each page
            if await self._process_page(state):
                state.last_discovery = datetime.now()

        # Main exploration loop
        while state.current_step < self.browser_config.max_steps:
            state.current_step += 1
            total_ops += 1

            # Ask LLM what to do
            action = await self._llm_decide_action(state)
            if not action:
                break

            if action.get("action") == "stop":
                break

            # Execute action
            success = await self._execute_action(action)
            if not success:
                error_count += 1

            await asyncio.sleep(random.uniform(1, 3))

            # Handle consent page if present
            await self._handle_consent_page()
            await asyncio.sleep(0.5)

            # Process current page
            if action.get("action") in ["navigate", "click", "scroll"]:
                if await self._process_page(state):
                    state.last_discovery = datetime.now()

            # Check error rate
            if total_ops >= 5 and error_count / total_ops > self.exploration_config.error_rate_threshold:
                break

            # Check stopping conditions
            steps_since_discovery = state.current_step - len(state.findings)
            if steps_since_discovery >= self.exploration_config.no_new_findings_limit:
                break

            # Checkpoint
            if checkpoint_callback and state.current_step % self.browser_config.checkpoint_interval == 0:
                if not checkpoint_callback(state):
                    break

        return state
