#!/usr/bin/env python3
"""Run an isolated, reusable Research Journal acceptance scenario.

The runner starts a dedicated FastAPI instance and Vite dev server backed by
per-run SQLite databases. It reuses the configured local LLM and Neo4j, drives
the browser through the complete analyst workflow, and writes a machine-
readable report plus service logs and screenshots under ``artifacts/``.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config/acceptance/research_journal_live.json"


class AcceptanceError(RuntimeError):
    """A required live-acceptance invariant failed."""


class ApiClient:
    def __init__(self, base_url: str, api_key: str, timeout_s: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s

    def get(self, path: str) -> Any:
        request = Request(
            f"{self.base_url}{path}",
            headers={"X-API-Key": self.api_key},
        )
        with urlopen(request, timeout=self.timeout_s) as response:
            raw = response.read().decode()
        return json.loads(raw) if raw else None


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    config = json.loads(config_path.read_text())
    validate_config(config)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else (
        ROOT / "artifacts/research-journal-live" / f"{config['scenario_id']}-{stamp}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    browser_report = run_dir / "browser-report.json"
    final_report = run_dir / "report.json"
    screenshot_dir = run_dir / "screenshots"
    screenshot_dir.mkdir(exist_ok=True)

    api_port = int(config["api_port"])
    frontend_port = int(config["frontend_port"])
    api_base = f"http://127.0.0.1:{api_port}"
    frontend_url = f"http://127.0.0.1:{frontend_port}"
    api_key = str(config["api_key"])
    processes: list[subprocess.Popen[str]] = []
    logs: list[Any] = []
    started = time.perf_counter()

    report: dict[str, Any] = {
        "scenario_id": config["scenario_id"],
        "started_at": datetime.now(UTC).isoformat(),
        "config_path": str(config_path),
        "run_dir": str(run_dir),
        "services": {"api": api_base, "frontend": frontend_url},
        "llm": config["llm"],
        "checks": [],
        "status": "running",
    }

    try:
        check_local_llm(config, report)
        if not args.reuse_services:
            processes, logs = start_isolated_services(config, run_dir, api_base, frontend_url)
        wait_for_url(f"{api_base}/", float(config["timeouts"]["service_start_s"]))
        wait_for_url(frontend_url, float(config["timeouts"]["service_start_s"]))

        browser_env = os.environ.copy()
        browser_env.update(
            {
                "RESEARCH_JOURNAL_LIVE_CONFIG": str(config_path),
                "RESEARCH_JOURNAL_LIVE_REPORT": str(browser_report),
                "RESEARCH_JOURNAL_SCREENSHOT_DIR": str(screenshot_dir),
                "FRONTEND_URL": frontend_url,
                "API_BASE_URL": api_base,
                "FINRISK_API_KEY": api_key,
                "HEADED": "1" if args.headed else "0",
            }
        )
        browser = subprocess.run(
            ["node", "e2e/research-journal-live.cjs"],
            cwd=ROOT / "frontend",
            env=browser_env,
            text=True,
            capture_output=True,
            timeout=float(config["timeouts"]["workflow_ms"]) / 1000 + 240,
            check=False,
        )
        report["browser"] = {
            "returncode": browser.returncode,
            "stdout": browser.stdout,
            "stderr": browser.stderr,
        }
        if browser.returncode != 0:
            raise AcceptanceError(
                "Research Journal browser scenario failed\n"
                f"stdout:\n{browser.stdout}\n\nstderr:\n{browser.stderr}"
            )
        if not browser_report.exists():
            raise AcceptanceError("browser scenario did not write its structured report")
        browser_data = json.loads(browser_report.read_text())
        report["browser"]["result"] = browser_data

        client = ApiClient(api_base, api_key)
        verify_persisted_state(client, config, browser_data, report)
        report["status"] = "pass"
    except Exception as exc:
        report["status"] = "fail"
        report["error"] = f"{type(exc).__name__}: {exc}"
        final_report.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"Research Journal live acceptance failed: {exc}", file=sys.stderr)
        print(f"report: {final_report}", file=sys.stderr)
        return 1
    finally:
        if processes and not args.keep_services:
            stop_processes(processes)
        for handle in logs:
            handle.close()

    report["completed_at"] = datetime.now(UTC).isoformat()
    report["duration_ms"] = int((time.perf_counter() - started) * 1000)
    final_report.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print("Research Journal live acceptance passed")
    print(f"report: {final_report}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output-dir")
    parser.add_argument("--reuse-services", action="store_true")
    parser.add_argument("--keep-services", action="store_true")
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


def validate_config(config: dict[str, Any]) -> None:
    required = {
        "scenario_id", "api_port", "frontend_port", "api_key", "primary",
        "peer", "expectation", "valuation", "llm", "timeouts",
    }
    missing = sorted(required - config.keys())
    if missing:
        raise AcceptanceError(f"scenario config is missing: {', '.join(missing)}")
    for key in ("provider", "base_url", "model"):
        if not str(config["llm"].get(key, "")).strip():
            raise AcceptanceError(f"llm.{key} must not be empty")


def check_local_llm(config: dict[str, Any], report: dict[str, Any]) -> None:
    base = str(config["llm"]["base_url"]).rstrip("/")
    try:
        with urlopen(f"{base}/models", timeout=10) as response:
            payload = json.loads(response.read().decode())
    except (URLError, TimeoutError) as exc:
        raise AcceptanceError(f"local LLM is unavailable at {base}: {exc}") from exc
    models = payload.get("data") or []
    expected = str(config["llm"]["model"])
    match = next((item for item in models if item.get("id") == expected), None)
    if match is None:
        raise AcceptanceError(f"local LLM model {expected!r} is not served: {models}")
    report["checks"].append(
        {
            "name": "local_llm",
            "status": "pass",
            "model": expected,
            "max_model_len": match.get("max_model_len"),
        }
    )


def start_isolated_services(
    config: dict[str, Any],
    run_dir: Path,
    api_base: str,
    frontend_url: str,
) -> tuple[list[subprocess.Popen[str]], list[Any]]:
    del frontend_url
    api_log = (run_dir / "api.log").open("w")
    frontend_log = (run_dir / "frontend.log").open("w")
    env = os.environ.copy()
    env.update(
        {
            "FINRISK_API_KEYS": str(config["api_key"]),
            "RESEARCH_SNAPSHOT_PATH": str(run_dir / "research-snapshots.sqlite"),
            "RESEARCH_JOURNAL_PATH": str(run_dir / "research-journal.sqlite"),
            "RATE_LIMIT_RPM": "600",
            "RATE_LIMIT_BURST": "600",
            "FINRISK_SKIP_BACKGROUND": "0",
        }
    )
    api = subprocess.Popen(
        [
            "uv",
            "run",
            "uvicorn",
            "src.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(config["api_port"]),
        ],
        cwd=ROOT,
        env=env,
        stdout=api_log,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    frontend_env = env.copy()
    frontend_env.update(
        {
            "FINRISK_API_PROXY_TARGET": api_base,
            "FINRISK_API_KEY": str(config["api_key"]),
        }
    )
    frontend = subprocess.Popen(
        [
            "npm",
            "run",
            "dev:normal",
            "--",
            "--host",
            "127.0.0.1",
            "--port",
            str(config["frontend_port"]),
        ],
        cwd=ROOT / "frontend",
        env=frontend_env,
        stdout=frontend_log,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    return [api, frontend], [api_log, frontend_log]


def wait_for_url(url: str, timeout_s: float) -> None:
    deadline = time.time() + timeout_s
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
        time.sleep(0.5)
    raise AcceptanceError(f"service did not become ready at {url}: {last_error}")


def verify_persisted_state(
    client: ApiClient,
    config: dict[str, Any],
    browser: dict[str, Any],
    report: dict[str, Any],
) -> None:
    primary = str(config["primary"]["ticker"]).upper()
    peer = str(config["peer"]["ticker"]).upper()
    snapshots = client.get(f"/research/snapshots?ticker={primary}&limit=20")
    peer_snapshots = client.get(f"/research/snapshots?ticker={peer}&limit=20")
    theses = client.get(f"/research/theses?ticker={primary}")
    watchlist = client.get("/research/watchlist")
    valuation_history = client.get(f"/research/valuation/history/{primary}?limit=50")
    drafts = client.get(f"/research/post-earnings/drafts?ticker={primary}")
    peer_groups = client.get("/research/peer-groups")

    if len(snapshots) < 2:
        raise AcceptanceError(f"expected at least two {primary} snapshots, got {len(snapshots)}")
    if not peer_snapshots:
        raise AcceptanceError(f"expected a {peer} snapshot")
    if not any(item.get("statement") == config["primary"]["thesis"] for item in theses):
        raise AcceptanceError("saved live thesis was not persisted")
    if not any(item.get("ticker") == primary for item in watchlist):
        raise AcceptanceError("primary ticker was not persisted to the Watchlist")
    kinds = {item.get("kind") for item in valuation_history}
    required_kinds = {"scenario", "sensitivity", "multiple", "dcf"}
    if not required_kinds.issubset(kinds):
        raise AcceptanceError(f"valuation history missing {sorted(required_kinds - kinds)}")
    if not any(item.get("status") == "confirmed" for item in drafts):
        raise AcceptanceError("post-earnings review was not confirmed")
    if not any(item.get("name") == config["peer"]["group_name"] for item in peer_groups):
        raise AcceptanceError("analyst-confirmed peer group was not persisted")

    workflow_id = str(browser.get("workflow_run_id") or "")
    if not workflow_id:
        raise AcceptanceError("browser report is missing workflow_run_id")
    workflow = client.get(f"/workflows/{workflow_id}")
    llm_log = client.get(f"/workflows/{workflow_id}/llm_log").get("llm_log", [])
    successful = [
        call
        for call in llm_log
        if call.get("provider") == config["llm"]["provider"]
        and not call.get("error")
        and str(call.get("response_text") or "").strip()
    ]
    if workflow.get("status") not in {"completed", "needs_review"}:
        raise AcceptanceError(f"linked FinRisk workflow did not finish: {workflow.get('status')}")
    if not successful:
        raise AcceptanceError("linked FinRisk workflow has no successful local-LLM call")

    report["checks"].extend(
        [
            {"name": "research_snapshots", "status": "pass", "primary": len(snapshots), "peer": len(peer_snapshots)},
            {"name": "thesis_watchlist", "status": "pass", "theses": len(theses), "watchlist": len(watchlist)},
            {"name": "valuation_history", "status": "pass", "kinds": sorted(kinds)},
            {"name": "peer_review", "status": "pass", "peer_groups": len(peer_groups), "drafts": len(drafts)},
            {
                "name": "local_llm_workflow",
                "status": "pass",
                "run_id": workflow_id,
                "successful_calls": len(successful),
            },
        ]
    )
    report["persisted"] = {
        "primary_snapshot_ids": [item.get("snapshot_id") for item in snapshots],
        "peer_snapshot_ids": [item.get("snapshot_id") for item in peer_snapshots],
        "valuation_snapshot_ids": [item.get("assumption_snapshot_id") for item in valuation_history],
        "workflow_run_id": workflow_id,
    }


def stop_processes(processes: list[subprocess.Popen[str]]) -> None:
    for process in reversed(processes):
        if process.poll() is None:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
    deadline = time.time() + 10
    for process in reversed(processes):
        if process.poll() is not None:
            continue
        timeout = max(0.1, deadline - time.time())
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)


if __name__ == "__main__":
    sys.exit(main())
