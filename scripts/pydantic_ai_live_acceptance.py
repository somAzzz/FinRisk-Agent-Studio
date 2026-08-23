#!/usr/bin/env python3
"""Run the synthetic Pydantic AI live-provider migration contract."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.ai.live_acceptance import run_live_acceptance  # noqa: E402
from src.ai.model_factory import (  # noqa: E402
    build_agent_model,
    resolve_agent_model_config,
)
from src.config import Settings  # noqa: E402
from src.schemas.llm_config import LLMRunConfig  # noqa: E402
from src.security.redaction import redact_text  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify one live provider with a synthetic local tool call and "
            "strict Pydantic output. No project or user data is sent."
        )
    )
    parser.add_argument(
        "--provider",
        choices=("sglang", "vllm", "deepseek", "openai"),
        required=True,
    )
    parser.add_argument("--base-url")
    parser.add_argument("--model")
    parser.add_argument("--output", help="Optional JSON report path.")
    return parser.parse_args()


def _emit(payload: dict, output: str | None) -> None:
    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    print(rendered)
    if output:
        path = Path(output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")


def main() -> int:
    args = _parse_args()
    try:
        config = resolve_agent_model_config(
            LLMRunConfig(
                provider=args.provider,
                base_url=args.base_url,
                model=args.model,
            ),
            settings=Settings(),
        )
        report = asyncio.run(
            run_live_acceptance(
                provider=config.provider,
                base_url=config.base_url,
                model_name=config.model,
                model=build_agent_model(config),
            )
        )
    except Exception as exc:
        _emit(
            {
                "status": "fail",
                "provider": args.provider,
                "error_type": type(exc).__name__,
                "error": redact_text(str(exc)),
            },
            args.output,
        )
        return 1

    _emit({"status": "pass", **report.model_dump(mode="json")}, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
