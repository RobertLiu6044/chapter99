"""
Part 1 — fetch the three HTSUS sources and land raw payloads under data/.

Release first, then the three downloads in parallel, then one metadata file
with provenance for the whole run.
"""

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from hatchet_sdk import Context
from pydantic import BaseModel

from echo import hatchet

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

RELEASE_URL = "https://hts.usitc.gov/reststop/currentRelease"

CHAPTER_99_URL = (
    "https://hts.usitc.gov/reststop/exportList"
    "?from=9900&to=9999&format=JSON&styles=false"
)
CHAPTERS_1_97_URL = (
    "https://hts.usitc.gov/reststop/exportList"
    "?from=0100&to=9799&format=JSON&styles=false"
)
NOTES_PDF_URL = (
    "https://hts.usitc.gov/reststop/file"
    "?release=currentRelease&filename=Chapter%2099"
)


class ScrapeInput(BaseModel):
    pass


class ReleaseOutput(BaseModel):
    name: str
    title: str
    description: str = ""


class FileOutput(BaseModel):
    filename: str
    url: str
    path: str
    bytes: int
    fetched_at: str


class MetadataOutput(BaseModel):
    path: str


scrape_workflow = hatchet.workflow(
    name="Scrape",
    input_validator=ScrapeInput,
)


def _download(ctx: Context, url: str, filename: str) -> FileOutput:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / filename
    ctx.log(f"fetching {filename}")

    with httpx.Client(timeout=120.0, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        payload = response.content

    # Write to a temp file and rename so a failure never leaves a truncated
    # payload, and a re-run simply replaces what was there.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, path)

    ctx.log(f"wrote {filename} ({len(payload)} bytes)")
    return FileOutput(
        filename=filename,
        url=url,
        path=str(path),
        bytes=len(payload),
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )


@scrape_workflow.task(
    execution_timeout=timedelta(minutes=2),
    retries=3,
    backoff_factor=2,
    backoff_max_seconds=30,
)
def release(input: ScrapeInput, ctx: Context) -> ReleaseOutput:
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(RELEASE_URL)
        response.raise_for_status()
        body = response.json()

    ctx.log(f"release: {body.get('title')}")
    return ReleaseOutput(
        name=body.get("name", ""),
        title=body.get("title", ""),
        description=body.get("description", ""),
    )


@scrape_workflow.task(
    parents=[release],
    execution_timeout=timedelta(minutes=10),
    retries=3,
    backoff_factor=2,
    backoff_max_seconds=60,
)
def chapter_99(input: ScrapeInput, ctx: Context) -> FileOutput:
    return _download(ctx, CHAPTER_99_URL, "chapter99.json")


@scrape_workflow.task(
    parents=[release],
    execution_timeout=timedelta(minutes=10),
    retries=3,
    backoff_factor=2,
    backoff_max_seconds=60,
)
def chapters_1_97(input: ScrapeInput, ctx: Context) -> FileOutput:
    return _download(ctx, CHAPTERS_1_97_URL, "chapters_1_97.json")


@scrape_workflow.task(
    parents=[release],
    execution_timeout=timedelta(minutes=10),
    retries=3,
    backoff_factor=2,
    backoff_max_seconds=60,
)
def notes_pdf(input: ScrapeInput, ctx: Context) -> FileOutput:
    return _download(ctx, NOTES_PDF_URL, "chapter99_notes.pdf")


@scrape_workflow.task(
    parents=[chapter_99, chapters_1_97, notes_pdf],
    execution_timeout=timedelta(minutes=1),
    retries=3,
)
def metadata(input: ScrapeInput, ctx: Context) -> MetadataOutput:
    """One provenance file for the whole run, written only after every fetch succeeded."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rel = ctx.task_output(release)
    sources = [
        ctx.task_output(chapter_99),
        ctx.task_output(chapters_1_97),
        ctx.task_output(notes_pdf),
    ]

    path = DATA_DIR / "provenance.json"
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "release": {
            "name": rel.name,
            "title": rel.title,
            "description": rel.description,
            "url": RELEASE_URL,
        },
        "sources": [
            {
                "filename": s.filename,
                "url": s.url,
                "path": s.path,
                "bytes": s.bytes,
                "fetched_at": s.fetched_at,
            }
            for s in sources
        ],
    }
    path.write_text(json.dumps(payload, indent=2))
    ctx.log(f"wrote {path}")
    return MetadataOutput(path=str(path))
