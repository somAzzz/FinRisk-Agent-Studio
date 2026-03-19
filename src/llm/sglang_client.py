"""SGLang client using OpenAI-compatible API with Pydantic structured output."""

from openai import OpenAI
from pydantic import BaseModel, Field
from typing import Literal


class BrowserAction(BaseModel):
    """Structured output for browser agent actions."""

    thought: str = Field(description="Brief reasoning for this action")
    action: Literal["navigate", "click", "scroll", "stop"] = Field(
        description="The action to perform"
    )
    url: str | None = Field(default=None, description="URL for navigate action")
    selector: str | None = Field(default=None, description="Selector for click action")


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

    def decide_action(
        self, goal: str, visited_urls: list[str], recent_findings: list[tuple[str, str]]
    ) *********REMOVED********* BrowserAction | None:
        """Decide next browser action."""
        visited_str = ", ".join(visited_urls[:5])
        findings_str = "; ".join([f"{s} ({u})" for s, u in recent_findings[-3:]])

        prompt = f"""Goal: {goal}

Visited URLs: {visited_str}
Recent findings: {findings_str}

You are a web browsing assistant. Focus on financial news and earnings."""

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
