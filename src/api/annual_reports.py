"""Document workflow accepts a public URL or bounded file bytes, never a server path."""

import asyncio
import json
from urllib.parse import unquote

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from pydantic import HttpUrl, ValidationError
from pydantic_ai.exceptions import AgentRunError

from src.annual_reports import jobs, library
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


def analyze_and_save(data, source, options):
    result = jsonable_encoder(analyze(data, source, options))
    result["report_id"] = library.persist(result, data)
    return result


@router.get("/library")
def report_library():
    return library.entries()


@router.get("/library/{run_id}")
def saved_report(run_id: str, cutoff: str | None = None):
    try:
        return library.bundle(run_id, cutoff)
    except KeyError as exc:
        raise HTTPException(404, "Report or snapshot not available") from exc


@router.get("/library/{run_id}/original")
def report_original(run_id: str):
    try:
        pdf = library.directory(run_id) / "original.pdf"
    except KeyError as exc:
        raise HTTPException(404, "Original PDF unavailable") from exc
    if not pdf.is_file():
        raise HTTPException(404, "Original PDF unavailable")
    return FileResponse(
        pdf,
        media_type="application/pdf",
        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"},
    )


def online_operation(report):
    def run():
        data, source = download(str(report.url))
        return analyze_and_save(data, source, report)

    return run


@router.post("/url")
async def analyze_online(report: OnlineReport):
    return await _run(online_operation(report))


async def upload_operation(request, filename, options):
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
    return lambda: analyze_and_save(bytes(data), display_name, config)


@router.post("/upload")
async def analyze_upload(request: Request, filename: str = "report.pdf", options: str = "{}"):
    return await _run(await upload_operation(request, filename, options))


# Bound interactive jobs per API process; do not enqueue unbounded PDF buffers.
_slots = asyncio.Semaphore(1)


async def launch(background, operation):
    if _slots.locked():
        raise HTTPException(429, "An annual analysis is in progress. Try again when it finishes.")
    await _slots.acquire()
    try:
        job = jobs.create()
    except BaseException:
        _slots.release()
        raise

    async def execute():
        try:
            jobs.write({**job, "status": "running"})
            report = await _run(operation)
            jobs.write({**job, "status": "completed", "report_id": report["report_id"]})
        except Exception as error:
            detail = (
                error.detail if isinstance(error, HTTPException) else "Analysis failed. Check the service and retry."
            )
            jobs.write({**job, "status": "failed", "detail": str(detail)})
        finally:
            _slots.release()

    background.add_task(execute)
    return {"id": job["id"], "status": "queued"}


@router.post("/jobs/url", status_code=202)
async def launch_online(report: OnlineReport, background: BackgroundTasks):
    return await launch(background, online_operation(report))


@router.post("/jobs/upload", status_code=202)
async def launch_upload(
    request: Request, background: BackgroundTasks, filename: str = "report.pdf", options: str = "{}"
):
    return await launch(background, await upload_operation(request, filename, options))


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    try:
        return jobs.get(job_id)
    except KeyError as exc:
        raise HTTPException(404, "Analysis job not found") from exc
