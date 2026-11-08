"""Compare mutually exclusive plant decisions using explicit incremental cash flows."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlantOption(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    action: Literal["continue", "convert", "exit"]
    initial_outflow: Decimal = Field(ge=0)
    annual_net_cashflows: list[Decimal] = Field(min_length=1, max_length=40)
    terminal_proceeds: Decimal = Decimal(0)


class PlantDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    site: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    discount_rate: Decimal = Field(gt=-1, le=1)
    assumptions_source: str = Field(min_length=1)
    alternatives: list[PlantOption] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def comparable(self):
        if (
            len({v.action for v in self.alternatives}) != 3
            or len({len(v.annual_net_cashflows) for v in self.alternatives}) != 1
        ):
            raise ValueError("Supply continue, convert and exit cash flows on the same time horizon")
        return self

    def compare(self) -> dict:
        values = {}
        for option in self.alternatives:
            flows = option.annual_net_cashflows
            present = sum(flow / (1 + self.discount_rate) ** t for t, flow in enumerate(flows, 1))
            values[option.action] = round(
                present - option.initial_outflow + option.terminal_proceeds / (1 + self.discount_rate) ** len(flows), 2
            )
        return {"inputs": self.model_dump(), "npv": values, "status": "conditional_on_analyst_assumptions"}
