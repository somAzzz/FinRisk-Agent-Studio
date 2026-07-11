"""Auditable financial metric templates loaded from repository configuration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

PeriodType = Literal["flow", "instant"]
DEFAULT_CONFIG_DIR = Path(__file__).parents[2] / "config" / "financial_metrics"


@dataclass(frozen=True)
class MetricDefinition:
    concepts: tuple[str, ...]
    unit: str
    period_type: PeriodType
    ttm: bool


@dataclass(frozen=True)
class MetricTemplate:
    name: str
    metrics: dict[str, MetricDefinition]

    @property
    def instant_metrics(self) -> set[str]:
        return {
            name
            for name, definition in self.metrics.items()
            if definition.period_type == "instant"
        }

    @property
    def ttm_metrics(self) -> set[str]:
        return {
            name for name, definition in self.metrics.items() if definition.ttm
        }


def _read_template(name: str, config_dir: Path) -> MetricTemplate:
    if not name or not name.replace("_", "").isalnum():
        raise ValueError("metric template name contains unsupported characters")
    path = config_dir / f"{name}.json"
    if not path.is_file():
        raise ValueError(f"unknown financial metric template: {name}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("template") != name or not isinstance(payload.get("metrics"), dict):
        raise ValueError(f"invalid financial metric template: {name}")
    metrics: dict[str, MetricDefinition] = {}
    for metric, raw in payload["metrics"].items():
        concepts = raw.get("concepts") if isinstance(raw, dict) else None
        period_type = raw.get("period_type") if isinstance(raw, dict) else None
        if (
            not isinstance(metric, str)
            or not isinstance(concepts, list)
            or not concepts
            or not all(isinstance(item, str) and item for item in concepts)
            or period_type not in {"flow", "instant"}
            or not isinstance(raw.get("unit"), str)
            or not isinstance(raw.get("ttm"), bool)
        ):
            raise ValueError(f"invalid metric definition: {name}.{metric}")
        metrics[metric] = MetricDefinition(
            concepts=tuple(concepts),
            unit=raw["unit"],
            period_type=period_type,
            ttm=raw["ttm"],
        )
    return MetricTemplate(name=name, metrics=metrics)


def load_metric_template(
    name: str = "general",
    *,
    config_dir: Path = DEFAULT_CONFIG_DIR,
) -> MetricTemplate:
    """Load general metrics and overlay an optional industry template."""
    general = _read_template("general", config_dir)
    if name == "general":
        return general
    industry = _read_template(name, config_dir)
    return MetricTemplate(
        name=name,
        metrics={**general.metrics, **industry.metrics},
    )
