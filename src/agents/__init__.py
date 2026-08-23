"""Agent runtime for FinRisk-Agent-Studio.

This package provides a small, locally-controllable agent framework built on
top of the project schemas. It exposes:

- ``AgentState`` and ``ToolCall`` (state container for a single run)
- ``Agent`` / ``AsyncAgent`` protocols (the contract every agent must satisfy)
- ``PlannerAgent`` (rule-based planner producing an ``AgentPlan``)
- ``CriticAgent`` (rule-based reviewer for claims/evidence)
- ``Tool`` protocol and ``ToolRegistry`` (uniform tool dispatch with error
  capture)
- ``GlobalAgentRuntime`` (the orchestrator that runs plans end-to-end)
"""

from src.agents.base import Agent, AsyncAgent
from src.agents.context import AgentContextBuilder
from src.agents.critic import CriticAgent
from src.agents.global_runtime import GlobalAgentRuntime
from src.agents.planner import (
    AgentPlan,
    AgentPlanner,
    PlannerAgent,
    PlanStep,
    PlanStepAction,
)
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
from src.ai.runtime_types import LLMToolRunResult

__all__ = [
    "Agent",
    "AgentBudget",
    "AgentContextBuilder",
    "AgentDecision",
    "AgentPlan",
    "AgentPlanner",
    "AgentRunState",
    "AgentRunTrace",
    "AgentState",
    "AgentSubgoal",
    "AsyncAgent",
    "CriticAgent",
    "GlobalAgentRuntime",
    "HumanReviewItem",
    "LLMToolRunResult",
    "PlanStep",
    "PlanStepAction",
    "PlannerAgent",
    "Tool",
    "ToolCall",
    "ToolRegistry",
    "ToolResult",
]
