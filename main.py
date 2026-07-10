"""Convenience CLI for the FinRisk API and workflow runner."""

from __future__ import annotations

import argparse


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fintext-llm",
        description="Run the FinRisk Agent Studio API or a company workflow.",
    )
    commands = parser.add_subparsers(dest="command")
    api = commands.add_parser("api", help="Start the FastAPI service")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8000)
    api.add_argument("--reload", action="store_true")
    commands.add_parser(
        "workflow",
        help="Run the FinRisk workflow; remaining options go to the workflow CLI",
        add_help=False,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args, remaining = parser.parse_known_args(argv)
    if args.command == "api":
        import uvicorn

        uvicorn.run(
            "src.api.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
        return 0
    if args.command == "workflow":
        from src.workflows.finrisk_workflow import main as workflow_main

        return workflow_main(remaining)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
