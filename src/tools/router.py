"""Tool router for multi-tool LLM agent.

Supports:
- web_search: Fast DuckDuckGo API search for quick RAG-style queries
- browser: Full browser automation for complex web interactions

.. deprecated::
    The :class:`ToolRouter` remains the high-level LLM-driven router used by
    the agent loop, but it is being progressively refactored to delegate to
    the new :class:`src.tools.search_router.SearchRouter` for unified search
    orchestration (multi-provider fallback, cache, fetch). New code should
    prefer ``SearchRouter`` directly; this module is kept for backwards
    compatibility until the integration is complete.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from src.llm.sglang_client import SGLangClient
from src.tools.web_fetch import serialize_result, web_fetch
from src.tools.web_search import web_search
from src.tools.tier_detection import detect_search_tier, is_direct_url
from src.tools.tavily import tavily_search
from src.tools.searxng import searxng_search
from src.browser import BrowserWrapper, MarketExplorer

_VALID_TIME_RANGES: set[Literal["d", "w", "m", "y", None]] = {"d", "w", "m", "y", None}

# Magic numbers extracted as constants
_TRUNCATION_LENGTH = 500
_HISTORY_SLICE_SIZE = 3
_DDGS_MAX_RESULTS = 5

# Hardcoded model name
_DEFAULT_MODEL = "Qwen/Qwen3.5-35B-A3B"


class SynthesisResult(BaseModel):
    """Structured output for synthesis responses."""
    answer: str = Field(description="Final answer to the user's question")
    needs_more_info: bool = Field(
        default=False,
        description="True if more information is needed to fully answer"
    )
    suggested_tool: (
        Literal["web_search", "web_fetch", "browser", "finish"] | None
    ) = Field(default=None, description="Next tool if needs_more_info is True")
    suggested_query: str | None = Field(default=None, description="Query for suggested tool")
    suggested_url: str | None = Field(default=None, description="URL for suggested tool")


class ToolChoice(BaseModel):
    """LLM response for tool selection."""
    thought: str = Field(description="Reasoning about what to do")
    tool: Literal["ddgs", "tavily", "web_fetch", "browser", "finish"] = Field(
        description="Choose: 'ddgs' for simple queries, 'tavily' for deep search, 'web_fetch' for URL content, 'browser' for complex interaction, 'finish' if done"
    )
    query: str | None = Field(default=None, description="Search query if using ddgs or tavily")
    url: str | None = Field(default=None, description="URL to fetch if using web_fetch")
    time_range: Literal["d", "w", "m", "y", None] = Field(
        default=None,
        description="Time filter for search. 'd'=day, 'w'=week, 'm'=month, 'y'=year. Only set if query implies recency. MUST be null (not empty string) when no time filter is needed."
    )
    reason: str | None = Field(default=None, description="Why you chose this tool")
    answer: str | None = Field(default=None, description="Final answer if using finish")


@dataclass
class ToolResult:
    """Result from a tool execution."""
    success: bool
    content: str
    tool_used: str


class ToolRouter:
    """Routes LLM requests to appropriate tools."""

    def __init__(self, llm_client: SGLangClient | None = None):
        self.llm_client = llm_client or SGLangClient()
        self.search_history: list[dict] = []

    def _build_router_prompt(self, goal: str, history: list[dict]) -> str:
        """Build prompt for tool selection."""
        history_str = ""
        if history:
            history_str = "\n\nPrevious tool uses:\n"
            for h in history[-_HISTORY_SLICE_SIZE:]:
                history_str += f"- {h['tool']}: {h.get('query', h.get('action', ''))[:100]}\n"
                history_str += f"  Result: {h.get('result', '')[:200]}\n"

        return f"""Goal: {goal}
{history_str}

You are a tool-selecting assistant. Choose the best tool for the job:

1. ddgs - Use for:
   - Quick factual queries
   - Stock tickers, current prices
   - Simple definitions and facts
   - When you need fast, clean text answers
   time_range: Time filter for search. Set this when:
   - User says "recent", "latest", "last [period]"
   - User mentions a specific period like "last week", "this month"
   - The topic requires current information (news, markets, events)
   - User does NOT specify a time, set to null (NOT empty string "")

   Options: 'd'=past 24 hours, 'w'=past week, 'm'=past month, 'y'=past year

2. tavily - Use for:
   - Deep analysis and comprehensive reports
   - Multi-source news and trend research
   - Earnings analysis and financial research
   - When you need longer summaries (500 chars) optimized for RAG
   - Reduces need for additional web_fetch calls

