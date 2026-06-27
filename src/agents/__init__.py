"""Agent runtime for FinText-LLM.

This package provides a small, locally-controllable agent framework built on
top of the project schemas. It exposes:

- ``AgentState`` and ``ToolCall`` (state container for a single run)
- ``Agent`` / ``AsyncAgent`` protocols (the contract every agent must satisfy)
- ``PlannerAgent`` (rule-based planner producing an ``AgentPlan``)
- ``CriticAgent`` (rule-based reviewer for claims/evidence)
- ``Tool`` protocol and ``ToolRegistry`` (uniform tool dispatch with error
  capture)
- ``AgentRuntime`` (the orchestrator that runs plans end-to-end)
- ``LLMToolAgentRuntime`` (OpenAI-compatible LLM-selected tool loop)
"""

from src.agents.base import Agent, AsyncAgent
from src.agents.context import AgentContextBuilder
from src.agents.critic import CriticAgent
from src.agents.global_runtime import GlobalAgentRuntime
from src.agents.llm_runtime import LLMToolAgentRuntime, LLMToolRunResult
from src.agents.planner import (
    AgentPlan,
    AgentPlanner,
    PlannerAgent,
    PlanStep,
    PlanStepAction,
)
from src.agents.runtime import AgentRuntime
from src.agents.state import (
    AgentBudget,
    AgentDecision,
    AgentRunState,
    AgentRunTrace,
    AgentState,
    AgentSubgoal,
    HumanReviewItem,
    ToolCall,
)
from src.agents.tools import Tool, ToolRegistry, ToolResult

__all__ = [
    "Agent",
    "AgentBudget",
    "AgentContextBuilder",
    "AgentDecision",
    "AgentPlan",
    "AgentPlanner",
    "AgentRunState",
    "AgentRunTrace",
    "AgentRuntime",
    "AgentState",
    "AgentSubgoal",
    "AsyncAgent",
    "CriticAgent",
    "GlobalAgentRuntime",
    "HumanReviewItem",
    "LLMToolAgentRuntime",
    "LLMToolRunResult",
    "PlanStep",
    "PlanStepAction",
    "PlannerAgent",
    "Tool",
    "ToolCall",
    "ToolRegistry",
    "ToolResult",
]
