"""Read-only issuer workspace over annual filings, workflow briefs and the research journal."""

import asyncio
from datetime import date

from fastapi import APIRouter, HTTPException

from src.annual_reports import library
from src.annual_reports.continuity import resolve_record, workspace
from src.api.research import get_research_journal_store
from src.api.workflows import get_run_store

router = APIRouter(prefix="/research/companies")


@router.get("/{company_id}/workspace")
async def company_workspace(company_id: str, as_of: date | None = None):
    cutoff = (as_of or date.today()).isoformat()
    entries = await asyncio.to_thread(library.entries)
    try:
        result = await asyncio.to_thread(workspace, company_id, cutoff, entries)
    except KeyError as exc:
        raise HTTPException(404, "No verified issuer filing at this cutoff") from exc
    tickers = sorted(
        {
            v
            for f in result["filings"]
            for listing in f["issuer"]["listings"]
            for v in (listing["symbol"], listing["qualified"])
            if v
        }
    )
    runs, groups = await asyncio.gather(
        get_run_store().for_tickers(tickers),
        asyncio.to_thread(lambda: [t for sym in tickers for t in get_research_journal_store().list_theses(ticker=sym)]),
    )
    for s in runs:
        if (
            not s.report
            or s.request.demo_mode
            or (
                s.company
                and (
                    s.company.ticker != s.request.ticker
                    or s.company.source == "fixture"
                    or s.company.company_name.casefold() not in {f["company"].casefold() for f in result["filings"]}
                )
            )
        ):
            continue
        timestamps = [e.completed_at for e in s.trace if e.completed_at]
        if not timestamps:
            continue
        stamp = max(timestamps).date().isoformat()
        if (
            stamp <= cutoff
            and resolve_record(entries, s.request.ticker, stamp, s.request.company_id, as_of=cutoff) == company_id
        ):
            result["briefs"].append(
                {
                    "id": s.run_id,
                    "ticker": s.request.ticker,
                    "title": s.report.title,
                    "summary": s.report.executive_summary,
                    "status": s.status,
                    "date": stamp,
                }
            )
    for t in groups:
        stamp = t.updated_at.date().isoformat()
        if (
            stamp <= cutoff
            and resolve_record(entries, t.ticker, t.created_at.date().isoformat(), t.company_id, as_of=cutoff)
            == company_id
        ):
            result["journal"].append(
                {
                    "id": t.thesis_id,
                    "ticker": t.ticker,
                    "title": t.statement,
                    "status": t.status,
                    "date": stamp,
                    "conditions": t.disconfirming_conditions,
                }
            )
    return result
