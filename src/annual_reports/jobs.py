"""Small single-host job ledger for the interactive annual-report launcher."""

import json
import os
import re
from uuid import uuid4

from .library import store


def folder():
    return store() / "jobs"


def write(job):
    folder().mkdir(parents=True, exist_ok=True)
    path = folder() / (job["id"] + ".json")
    temp = path.with_suffix("." + uuid4().hex)
    temp.write_text(json.dumps(job), encoding="utf-8")
    temp.replace(path)


def create():
    job = {"id": "job-" + uuid4().hex, "status": "queued", "owner": os.getpid()}
    write(job)
    return job


def get(job_id):
    if not re.fullmatch(r"job-[0-9a-f]{32}", job_id):
        raise KeyError(job_id)
    try:
        job = json.loads((folder() / (job_id + ".json")).read_text())
    except FileNotFoundError as exc:
        raise KeyError(job_id) from exc
    if job["status"] in ("queued", "running"):
        try:
            os.kill(job["owner"], 0)
        except ProcessLookupError:
            job = {**job, "status": "failed", "detail": "The analysis service restarted. Submit the report again."}
    return {k: v for k, v in job.items() if k != "owner"}
