"""
SGLang Native Frontend Syntax Reference
=======================================

This file documents the SGLang native @sgl.function approach for future use.
Current sglang version (0.5.9) in Docker does NOT support response_format parameter.

UPGRADE PATH:
When sglang Docker image is upgraded to 0.6+, use this approach instead of OpenAI-compatible API.

Installation:
    pip install sglang

Reference: https://docs.sglang.ai/
"""

# ============================================================
# CURRENT IMPLEMENTATION (OpenAI-compatible API)
# ============================================================
# Located at: src/llm/sglang_client.py
# Uses: client.beta.chat.completions.parse() with Pydantic
# Works with: sglang 0.5.9+
# ============================================================

"""
from openai import OpenAI
from pydantic import BaseModel
from typing import Literal

class BrowserAction(BaseModel):
    thought: str
    action: Literal["navigate", "click", "scroll", "stop"]
    url: str | None = None
    selector: str | None = None

client = OpenAI(base_url="http://localhost:30000/v1", api_key="EMPTY")

completion = client.beta.chat.completions.parse(
    model="Qwen/Qwen3.5-35B-A3B",
    messages=[{"role": "user", "content": "Your prompt here"}],
    response_format=BrowserAction,
)
action = completion.choices[0].message.parsed
"""


# ============================================================
# FUTURE IMPLEMENTATION (SGLang Native - When sglang 0.6+)
# ============================================================
# Expected to have better performance due to FSM-based constrained decoding
# ============================================================

"""
import sglang as sgl
from pydantic import BaseModel
from typing import Literal

# 1. Define Pydantic models
class BrowserAction(BaseModel):
    thought: str
    action: Literal["navigate", "click", "scroll", "stop"]
    url: str | None = None
    selector: str | None = None

class PageSummary(BaseModel):
    summary: str

# 2. Connect to SGLang server
sgl.set_default_backend(sgl.RuntimeEndpoint("http://localhost:30000"))

# 3. Define SGLang functions with response_format
@sgl.function
def agent_decide_action(s, goal: str, visited_urls: str, recent_findings: str):
    s += sgl.system("You are a web browsing assistant.")
    s += sgl.user(
        f"Goal: {goal}\n\n"
        f"Visited URLs: {visited_urls}\n"
        f"Recent findings: {recent_findings}"
    )
    s += sgl.assistant(
        sgl.gen("action_json", response_format=BrowserAction)
    )

@sgl.function
def summarize_page(s, content: str):
    s += sgl.system("You are a financial analyst.")
    s += sgl.user(f"Summarize this page:\n{content[:5000]}")
    s += sgl.assistant(
        sgl.gen("summary_json", response_format=PageSummary)
    )

# 4. Run the functions
def run_agent():
    # Decide action
    state = agent_decide_action.run(
        goal="Explore Apple earnings",
        visited_urls="https://cnbc.com, https://reuters.com",
        recent_findings="CNBC: Apple stock up (https://cnbc.com/apple)"
    )
    action = state["action_json"]
    print(f"Thought: {action.thought}")
    print(f"Action: {action.action}")

    # Summarize page
    state = summarize_page.run(content="Apple reported Q4 earnings...")
    summary = state["summary_json"]
    print(f"Summary: {summary.summary}")
"""


# ============================================================
# UPGRADE CHECKLIST
# ============================================================
# 1. Update sglang Docker image to version 0.6+
# 2. pip install sglang>=0.6.0
# 3. Test response_format in gen() function
# 4. Compare performance with current OpenAI-compatible approach
# 5. Migrate src/llm/sglang_client.py to native syntax if beneficial
# ============================================================
