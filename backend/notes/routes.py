"""Authenticated personal notes API."""

from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from backend.auth import require_api_auth
from backend.notes import export as note_export
from backend.notes import store
from backend.notes.models import NoteCreate, NoteItem, NotesListResponse, NoteUpdate

router = APIRouter(prefix="/api/notes", tags=["notes"], dependencies=[Depends(require_api_auth)])

_DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.get("", response_model=NotesListResponse)
def list_notes(
    year: Annotated[str | None, Query(max_length=4)] = None,
    q: Annotated[str, Query(max_length=500)] = "",
    sort: Literal["recorded", "event"] = "recorded",
) -> dict:
    try:
        return store.list_notes(year=year, q=q, sort=sort)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


@router.get("/export")
def export_notes(
    format: Literal["md", "docx"] = "md",
    year: Annotated[str | None, Query(max_length=4)] = None,
    q: Annotated[str, Query(max_length=500)] = "",
) -> Response:
    try:
        data = store.list_notes(year=year, q=q, sort="event")
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None

    clean_year = year.strip() if year else ""
    heading = f"{clean_year} 年随手记" if clean_year else "全部随手记"
    ascii_name = f"notes-{clean_year or 'all'}.{format}"
    utf8_name = quote(f"{heading}.{format}")
    headers = {
        "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"
    }

    if format == "docx":
        return Response(
            content=note_export.render_docx(data["items"], heading),
            media_type=_DOCX_MEDIA_TYPE,
            headers=headers,
        )
    return Response(
        content=note_export.render_markdown(data["items"], heading),
        media_type="text/markdown; charset=utf-8",
        headers=headers,
    )


@router.post("", response_model=NoteItem, status_code=status.HTTP_201_CREATED)
def create_note(body: NoteCreate) -> dict:
    try:
        return store.create_note(body)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


@router.patch("/{note_id}", response_model=NoteItem)
def update_note(note_id: int, body: NoteUpdate) -> dict:
    try:
        return store.update_note(note_id, body)
    except store.NoteNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(note_id: int) -> None:
    try:
        store.delete_note(note_id)
    except store.NoteNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
