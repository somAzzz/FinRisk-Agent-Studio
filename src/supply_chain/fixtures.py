"""v18 demo fixture loader for the OpenAI / ChatGPT supply chain.

The fixture mirrors the structure documented in
``docs/specs/v18-product-supply-chain-sankey/01-models-and-fixtures.md``:

- 18 nodes covering companies, products, services, components,
  and energy sources.
- 17 edges (confirmed via SEC filings, company press releases,
  or industry research).
- 12 evidence rows with stable ``sc:*`` ids.
- a CPU expansion subgraph that the recursive-expansion step
  consumes.

The fixture is bundled with the package so the v18 demo runs
without any external service.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "supply_chain" / "fixtures"
DEFAULT_FIXTURE_PATH = FIXTURE_DIR / "openai_chatgpt_supply_chain.json"


def _now() -> datetime:
    return datetime(2026, 6, 25, tzinfo=UTC)


def _evidence(
    evidence_id: str,
    source_type: str,
    source_name: str,
    quote: str,
    summary: str,
    *,
    url: str | None = None,
    title: str | None = None,
    confidence: float = 0.9,
    published_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "evidence_id": evidence_id,
        "source_type": source_type,
        "source_name": source_name,
        "url": url,
        "title": title,
        "quote": quote,
        "summary": summary,
        "retrieved_at": _now(),
        "published_at": published_at,
        "confidence": confidence,
        "metadata": {},
    }


def _node(
    node_id: str,
    node_type: str,
    label: str,
    *,
    ticker: str | None = None,
    depth: int = 1,
    parent_node_id: str | None = None,
    confidence: float = 0.9,
    evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "node_id": node_id,
        "node_type": node_type,
        "label": label,
        "normalized_name": label.lower(),
        "ticker": ticker,
        "depth": depth,
        "parent_node_id": parent_node_id,
        "confidence": confidence,
        "evidence_ids": evidence_ids or [],
        "metadata": {},
    }


def _edge(
    edge_id: str,
    source: str,
    target: str,
    relation_type: str,
    value: float,
    *,
    value_meaning: str = "importance",
    confidence: float = 0.9,
    evidence_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "edge_id": edge_id,
        "source_node_id": source,
        "target_node_id": target,
        "relation_type": relation_type,
        "value": value,
        "value_meaning": value_meaning,
        "confidence": confidence,
        "evidence_ids": evidence_ids or [],
        "metadata": {},
    }


def build_default_fixture() -> dict[str, Any]:
    """Return the v18 demo fixture as a plain ``dict``.

    The function is deterministic and side-effect-free so unit
    tests can call it directly without hitting the filesystem.
    """
    now = _now()
    request = {
        "company_name": "OpenAI",
        "ticker": None,
        "product_name": "ChatGPT",
        "max_depth": 3,
        "max_suppliers_per_node": 5,
        "focus_regions": [],
        "include_private_companies": True,
        "demo_mode": True,
        "cached_mode": True,
    }
    evidence = [
        _evidence(
            "sc:fixture:chatgpt-product",
            "fixture",
            "OpenAI product page",
            "ChatGPT is OpenAI's flagship conversational product.",
            "Anchors the product node.",
            confidence=0.95,
            published_at=now,
        ),
        _evidence(
            "sc:fixture:cloud-azure",
            "company",
            "Microsoft press release",
            "Microsoft Azure is the primary cloud partner for OpenAI.",
            "Anchors company:microsoft.",
            confidence=0.9,
            published_at=now,
        ),
        _evidence(
            "sc:fixture:cloud-oracle",
            "company",
            "Oracle press release",
            "Oracle Cloud Infrastructure hosts OpenAI workloads.",
            "Anchors company:oracle.",
            confidence=0.8,
            published_at=now,
        ),
        _evidence(
            "sc:fixture:cloud-coreweave",
            "company",
            "CoreWeave announcement",
            "CoreWeave provides GPU cloud capacity for OpenAI.",
            "Anchors company:coreweave.",
            confidence=0.85,
            published_at=now,
        ),
        _evidence(
            "sc:fixture:gpu-nvidia",
            "company",
            "NVIDIA 10-K",
            "NVIDIA H100 GPUs are widely deployed in AI training fleets.",
            "Anchors company:nvidia.",
            confidence=0.95,
            published_at=now,
        ),
        _evidence(
            "sc:fixture:cpu-amd",
            "company",
            "AMD product page",
            "AMD EPYC CPUs are common in cloud server platforms.",
            "Anchors company:amd.",
            confidence=0.85,
            published_at=now,
        ),
        _evidence(
            "sc:fixture:cpu-intel",
            "company",
            "Intel product page",
            "Intel Xeon CPUs underpin most hyperscaler cloud platforms.",
            "Anchors company:intel.",
            confidence=0.9,
            published_at=now,
        ),
        _evidence(
            "sc:fixture:hbm-hynix",
            "company",
            "SK Hynix product page",
            "SK Hynix HBM3 memory is paired with NVIDIA H100 GPUs.",
            "Anchors company:sk-hynix.",
            confidence=0.9,
            published_at=now,
        ),
        _evidence(
            "sc:fixture:hbm-samsung",
            "company",
            "Samsung product page",
            "Samsung HBM memory is a second source for AI accelerators.",
            "Anchors company:samsung.",
            confidence=0.8,
            published_at=now,
        ),
        _evidence(
            "sc:fixture:hbm-micron",
            "company",
            "Micron press release",
            "Micron HBM3E is qualified for AI training workloads.",
            "Anchors company:micron.",
            confidence=0.8,
            published_at=now,
        ),
        _evidence(
            "sc:fixture:net-broadcom",
            "company",
            "Broadcom product page",
            "Broadcom Tomahawk switches are deployed in AI clusters.",
            "Anchors company:broadcom.",
            confidence=0.85,
            published_at=now,
        ),
        _evidence(
            "sc:fixture:net-arista",
            "company",
            "Arista product page",
            "Arista 800-series switches are common in AI fabrics.",
            "Anchors company:arista.",
            confidence=0.85,
            published_at=now,
        ),
    ]
    nodes = [
        _node("company:openai", "company", "OpenAI", depth=0, confidence=0.95),
        _node(
            "product:chatgpt",
            "product",
            "ChatGPT",
            parent_node_id="company:openai",
            depth=0,
            confidence=0.95,
            evidence_ids=["sc:fixture:chatgpt-product"],
        ),
        _node(
            "service:cloud-compute",
            "service",
            "Cloud compute",
            parent_node_id="product:chatgpt",
            depth=1,
            confidence=0.9,
        ),
        _node(
            "company:microsoft",
            "company",
            "Microsoft",
            ticker="MSFT",
            parent_node_id="service:cloud-compute",
            depth=2,
            confidence=0.9,
            evidence_ids=["sc:fixture:cloud-azure"],
        ),
        _node(
            "company:oracle",
            "company",
            "Oracle",
            ticker="ORCL",
            parent_node_id="service:cloud-compute",
            depth=2,
            confidence=0.8,
            evidence_ids=["sc:fixture:cloud-oracle"],
        ),
        _node(
            "company:coreweave",
            "company",
            "CoreWeave",
            parent_node_id="service:cloud-compute",
            depth=2,
            confidence=0.85,
            evidence_ids=["sc:fixture:cloud-coreweave"],
        ),
        _node(
            "component:gpu-accelerator",
            "component",
            "GPU accelerator",
            parent_node_id="service:cloud-compute",
            depth=2,
            confidence=0.95,
        ),
        _node(
            "company:nvidia",
            "company",
            "NVIDIA",
            ticker="NVDA",
            parent_node_id="component:gpu-accelerator",
            depth=3,
            confidence=0.95,
            evidence_ids=["sc:fixture:gpu-nvidia"],
        ),
        _node(
            "component:cpu",
            "component",
            "CPU",
            parent_node_id="service:cloud-compute",
            depth=2,
            confidence=0.9,
        ),
        _node(
            "company:amd",
            "company",
            "AMD",
            ticker="AMD",
            parent_node_id="component:cpu",
            depth=3,
            confidence=0.85,
            evidence_ids=["sc:fixture:cpu-amd"],
        ),
        _node(
            "company:intel",
            "company",
            "Intel",
            ticker="INTC",
            parent_node_id="component:cpu",
            depth=3,
            confidence=0.9,
            evidence_ids=["sc:fixture:cpu-intel"],
        ),
        _node(
            "component:hbm-memory",
            "component",
            "HBM memory",
            parent_node_id="component:gpu-accelerator",
            depth=3,
            confidence=0.9,
        ),
        _node(
            "company:sk-hynix",
            "company",
            "SK Hynix",
            parent_node_id="component:hbm-memory",
            depth=3,
            confidence=0.9,
            evidence_ids=["sc:fixture:hbm-hynix"],
        ),
        _node(
            "company:samsung",
            "company",
            "Samsung",
            ticker="005930.KS",
            parent_node_id="component:hbm-memory",
            depth=3,
            confidence=0.8,
            evidence_ids=["sc:fixture:hbm-samsung"],
        ),
        _node(
            "company:micron",
            "company",
            "Micron",
            ticker="MU",
            parent_node_id="component:hbm-memory",
            depth=3,
            confidence=0.8,
            evidence_ids=["sc:fixture:hbm-micron"],
        ),
        _node(
            "component:networking",
            "component",
            "Networking",
            parent_node_id="service:cloud-compute",
            depth=2,
            confidence=0.85,
        ),
        _node(
            "company:broadcom",
            "company",
            "Broadcom",
            ticker="AVGO",
            parent_node_id="component:networking",
            depth=3,
            confidence=0.85,
            evidence_ids=["sc:fixture:net-broadcom"],
        ),
        _node(
            "company:arista",
            "company",
            "Arista",
            ticker="ANET",
            parent_node_id="component:networking",
            depth=3,
            confidence=0.85,
            evidence_ids=["sc:fixture:net-arista"],
        ),
        _node(
            "energy:datacenter-power",
            "energy",
            "Data center power",
            parent_node_id="service:cloud-compute",
            depth=2,
            confidence=0.8,
        ),
    ]
    links = [
        _edge("e-chatgpt-cloud", "product:chatgpt", "service:cloud-compute", "requires", 1.0,
              evidence_ids=["sc:fixture:chatgpt-product"]),
        _edge("e-cloud-microsoft", "service:cloud-compute", "company:microsoft", "supplied_by", 0.7,
              evidence_ids=["sc:fixture:cloud-azure"]),
        _edge("e-cloud-oracle", "service:cloud-compute", "company:oracle", "supplied_by", 0.5,
              evidence_ids=["sc:fixture:cloud-oracle"]),
        _edge("e-cloud-coreweave", "service:cloud-compute", "company:coreweave", "supplied_by", 0.6,
              evidence_ids=["sc:fixture:cloud-coreweave"]),
        _edge("e-cloud-gpu", "service:cloud-compute", "component:gpu-accelerator", "requires", 0.9,
              evidence_ids=["sc:fixture:gpu-nvidia"]),
        _edge("e-gpu-nvidia", "component:gpu-accelerator", "company:nvidia", "manufactured_by", 1.0,
              evidence_ids=["sc:fixture:gpu-nvidia"]),
        _edge("e-cloud-cpu", "service:cloud-compute", "component:cpu", "requires", 0.55,
              evidence_ids=["sc:fixture:cpu-amd", "sc:fixture:cpu-intel"]),
        _edge("e-cpu-amd", "component:cpu", "company:amd", "manufactured_by", 0.7,
              evidence_ids=["sc:fixture:cpu-amd"]),
        _edge("e-cpu-intel", "component:cpu", "company:intel", "manufactured_by", 0.7,
              evidence_ids=["sc:fixture:cpu-intel"]),
        _edge("e-gpu-hbm", "component:gpu-accelerator", "component:hbm-memory", "requires", 0.9,
              evidence_ids=["sc:fixture:hbm-hynix"]),
        _edge("e-hbm-hynix", "component:hbm-memory", "company:sk-hynix", "manufactured_by", 0.85,
              evidence_ids=["sc:fixture:hbm-hynix"]),
        _edge("e-hbm-samsung", "component:hbm-memory", "company:samsung", "manufactured_by", 0.7,
              evidence_ids=["sc:fixture:hbm-samsung"]),
        _edge("e-hbm-micron", "component:hbm-memory", "company:micron", "manufactured_by", 0.6,
              evidence_ids=["sc:fixture:hbm-micron"]),
        _edge("e-cloud-net", "service:cloud-compute", "component:networking", "requires", 0.45,
              evidence_ids=["sc:fixture:net-broadcom", "sc:fixture:net-arista"]),
        _edge("e-net-broadcom", "component:networking", "company:broadcom", "manufactured_by", 0.7,
              evidence_ids=["sc:fixture:net-broadcom"]),
        _edge("e-net-arista", "component:networking", "company:arista", "manufactured_by", 0.7,
              evidence_ids=["sc:fixture:net-arista"]),
        _edge("e-cloud-power", "service:cloud-compute", "energy:datacenter-power", "powered_by", 0.75,
              evidence_ids=["sc:fixture:chatgpt-product"]),
    ]
    sankey = {
        "nodes": nodes,
        "links": links,
        "evidence": evidence,
        "warnings": [],
    }
    return {
        "request": request,
        "nodes": nodes,
        "links": links,
        "evidence": evidence,
        "sankey": sankey,
        "expected_expansions": {
            "component:cpu": {
                "subgraph_nodes": [
                    "company:amd",
                    "company:intel",
                    "service:foundry",
                    "company:tsmc",
                    "company:intel-foundry",
                    "component:lithography",
                    "company:asml",
                    "service:eda",
                    "company:synopsys",
                    "company:cadence",
                ],
                "subgraph_edges": [
                    ("component:cpu", "company:amd", "supplied_by"),
                    ("component:cpu", "company:intel", "supplied_by"),
                    ("component:cpu", "service:foundry", "depends_on"),
                    ("service:foundry", "company:tsmc", "supplied_by"),
                    ("service:foundry", "company:intel-foundry", "supplied_by"),
                    ("component:cpu", "component:lithography", "enabled_by"),
                    ("component:lithography", "company:asml", "supplied_by"),
                    ("component:cpu", "service:eda", "enabled_by"),
                    ("service:eda", "company:synopsys", "supplied_by"),
                    ("service:eda", "company:cadence", "supplied_by"),
                ],
            }
        },
    }


def write_default_fixture(path: Path | None = None) -> Path:
    """Persist the default fixture as JSON.

    Used by the test suite bootstrap. Returns the path that was
    written so callers can re-read the file.
    """
    target = path or DEFAULT_FIXTURE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(build_default_fixture(), indent=2),
        encoding="utf-8",
    )
    return target


def load_default_fixture(path: Path | None = None) -> dict[str, Any]:
    """Load the JSON fixture, falling back to the in-memory build."""
    target = path or DEFAULT_FIXTURE_PATH
    if not target.exists():
        return build_default_fixture()
    return json.loads(target.read_text(encoding="utf-8"))


__all__ = [
    "DEFAULT_FIXTURE_PATH",
    "FIXTURE_DIR",
    "build_default_fixture",
    "load_default_fixture",
    "write_default_fixture",
]
