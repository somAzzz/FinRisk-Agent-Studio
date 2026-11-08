"""Document workflow accepts a public URL or bounded file bytes, never a server path."""

import asyncio
import json
from urllib.parse import unquote

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import HttpUrl, ValidationError
from pydantic_ai.exceptions import AgentRunError

from src.annual_reports.analysis import Options, analyze
from src.annual_reports.documents import MAX_BYTES, DocumentError, download

router = APIRouter(prefix="/workflows/annual-report")


class OnlineReport(Options):
    url: HttpUrl


async def _run(operation):
    try:
        return await asyncio.to_thread(operation)
    except (DocumentError, ValidationError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except (OSError, httpx.HTTPError, AgentRunError) as exc:
        raise HTTPException(502, f"Document source or inference service failed ({type(exc).__name__})") from exc


@router.post("/url")
async def analyze_online(report: OnlineReport):
    def run():
        data, source = download(str(report.url))
        return analyze(data, source, report)

    return await _run(run)


@router.post("/upload")
async def analyze_upload(request: Request, filename: str = "report.pdf", options: str = "{}"):
    try:
        config = Options.model_validate(json.loads(options))
    except ValueError as exc:
        raise HTTPException(422, "Invalid analysis options") from exc
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_BYTES:
            raise HTTPException(413, "Document exceeds 48 MiB")
    display_name = unquote(filename).replace("\\", "/").split("/")[-1][:255]
    return await _run(lambda: analyze(bytes(data), display_name, config))
