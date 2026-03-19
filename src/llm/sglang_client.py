"""SGLang client using OpenAI-compatible API with Pydantic structured output."""

from openai import OpenAI
from pydantic import BaseModel, Field
from typing import Literal


class BrowserAction(BaseModel):
    """Structured output for browser agent actions."""

    thought: str = Field(description="Brief reasoning for this action")
    action: Literal["search", "navigate", "click", "scroll", "stop"] = Field(
        description="The action to perform: search for a topic, navigate to URL, click element, scroll, or stop"
    )
    query: str | None = Field(
        default=None,
        description="Search query for 'search' action (e.g., 'Intel stock Middle East war impact')"
    )
    url: str | None = Field(
        default=None,
        description="URL for navigate action (e.g., 'https://finance.yahoo.com/q?s=INTC')"
    )
    selector: str | None = Field(
        default=None,
        description="Selector for click action (e.g., 'text:Learn more' or '@e5')"
    )


class PageSummary(BaseModel):
    """Structured output for page summaries."""

    summary: str = Field(description="2-3 sentence summary of the page content")


class SGLangClient:
    """LLM client using OpenAI-compatible API with structured output."""

    def __init__(self, base_url: str = "http://localhost:30000/v1"):
        self.client = OpenAI(
            base_url=base_url,
            api_key="EMPTY",
        )

    # URLs that commonly trigger verification - LLM should avoid these
    BLOCKED_URLS = [
        "consent.yahoo.com",
        "google.com/sorry",
        "investor.apple.com",
    ]

    def decide_action(
        self, goal: str, visited_urls: list[str], recent_findings: list[tuple[str, str]]
    ) *********REMOVED********* BrowserAction | None:
        """Decide next browser action."""
        visited_str = ", ".join(visited_urls[:5])
        findings_str = "; ".join([f"{s} ({u})" for s, u in recent_findings[-3:]])
        blocked_str = ", ".join(self.BLOCKED_URLS)

        prompt = f"""Goal: {goal}

Visited URLs: {visited_str}
Recent findings: {findings_str}
AVOID these URLs (they trigger verification): {blocked_str}

You are a web browsing assistant exploring financial news.

Suggested search URLs:
- https://finance.yahoo.com/news/?p=YOUR_SEARCH_QUERY
- https://www.cnbc.com/search/?query=YOUR_SEARCH_QUERY
- https://www.reuters.com/search/news/?blob=YOUR_SEARCH_QUERY

Rules:
- Start by SEARCHING for your topic
- Then NAVIGATE to interesting URLs from search results
- CLICK on relevant article links
- SCROLL to see more content
- STOP when you have gathered enough information

Skip verification/CAPTCHA pages - they are blocked automatically."""

        try:
            completion = self.client.beta.chat.completions.parse(
                model="Qwen/Qwen3.5-35B-A3B",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a web browsing assistant. Respond with ONLY valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format=BrowserAction,
            )
            return completion.choices[0].message.parsed
        except Exception as e:
            print(f"Error in decide_action: {e}")
            return None

    def summarize(self, content: str) *********REMOVED********* str:
        """Summarize page content."""
        prompt = f"Summarize this page in 2-3 sentences:\n\n{content[:5000]}"

        try:
            completion = self.client.beta.chat.completions.parse(
                model="Qwen/Qwen3.5-35B-A3B",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a financial analyst. Respond with ONLY valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format=PageSummary,
            )
            return completion.choices[0].message.parsed.summary
        except Exception as e:
            print(f"Error in summarize: {e}")
            return content[:200]
