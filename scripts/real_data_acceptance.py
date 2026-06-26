#!/usr/bin/env python3
"""Reusable real-data acceptance runner for FinText-LLM.

The runner validates the production-shaped paths against a running API
and, optionally, the frontend:

- FinRisk workflow with demo/cached disabled.
- LLM call log, chunk validation, section location, lifecycle outputs.
- Supply-chain explorer with SearchRouter + LLM supplier extraction.
- Optional Playwright frontend smoke using the existing e2e script.

It writes a machine-readable report so regressions can be compared
across local runs, CI, and model/provider changes.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

TERMINAL_STATUSES = {"completed", "needs_review", "failed"}
DEFAULT_GOAL = "Identify macro, policy and supply-chain risks that changed recently."


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class AcceptanceError(RuntimeError):
    """Raised when a required acceptance check fails."""


class ApiClient:
    def __init__(self, base_url: str, timeout_s: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def get(self, path: str) -> dict[str, Any]:
        return self._request("GET", path)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, payload)

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"} if body is not None else {}
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=headers,
            method=method,
        )
        with urlopen(request, timeout=self.timeout_s) as response:
            raw = response.read().decode()
        return json.loads(raw) if raw else {}


def main() -> int:
    args = _parse_args()
    report: dict[str, Any] = {
        "started_at": _now_ms(),
        "api_base": args.api_base,
        "frontend_url": args.frontend_url,
        "llm_provider": args.llm_provider,
        "checks": [],
        "artifacts": {},
    }
    client = ApiClient(args.api_base, args.request_timeout_s)
    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        _record(report, check_api_health(client))
        finrisk = run_finrisk_acceptance(client, args)
        report["artifacts"]["finrisk"] = finrisk
        _record(report, finrisk["check"])
        supply_chain = run_supply_chain_acceptance(client, args)
        report["artifacts"]["supply_chain"] = supply_chain
        _record(report, supply_chain["check"])
        if not args.skip_frontend:
            frontend = run_frontend_acceptance(args)
            report["artifacts"]["frontend"] = frontend
            _record(report, frontend["check"])
        report["status"] = "pass"
    except Exception as exc:
        report["status"] = "fail"
        report["error"] = f"{type(exc).__name__}: {exc}"
        _write_report(output_path, report)
        print(f"real-data acceptance failed: {exc}", file=sys.stderr)
        print(f"report: {output_path}", file=sys.stderr)
        return 1

    _write_report(output_path, report)
    print("real-data acceptance passed")
    print(f"report: {output_path}")
    return 0


def run_finrisk_acceptance(client: ApiClient, args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "ticker": args.ticker,
        "analysis_goal": args.analysis_goal,
        "time_horizon": args.time_horizon,
        "year": args.year,
        "sources": args.sources,
        "max_browser_steps": args.max_browser_steps,
        "demo_mode": False,
        "cached_mode": False,
        "llm_config": _llm_config(args),
    }
    if payload["year"] is None:
        payload.pop("year")
    start = client.post("/workflows/finrisk/run", payload)
    run_id = _require_str(start, "run_id")
    status = poll_status(
        lambda: client.get(f"/workflows/{run_id}"),
        timeout_s=args.workflow_timeout_s,
        label=f"finrisk:{run_id}",
    )
    report = client.get(f"/workflows/{run_id}/report")
    llm_log = client.get(f"/workflows/{run_id}/llm_log")
    chunks = client.get(f"/workflows/{run_id}/chunks")
    sections = client.get(f"/workflows/{run_id}/sections")
    lifecycles = client.get(f"/workflows/{run_id}/lifecycles")
    evaluation = client.get(f"/workflows/{run_id}/evaluation")
    trace = client.get(f"/workflows/{run_id}/trace")

    _assert_real_modes(payload)
    _assert_status_ok(status, "FinRisk")
    _assert_report(report)
    _assert_trace_steps(status.get("trace", []), min_steps=args.min_finrisk_steps)
    if args.require_llm:
        _assert_llm_log(llm_log.get("llm_log", []), args.llm_provider)
    _assert_nonempty(chunks.get("chunk_validations", []), "FinRisk chunk validations")
    _assert_nonempty(sections.get("section_locations", []), "FinRisk section locations")
    _assert_nonempty(lifecycles.get("risk_lifecycles", []), "FinRisk lifecycle annotations")
    _assert_no_fail_evaluation(evaluation)

    check = CheckResult(
        name="finrisk_real_data",
        status="pass",
        data={
            "run_id": run_id,
            "workflow_status": status.get("status"),
            "risk_count": status.get("risk_count"),
            "evidence_count": status.get("evidence_count"),
            "llm_call_count": len(llm_log.get("llm_log", [])),
            "chunk_count": len(chunks.get("chunk_validations", [])),
            "section_count": len(sections.get("section_locations", [])),
            "lifecycle_count": len(lifecycles.get("risk_lifecycles", [])),
            "final_status": evaluation.get("final_status"),
        },
    )
    return {
        "check": asdict(check),
        "request": payload,
        "status": status,
        "report_summary": _report_summary(report),
        "llm_log": llm_log,
        "chunks": chunks,
        "sections": sections,
        "lifecycles": lifecycles,
        "evaluation": evaluation,
        "trace": trace,
    }


def run_supply_chain_acceptance(client: ApiClient, args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "company_name": args.supply_company,
        "ticker": args.supply_ticker,
        "product_name": args.supply_product,
        "max_depth": args.supply_max_depth,
        "max_suppliers_per_node": args.supply_max_suppliers,
        "focus_regions": [],
        "include_private_companies": True,
        "demo_mode": False,
        "cached_mode": False,
        "llm_config": _llm_config(args),
    }
    if payload["ticker"] is None:
        payload.pop("ticker")
    start = client.post("/supply-chain/explore", payload)
    run_id = _require_str(start, "run_id")
    status = poll_status(
        lambda: client.get(f"/supply-chain/{run_id}"),
        timeout_s=args.workflow_timeout_s,
        label=f"supply-chain:{run_id}",
    )
    sankey = client.get(f"/supply-chain/{run_id}/sankey")

    _assert_real_modes(payload)
    _assert_status_ok(status, "Supply chain")
    _assert_supply_chain_graph(status, sankey, args)
    if args.require_llm:
        _assert_supply_chain_llm_trace(status.get("trace", []), args.llm_provider)

    check = CheckResult(
        name="supply_chain_real_data",
        status="pass",
        data={
            "run_id": run_id,
            "workflow_status": status.get("status"),
            "node_count": status.get("node_count"),
            "link_count": status.get("link_count"),
            "evidence_count": status.get("evidence_count"),
            "provider_calls": _provider_call_summary(status.get("trace", [])),
            "final_status": (status.get("evaluation") or {}).get("final_status"),
        },
    )
    return {
        "check": asdict(check),
        "request": payload,
        "status": status,
        "sankey": sankey,
    }


def run_frontend_acceptance(args: argparse.Namespace) -> dict[str, Any]:
    if not _url_available(args.frontend_url, timeout_s=args.request_timeout_s):
        raise AcceptanceError(
            f"frontend unavailable at {args.frontend_url}; use --skip-frontend to run API-only acceptance"
        )
    env = os.environ.copy()
    env["FRONTEND_URL"] = args.frontend_url
    env.setdefault("PLAYWRIGHT_BROWSERS_PATH", os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""))
    started = time.perf_counter()
    proc = subprocess.run(
        ["node", "e2e/real-mode.cjs"],
        cwd=Path("frontend"),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if proc.returncode != 0:
        raise AcceptanceError(
            "frontend Playwright real-mode check failed\n"
            f"stdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}"
        )
    check = CheckResult(
        name="frontend_real_mode",
        status="pass",
        detail=proc.stdout.strip(),
        data={"latency_ms": elapsed_ms},
    )
    return {"check": asdict(check), "stdout": proc.stdout, "stderr": proc.stderr}


def check_api_health(client: ApiClient) -> CheckResult:
    root = client.get("/")
    workflows = client.get("/workflows/health")
    supply_chain = client.get("/supply-chain/health")
    if root.get("name") != "FinRisk Agent Studio":
        raise AcceptanceError("API root did not return FinRisk Agent Studio metadata")
    return CheckResult(
        name="api_health",
        status="pass",
        data={
            "root": root,
            "workflows": workflows,
            "supply_chain": supply_chain,
        },
    )


def poll_status(fetch, *, timeout_s: float, label: str) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = fetch()
        if last.get("status") in TERMINAL_STATUSES:
            return last
        time.sleep(1.0)
    raise AcceptanceError(f"timed out waiting for {label}; last={last}")


def _assert_real_modes(payload: dict[str, Any]) -> None:
    if payload.get("demo_mode") is not False or payload.get("cached_mode") is not False:
        raise AcceptanceError("acceptance request must disable demo_mode and cached_mode")


def _assert_status_ok(status: dict[str, Any], label: str) -> None:
    if status.get("status") == "failed":
        raise AcceptanceError(f"{label} workflow failed: {status}")
    if status.get("status") not in {"completed", "needs_review"}:
        raise AcceptanceError(f"{label} workflow did not finish: {status.get('status')}")


def _assert_report(report: dict[str, Any]) -> None:
    markdown = report.get("markdown") or ""
    if not markdown.strip():
        raise AcceptanceError("FinRisk report markdown is empty")
    if "not investment advice" not in markdown.lower() and "disclaimer" not in markdown.lower():
        raise AcceptanceError("FinRisk report is missing disclaimer language")


def _assert_trace_steps(trace: list[dict[str, Any]], *, min_steps: int) -> None:
    completed = [event for event in trace if event.get("status") == "completed"]
    if len(completed) < min_steps:
        raise AcceptanceError(f"expected at least {min_steps} completed steps, got {len(completed)}")


def _assert_llm_log(calls: list[dict[str, Any]], provider: str) -> None:
    _assert_nonempty(calls, "FinRisk LLM log")
    ok_calls = [
        call for call in calls
        if not call.get("error") and (call.get("response_text") or "").strip()
    ]
    if not ok_calls:
        raise AcceptanceError("FinRisk LLM log has no successful non-empty responses")
    providers = {str(call.get("provider")) for call in calls}
    if provider and provider not in providers:
        raise AcceptanceError(f"expected FinRisk LLM provider {provider!r}, got {sorted(providers)}")
    for call in ok_calls:
        if not call.get("prompt_text"):
            raise AcceptanceError(f"LLM call {call.get('call_id')} is missing prompt_text")
        if int(call.get("latency_ms") or 0) < 0:
            raise AcceptanceError(f"LLM call {call.get('call_id')} has invalid latency")


def _assert_no_fail_evaluation(evaluation: dict[str, Any]) -> None:
    final_status = evaluation.get("final_status")
    if final_status == "fail":
        raise AcceptanceError(f"workflow evaluation failed: {evaluation}")


def _assert_supply_chain_graph(
    status: dict[str, Any],
    sankey_response: dict[str, Any],
    args: argparse.Namespace,
) -> None:
    if int(status.get("node_count") or 0) < args.min_supply_nodes:
        raise AcceptanceError(f"supply-chain node count too low: {status.get('node_count')}")
    if int(status.get("link_count") or 0) < args.min_supply_links:
        raise AcceptanceError(f"supply-chain link count too low: {status.get('link_count')}")
    if int(status.get("evidence_count") or 0) < args.min_supply_evidence:
        raise AcceptanceError(f"supply-chain evidence count too low: {status.get('evidence_count')}")
    sankey = sankey_response.get("sankey") or {}
    nodes = sankey.get("nodes") or []
    links = sankey.get("links") or []
    evidence = sankey.get("evidence") or []
    if not nodes or not links:
        raise AcceptanceError("supply-chain sankey payload is empty")
    evidence_ids = {row.get("evidence_id") for row in evidence}
    for link in links:
        if link.get("relation_type") != "hypothesized":
            missing = [eid for eid in link.get("evidence_ids", []) if eid not in evidence_ids]
            if missing:
                raise AcceptanceError(f"supply-chain link has missing evidence ids: {missing}")
    warnings = "\n".join(status.get("warnings") or [])
    if "no demo fixture" in warnings.lower():
        raise AcceptanceError("supply-chain real run hit demo fixture warning")


def _assert_supply_chain_llm_trace(trace: list[dict[str, Any]], provider: str) -> None:
    provider_calls = [
        call
        for event in trace
        for call in event.get("provider_calls", [])
    ]
    _assert_nonempty(provider_calls, "Supply-chain provider calls")
    operations = {call.get("operation") for call in provider_calls}
    if "search" not in operations:
        raise AcceptanceError("supply-chain trace has no search provider call")
    llm_calls = [
        call for call in provider_calls
        if call.get("operation") == "llm_extract_suppliers"
    ]
    _assert_nonempty(llm_calls, "Supply-chain LLM extraction provider calls")
    successful = [call for call in llm_calls if call.get("status") == "success"]
    if not successful:
        raise AcceptanceError(f"supply-chain LLM extraction had no success: {llm_calls}")
    providers = {str(call.get("provider")) for call in llm_calls}
    if provider and provider not in providers:
        raise AcceptanceError(f"expected supply-chain LLM provider {provider!r}, got {sorted(providers)}")


def _provider_call_summary(trace: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for event in trace:
        for call in event.get("provider_calls", []):
            key = f"{call.get('operation')}:{call.get('status')}"
            summary[key] = summary.get(key, 0) + 1
    return summary


def _assert_nonempty(value: list[Any], label: str) -> None:
    if not value:
        raise AcceptanceError(f"{label} is empty")


def _llm_config(args: argparse.Namespace) -> dict[str, Any]:
    config: dict[str, Any] = {"provider": args.llm_provider}
    if args.llm_base_url:
        config["base_url"] = args.llm_base_url
    if args.llm_model:
        config["model"] = args.llm_model
    return config


def _report_summary(report: dict[str, Any]) -> dict[str, Any]:
    markdown = report.get("markdown") or ""
    return {
        "status": report.get("status"),
        "evaluation": report.get("evaluation"),
        "markdown_chars": len(markdown),
        "markdown_prefix": markdown[:500],
    }


def _require_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise AcceptanceError(f"response missing string {key}: {payload}")
    return value


def _url_available(url: str, *, timeout_s: float) -> bool:
    try:
        request = Request(url, method="GET")
        with urlopen(request, timeout=timeout_s):
            return True
    except (OSError, URLError):
        return False


def _record(report: dict[str, Any], check: dict[str, Any] | CheckResult) -> None:
    report["checks"].append(asdict(check) if isinstance(check, CheckResult) else check)


def _write_report(path: Path, report: dict[str, Any]) -> None:
    report["completed_at"] = _now_ms()
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run reusable real-data acceptance checks against a running FinText-LLM stack.",
    )
    parser.add_argument("--api-base", default=os.environ.get("API_BASE", "http://127.0.0.1:8000"))
    parser.add_argument("--frontend-url", default=os.environ.get("FRONTEND_URL", "http://127.0.0.1:5173"))
    parser.add_argument("--output", default="artifacts/real_data_acceptance/latest.json")
    parser.add_argument("--request-timeout-s", type=float, default=30.0)
    parser.add_argument("--workflow-timeout-s", type=float, default=240.0)
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--require-llm", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--llm-provider", default=os.environ.get("LLM_PROVIDER", "sglang"))
    parser.add_argument("--llm-base-url", default=os.environ.get("LLM_BASE_URL"))
    parser.add_argument("--llm-model", default=os.environ.get("LLM_MODEL"))
    parser.add_argument("--ticker", default="AAPL")
    parser.add_argument("--analysis-goal", default=DEFAULT_GOAL)
    parser.add_argument("--time-horizon", default="6-12 months")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--sources", nargs="+", default=["filing", "web", "graph"])
    parser.add_argument("--max-browser-steps", type=int, default=3)
    parser.add_argument("--min-finrisk-steps", type=int, default=8)
    parser.add_argument("--supply-company", default="NVIDIA")
    parser.add_argument("--supply-ticker", default=None)
    parser.add_argument("--supply-product", default="GPU")
    parser.add_argument("--supply-max-depth", type=int, default=3)
    parser.add_argument("--supply-max-suppliers", type=int, default=3)
    parser.add_argument("--min-supply-nodes", type=int, default=3)
    parser.add_argument("--min-supply-links", type=int, default=1)
    parser.add_argument("--min-supply-evidence", type=int, default=1)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