3. web_fetch - Use for:
   - When you have a specific URL to fetch
   - Getting detailed article content for RAG
   - Extracting metadata (title, description) with content
   - Best for static pages (news, blogs, wikis)

4. browser - Use for:
   - Complex web interactions (login, forms, clicks)
   - Extracting data from specific websites that require interaction
   - Accessing paywalled or dynamic/SPA content
   - When web_fetch fails on a URL

5. finish - Use when:
   - You have enough information to answer the goal
   - The user question is answered
   - You want to stop exploration

Current date: 2026-03-19 (use this to evaluate result freshness)

⚠️ Time Anchor Requirement: The LLM must receive current time as an absolute reference to correctly interpret relative time expressions like "last week". The System Prompt (agent role) MUST include "Current system time is: 2026-03-22T14:30:00Z (UTC)".

Respond with ONLY valid JSON:
{{"thought": "why you chose this tool", "tool": "ddgs|tavily|web_fetch|browser|finish", "query": "search term if ddgs or tavily", "url": "url to fetch if web_fetch", "reason": "why this tool"}}"""

    def select_tool(self, goal: str) -> ToolChoice | None:
        """Select appropriate tool using tier detection or LLM."""
        # 1. URL detection
        if is_direct_url(goal):
            return ToolChoice(
                thought="Direct URL detected → web_fetch",
                tool="web_fetch",
                url=goal,
                reason="Direct URL input",
            )

        # 2. Rule-based tier detection
        tier = detect_search_tier(goal)

        if tier == "ddgs":
            return ToolChoice(
                thought="Rule-based: simple query detected → ddgs",
                tool="ddgs",
                query=goal,
                reason="Simple query pattern matched",
            )

        if tier == "tavily":
            return ToolChoice(
                thought="Rule-based: deep search detected → tavily",
                tool="tavily",
                query=goal,
                reason="Deep search keyword detected",
            )

        # 3. Ambiguous → LLM router
        try:
            completion = self.llm_client.client.chat.completions.parse(
                model=_DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": "You are a tool selection assistant. Respond with ONLY valid JSON."},
                    {"role": "user", "content": self._build_router_prompt(goal, self.search_history)},
                ],
                response_format=ToolChoice,
            )
            return completion.choices[0].message.parsed
        except Exception as e:
            print(f"Error in tool selection: {e}")
            return None

    async def execute_web_fetch(self, url: str) -> str:
        """Execute web fetch and record result."""
        print(f"[Web Fetch] URL: {url}")
        result = await web_fetch(url)
        serialized = serialize_result(result)
        self.search_history.append({
            "tool": "web_fetch",
            "query": url,
            "result": serialized[:_TRUNCATION_LENGTH],
        })
        return serialized

    def execute_web_search(self, query: str, time_range: Literal["d", "w", "m", "y", None] = None) -> str:
        """Execute web search and record result."""
        # Sanitize: only pass valid time_range values to DDGS
        sanitized_time_range = time_range if time_range in _VALID_TIME_RANGES else None
        print(f"[Web Search] Query: {query}, time_range: {sanitized_time_range}")
        result = web_search(query, time_range=sanitized_time_range)
        self.search_history.append({
            "tool": "web_search",
            "query": query,
            "result": result[:_TRUNCATION_LENGTH],
        })
        return result

    def execute_ddgs(self, query: str, time_range: Literal["d", "w", "m", "y", None] = None) -> str:
        """Execute ddgs search with transparent SearXNG fallback."""
        # Sanitize: only pass valid time_range values
        sanitized_time_range = time_range if time_range in _VALID_TIME_RANGES else None
        print(f"[Search] Using ddgs for: {query}")
        try:
            result = web_search(query, max_results=_DDGS_MAX_RESULTS, time_range=sanitized_time_range)
        except Exception as e:
            print(f"[Search] ddgs failed ({e}), trying SearXNG...")
            result = searxng_search(query, time_range=sanitized_time_range)

        self.search_history.append({
            "tool": "ddgs",
            "query": query,
            "result": result[:_TRUNCATION_LENGTH],
        })
        return result

    def execute_tavily(self, query: str, time_range: Literal["d", "w", "m", "y", None] = None) -> str:
        """Execute tavily deep search."""
        # Sanitize: only pass valid time_range values
        sanitized_time_range = time_range if time_range in _VALID_TIME_RANGES else None
        print(f"[Search] Using tavily for: {query}")
        result = tavily_search(query, time_range=sanitized_time_range)

        self.search_history.append({
            "tool": "tavily",
            "query": query,
            "result": result[:_TRUNCATION_LENGTH],
        })
        return result

    async def execute_browser(self, goal: str) -> str:
        """Execute browser exploration."""
        wrapper = BrowserWrapper()
        explorer = MarketExplorer(llm_client=self.llm_client, wrapper=wrapper)

        result = await explorer.explore(goal)
        wrapper.close()

        findings_str = "\n".join([
            f"- [{f.source_type}] {f.summary}" for f in result.findings
        ])

        browser_result = f"Browser exploration complete:\n- Steps: {result.current_step}\n- Findings: {len(result.findings)}\n\n{findings_str}"

        self.search_history.append({
            "tool": "browser",
            "query": goal,
            "result": browser_result[:_TRUNCATION_LENGTH],
        })
        return browser_result

    def build_synthesis_prompt(self, tool_result: str, original_goal: str) -> str:
        """Build prompt for LLM to synthesize final answer."""
        return f"""Based on the tool execution result, please provide a comprehensive answer.

