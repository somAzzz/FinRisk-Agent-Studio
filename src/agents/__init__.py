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
"""

from src.agents.base import Agent, AsyncAgent
from src.agents.critic import CriticAgent
from src.agents.planner import AgentPlan, PlanStep, PlanStepAction, PlannerAgent
from src.agents.runtime import AgentRuntime
from src.agents.state import AgentState, ToolCall
from src.agents.tools import Tool, ToolRegistry, ToolResult

__all__ = [
    "Agent",
    "AgentPlan",
    "AgentRuntime",
    "AgentState",
    "AsyncAgent",
    "CriticAgent",
    "PlanStep",
    "PlanStepAction",
    "PlannerAgent",
    "Tool",
    "ToolCall",
    "ToolRegistry",
    "ToolResult",
]
