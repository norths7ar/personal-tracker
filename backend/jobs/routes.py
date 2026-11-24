"""Authenticated job search API."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from starlette.concurrency import run_in_threadpool

from backend.auth import require_api_auth
from backend.jobs import docx, store, workflow
from backend.jobs.models import (
    AnalysisRequest,
    Context,
    DocxPreview,
    Intake,
    IntakeCreate,
    IntakeSave,
    JobDetail,
    JobStatus,
    JobSummary,
    JobUpdate,
    MatchLevel,
    Profile,
    ProfileWrite,
    QuestionRequest,
)
from backend.llm import LLMError

router = APIRouter(prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(require_api_auth)])

_DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@contextmanager
def _api_errors() -> Iterator[None]:
    try:
        yield
    except store.NotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except store.Conflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    except LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


@router.get("", response_model=list[JobSummary])
def list_jobs(
    q: Annotated[str, Query(max_length=500)] = "",
    status: JobStatus | None = None,
    platform: Annotated[str | None, Query(max_length=150)] = None,
    city: Annotated[str | None, Query(max_length=250)] = None,
    is_headhunter: bool | None = None,
    match_level: MatchLevel | None = None,
) -> list[JobSummary]:
    return store.list_jobs(
        q=q,
        status=status,
        platform=platform,
        city=city,
        is_headhunter=is_headhunter,
        match_level=match_level,
    )


@router.get("/profile", response_model=Profile)
def get_profile() -> Profile:
    return store.get_profile()


@router.put("/profile", response_model=Profile)
def save_profile(body: ProfileWrite) -> Profile:
    with _api_errors():
        return store.save_profile(body)


@router.post(
    "/profile/docx",
    response_model=DocxPreview,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {_DOCX_MEDIA_TYPE: {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def preview_docx(request: Request, filename: Annotated[str, Query()]) -> DocxPreview:
    with _api_errors():
        filename = docx.clean_filename(filename)
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > docx.MAX_DOCX_BYTES:
                raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Word 文件超过 8 MiB")
            data.extend(chunk)
        resume_text = await run_in_threadpool(docx.extract_text, bytes(data))
        return DocxPreview(resume_text=resume_text, source_filename=filename)


@router.get("/intakes", response_model=list[Intake])
def list_intakes() -> list[Intake]:
    return store.list_intakes()


@router.post("/intakes", response_model=Intake)
def create_intake(body: IntakeCreate) -> Intake:
    with _api_errors():
        intake_id, claim = store.create_intake(body)
        if claim:
            workflow.extract(claim)
        return store.get_intake(intake_id)


@router.get("/intakes/{intake_id}", response_model=Intake)
def get_intake(intake_id: int) -> Intake:
    with _api_errors():
        return store.get_intake(intake_id)


@router.delete("/intakes/{intake_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard_intake(intake_id: int) -> None:
    with _api_errors():
        store.discard_intake(intake_id)


@router.post("/intakes/{intake_id}/retry", response_model=Intake)
def retry_intake(intake_id: int) -> Intake:
    with _api_errors():
        if claim := store.retry_intake(intake_id):
            workflow.extract(claim)
        return store.get_intake(intake_id)


@router.post("/intakes/{intake_id}/save", response_model=JobDetail)
def save_intake(intake_id: int, body: IntakeSave) -> JobDetail:
    with _api_errors():
        job_id, claim = store.save_intake(intake_id, body)
        if claim:
            workflow.analyze(claim)
        return store.get_job(job_id)


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: int) -> JobDetail:
    with _api_errors():
        return store.get_job(job_id)


@router.patch("/{job_id}", response_model=JobDetail)
def update_job(job_id: int, body: JobUpdate) -> JobDetail:
    with _api_errors():
        return store.update_job(job_id, body)


@router.post("/{job_id}/analysis", response_model=JobDetail)
def analyze_job(job_id: int, body: AnalysisRequest) -> JobDetail:
    with _api_errors():
        if claim := store.start_analysis(job_id, str(body.request_id)):
            workflow.analyze(claim)
        return store.get_job(job_id)


@router.post("/{job_id}/questions", response_model=JobDetail)
def ask_question(job_id: int, body: QuestionRequest) -> JobDetail:
    with _api_errors():
        if claim := store.start_question(job_id, str(body.request_id), body.question):
            workflow.answer(claim)
        return store.get_job(job_id)


@router.get("/{job_id}/context", response_model=Context)
def copy_context(job_id: int) -> Context:
    with _api_errors():
        profile, job = store.context_input(job_id)
        return Context(text=workflow.copy_context(profile, job))
