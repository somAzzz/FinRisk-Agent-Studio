"""Tool router for multi-tool LLM agent.

Supports:
- web_search: Fast DuckDuckGo API search for quick RAG-style queries
- browser: Full browser automation for complex web interactions
"""

import asyncio
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field

from src.llm.sglang_client import SGLangClient
from src.tools.web_search import web_search, WEB_SEARCH_TOOL, SearchResult


class ToolChoice(BaseModel):
    """LLM response for tool selection."""
    thought: str = Field(description="Reasoning about what to do")
    tool: Literal["web_search", "browser", "finish"] = Field(
        description="Choose: 'web_search' for quick info, 'browser' for complex web interaction, 'finish' if done"
    )
    query: str | None = Field(default=None, description="Search query if using web_search")
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

    def _build_router_prompt(self, goal: str, history: list[dict]) *********REMOVED********* str:
        """Build prompt for tool selection."""
        history_str = ""
        if history:
            history_str = "\n\nPrevious tool uses:\n"
            for h in history[-3:]:
                history_str += f"- {h['tool']}: {h.get('query', h.get('action', ''))[:100]}\n"
                history_str += f"  Result: {h.get('result', '')[:200]}\n"

        return f"""Goal: {goal}
{history_str}

You are a tool-selecting assistant. Choose the best tool for the job:

1. web_search - Use for:
   - Quick factual queries
   - Current events and news
   - Stock prices, market data
   - General web information
   - When you need fast, clean text answers

2. browser - Use for:
   - Complex web interactions (login, forms, clicks)
   - Extracting data from specific websites that require interaction
   - Accessing paywalled or dynamic content
   - When you need to navigate to specific pages

3. finish - Use when:
   - You have enough information to answer the goal
   - The user question is answered
   - You want to stop exploration

Current date: 2026-03-19 (use this to evaluate result freshness)

Respond with ONLY valid JSON:
{{"thought": "why you chose this tool", "tool": "web_search|browser|finish", "query": "search term if web_search", "reason": "why this tool"}}"""

    def select_tool(self, goal: str) *********REMOVED********* ToolChoice | None:
        """Ask LLM to select appropriate tool."""
        try:
            completion = self.llm_client.client.chat.completions.parse(
                model="Qwen/Qwen3.5-35B-A3B",
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

    def execute_web_search(self, query: str) *********REMOVED********* str:
        """Execute web search and record result."""
        print(f"[Web Search] Query: {query}")
        result = web_search(query)
        self.search_history.append({
            "tool": "web_search",
            "query": query,
            "result": result[:500],
        })
        return result

    async def execute_browser(self, goal: str) *********REMOVED********* str:
        """Execute browser exploration."""
        from src.browser import BrowserWrapper, MarketExplorer

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
            "result": browser_result[:500],
        })
        return browser_result

    def build_synthesis_prompt(self, tool_result: str, original_goal: str) *********REMOVED********* str:
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

    def synthesize(self, tool_result: str, original_goal: str) *********REMOVED********* str | None:
        """Ask LLM to synthesize final answer from tool results."""
        try:
            completion = self.llm_client.client.chat.completions.parse(
                model="Qwen/Qwen3.5-35B-A3B",
                messages=[
                    {"role": "system", "content": "You are a financial analysis assistant. Provide clear answers with citations."},
                    {"role": "user", "content": self.build_synthesis_prompt(tool_result, original_goal)},
                ],
                response_format=ToolChoice,
            )
            return completion.choices[0].message.parsed
        except Exception as e:
            print(f"Error in synthesis: {e}")
            return None

    async def run(self, goal: str, max_iterations: int = 5) *********REMOVED********* str:
        """Run tool selection loop until completion."""
        print(f"\n=== Tool Router: {goal} ===\n")

        for i in range(max_iterations):
            print(f"[Step {i+1}] Selecting tool...")

            choice = self.select_tool(goal)
            if not choice:
                print("Tool selection failed, stopping.")
                break

            print(f"[Step {i+1}] Selected: {choice.tool} - {choice.thought}")

            if choice.tool == "web_search" and choice.query:
                result = self.execute_web_search(choice.query)
                print(f"[Step {i+1}] Search returned {len(result)} chars")

                # Ask LLM to decide if more search needed or finish
                synthesis = self.synthesize(result, goal)
                if synthesis and synthesis.tool == "finish" and synthesis.answer:
                    print(f"\n=== Final Answer ===\n{synthesis.answer}")
                    return synthesis.answer

            elif choice.tool == "browser":
                result = await self.execute_browser(goal)
                print(f"[Step {i+1}] Browser returned {len(result)} chars")

                synthesis = self.synthesize(result, goal)
                if synthesis and synthesis.tool == "finish" and synthesis.answer:
                    print(f"\n=== Final Answer ===\n{synthesis.answer}")
                    return synthesis.answer

            elif choice.tool == "finish":
                if choice.answer:
                    print(f"\n=== Final Answer ===\n{choice.answer}")
                return choice.answer or "No answer provided."

        return "Max iterations reached without final answer."
