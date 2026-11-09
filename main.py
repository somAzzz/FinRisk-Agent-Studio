"""Convenience CLI for the FinRisk API and workflow runner."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="finrisk-agent-studio",
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
    annual = commands.add_parser("annual-report", help="Analyze a local or public PDF / ESEF report")
    annual.add_argument("source")
    annual.add_argument("--options", type=Path, help="JSON with as_of, external sources, scenarios and OCR pages")
    annual.add_argument("--extract-only", action="store_true", help="Skip LLM interpretation")
    annual.add_argument("--output", type=Path)
    tracking = commands.add_parser("track-report", help="Discover and audit evidence from one annual report")
    tracking.add_argument("source")
    tracking.add_argument("--as-of", nargs="+", required=True)
    tracking.add_argument("--work", type=Path, required=True)
    tracking.add_argument("--neo4j", action="store_true")
    blind = commands.add_parser("discover-exposures", help="Discover and verify exposures from one annual report")
    blind.add_argument("source", help="Local or online annual PDF")
    blind.add_argument("--output", type=Path, required=True)
    blind.add_argument("--neo4j", action="store_true")
    exposure = commands.add_parser(
        "exposure-replay", help="Trace audited alerts and replay jurisdiction-specific policy"
    )
    exposure.add_argument("--case", type=Path, required=True)
    exposure.add_argument("--tracking", type=Path, required=True, help="Company directory containing P0 snapshots")
    exposure.add_argument("--sources", type=Path, default=Path(".cache/p1/sources"))
    exposure.add_argument("--as-of", nargs="+", required=True)
    exposure.add_argument("--output", type=Path, required=True)
    exposure.add_argument("--neo4j", action="store_true")
    exposure.add_argument("--fetch", action="store_true", help="Retrieve missing pinned originals from case URLs")
    auditor = commands.add_parser("audit-claims", help="Independently audit a batch against a dated report")
    auditor.add_argument("source")
    auditor.add_argument("--claims", type=Path, required=True)
    auditor.add_argument("--as-of", type=date.fromisoformat, required=True)
    auditor.add_argument("--output", type=Path, required=True)
    monitor = commands.add_parser(
        "monitor",
        help="Run one incremental Watchlist research scan",
    )
    monitor.add_argument("--ticker", action="append", dest="tickers")
    monitor.add_argument("--as-of", type=date.fromisoformat)
    monitor.add_argument("--year", type=int)
    monitor.add_argument("--quarter", type=int, choices=(1, 2, 3, 4))
    monitor.add_argument(
        "--minimum-materiality",
        choices=("low", "medium", "high"),
        default="medium",
    )
    monitor.add_argument("--max-workers", type=int, default=2)
    monitor.add_argument("--dry-run", action="store_true")
    monitor.add_argument("--request-interval-seconds", type=float, default=0.0)
    monitor.add_argument("--max-retries", type=int, default=1)
    monitor.add_argument("--source-stale-after-days", type=int)
    database = commands.add_parser(
        "database",
        help="Migrate, back up, or restore a research SQLite database",
    )
    database.add_argument("action", choices=("migrate", "backup", "restore"))
    database.add_argument(
        "--path",
        default=".cache/research_snapshots.sqlite",
        help="Database to migrate, back up, or restore",
    )
    database.add_argument("--destination", help="Backup destination")
    database.add_argument("--backup", help="Backup source used for restore")
    return parser


def _run_database_command(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
) -> int:
    from src.research.database import (
        apply_migrations,
        backup_database,
        restore_database,
    )

    if args.action == "migrate":
        version = apply_migrations(args.path)
        print(f"schema version: {version}")
        return 0
    if args.action == "backup":
        if not args.destination:
            parser.error("database backup requires --destination")
        result = backup_database(args.path, args.destination)
        print(result)
        return 0
    if not args.backup:
        parser.error("database restore requires --backup")
    result = restore_database(args.backup, args.path)
    print(result)
    return 0


def _document_command(args, remaining, parser) -> int:
    if args.command == "discover-exposures":
        if remaining:
            parser.error("Unexpected discover-exposures arguments: " + " ".join(remaining))
        from src.annual_reports.blind import run
        run(args)
        return 0
    if args.command == "exposure-replay":
        if remaining:
            parser.error("Unexpected exposure-replay arguments: " + " ".join(remaining))
        from src.annual_reports.exposure_report import run
        run(args)
        return 0
    if args.command in {"track-report", "audit-claims"}:
        from src.annual_reports.audit import Claim, audit, passages, segment_note_loader, write_report
        from src.annual_reports.tracking import read_primary, replay

        if remaining:
            parser.error("Unexpected arguments: " + " ".join(remaining))
        if args.command == "track-report":
            print(json.dumps(replay(args.source, args.as_of, args.work, neo4j=args.neo4j), indent=2))
        else:
            doc, published, _ = read_primary(args.source)
            pool = passages(doc, published)
            note = segment_note_loader(doc if published <= args.as_of else None)
            claims = json.loads(args.claims.read_text())
            audits = [audit(Claim.model_validate(c), pool, args.as_of, note_loader=note) for c in claims]
            from dataclasses import asdict

            used = {pid for a in audits for v in a["history"] for pid in v["checked"]}
            write_report(
                args.output,
                {"as_of": str(args.as_of), "audits": audits, "evidence": {pid: asdict(pool[pid]) for pid in used}},
            )
        return 0
    from fastapi.encoders import jsonable_encoder

    from src.annual_reports.analysis import Options, analyze
    from src.annual_reports.documents import MAX_BYTES, download

    if remaining:
        parser.error("Unexpected annual-report arguments: " + " ".join(remaining))
    try:
        options = Options.model_validate_json(args.options.read_bytes()) if args.options else Options()
        if args.extract_only:
            options.narrative = False
        source = args.source
        if source.startswith(("https://", "http://")):
            data, source = download(source)
        else:
            with Path(source).open("rb") as file:
                data = file.read(MAX_BYTES + 1)
        result = json.dumps(jsonable_encoder(analyze(data, source, options)), indent=2, ensure_ascii=False)
        if args.output:
            args.output.write_text(result + "\n", encoding="utf-8")
        else:
            print(result)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Document analysis failed: {exc}\n")
    return 0


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
    if args.command in {"track-report", "audit-claims", "annual-report", "discover-exposures", "exposure-replay"}:
        return _document_command(args, remaining, parser)

    if args.command == "monitor":
        from src.api.research import get_watchlist_monitor
        from src.research.monitor import MonitorScanRequest

        response = get_watchlist_monitor().scan(
            MonitorScanRequest(
                tickers=args.tickers,
                as_of=args.as_of,
                minimum_materiality=args.minimum_materiality,
                max_workers=args.max_workers,
                dry_run=args.dry_run,
                request_interval_seconds=args.request_interval_seconds,
                max_retries=args.max_retries,
                source_stale_after_days=args.source_stale_after_days,
                year=args.year,
                quarter=args.quarter,
            )
        )
        print(json.dumps(response.model_dump(mode="json"), indent=2))
        return 1 if any(item.status == "failed" for item in response.results) else 0
    if args.command == "database":
        return _run_database_command(args, parser)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