Original Goal: {original_goal}

Tool Result:
{tool_result}

Instructions:
1. If the result answers the goal, provide a clear, concise answer with citations
2. If information is insufficient, explain what's missing
3. Always cite sources using [1], [2], etc. format
4. Current date is 2026-03-19 - use this to evaluate freshness

Respond with your final answer:"""

    def synthesize(self, tool_result: str, original_goal: str) -> SynthesisResult | None:
        """Ask LLM to synthesize final answer from tool results."""
        try:
            completion = self.llm_client.client.chat.completions.parse(
                model=_DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": "You are a financial analysis assistant."},
                    {"role": "user", "content": self.build_synthesis_prompt(tool_result, original_goal)},
                ],
                response_format=SynthesisResult,
            )
            return completion.choices[0].message.parsed
        except Exception as e:
            print(f"Error in synthesis: {e}")
            return None

    async def run(self, goal: str, max_iterations: int = 5) -> str:
        """Run tool selection loop until completion."""
        print(f"\n=== Tool Router: {goal} ===\n")

        for i in range(max_iterations):
            print(f"[Step {i+1}] Selecting tool...")

            choice = self.select_tool(goal)
            if not choice:
                print("Tool selection failed, stopping.")
                break

            print(f"[Step {i+1}] Selected: {choice.tool} - {choice.thought}")

            # Execute the chosen tool
            if choice.tool == "ddgs" and choice.query:
                result = self.execute_ddgs(choice.query, choice.time_range)
                print(f"[Step {i+1}] Search returned {len(result)} chars")
            elif choice.tool == "tavily" and choice.query:
                result = self.execute_tavily(choice.query, choice.time_range)
                print(f"[Step {i+1}] Tavily returned {len(result)} chars")
            elif choice.tool == "browser":
                result = await self.execute_browser(goal)
                print(f"[Step {i+1}] Browser returned {len(result)} chars")
            elif choice.tool == "web_fetch" and choice.url:
                result = await self.execute_web_fetch(choice.url)
                print(f"[Step {i+1}] Fetch returned {len(result)} chars")
            elif choice.tool == "finish":
                if choice.answer:
                    print(f"\n=== Final Answer ===\n{choice.answer}")
                return choice.answer or "No answer provided."
            else:
                break

            # Synthesize result
            synthesis = self.synthesize(result, goal)
            if synthesis:
                if not synthesis.needs_more_info and synthesis.answer:
                    print(f"\n=== Final Answer ===\n{synthesis.answer}")
                    return synthesis.answer

                # If needs more info, continue with suggested tool
                if synthesis.needs_more_info and synthesis.suggested_tool:
                    print(f"[Step {i+1}] Needs more info, suggesting: {synthesis.suggested_tool}")
                    if synthesis.suggested_tool == "web_search" and synthesis.suggested_query:
                        result = self.execute_web_search(synthesis.suggested_query)
                        synthesis = self.synthesize(result, goal)
                        if synthesis and synthesis.answer:
                            print(f"\n=== Final Answer ===\n{synthesis.answer}")
                            return synthesis.answer
                    elif synthesis.suggested_tool == "web_fetch" and synthesis.suggested_url:
                        result = await self.execute_web_fetch(synthesis.suggested_url)
                        synthesis = self.synthesize(result, goal)
                        if synthesis and synthesis.answer:
                            print(f"\n=== Final Answer ===\n{synthesis.answer}")
                            return synthesis.answer

        return "Max iterations reached without final answer."
