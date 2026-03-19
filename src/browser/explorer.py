import asyncio
import hashlib
import random
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
        error_count = 0
        total_ops = 0

        while state.current_step < self.browser_config.max_steps:
            state.current_step += 1
            total_ops += 1

            # Get current page content
            snapshot_result = self.wrapper.get_snapshot()
            if not snapshot_result["success"]:
                error_count += 1
                continue

            content = snapshot_result.get("content", "")
            if not content:
                continue

            # Record visited URL
            url = snapshot_result.get("url", "")
            if url and url not in state.visited_urls:
                state.visited_urls.add(url)

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
                    url=url,
                    content_hash=content_hash,
                    summary=summary,
                    timestamp=datetime.now(),
                )
                state.findings.append(finding)
                state.last_discovery = datetime.now()
                self._recent_embeddings.append(embedding)

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

            # Random delay to respect rate limits
            await asyncio.sleep(random.uniform(1, 3))

        return state
