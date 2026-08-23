"""Typed model outputs used by the Browser Explorer agent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BrowserAction(BaseModel):
    """One validated action selected by the browser decision agent."""

    model_config = ConfigDict(extra="forbid")

    thought: str = Field(description="Brief reasoning for this action")
    action: Literal["search", "navigate", "click", "scroll", "stop"]
    query: str | None = None
    url: str | None = None
    selector: str | None = None

    @model_validator(mode="after")
    def validate_action_argument(self) -> BrowserAction:
        required = {
            "search": self.query,
            "navigate": self.url,
            "click": self.selector,
        }
        value = required.get(self.action)
        if self.action in required and not (value or "").strip():
            raise ValueError(f"{self.action} action requires its argument")
        return self


class PageSummary(BaseModel):
    """Concise financial summary of one browser page."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, description="A 2-3 sentence summary")


__all__ = ["BrowserAction", "PageSummary"]
