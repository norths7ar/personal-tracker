"""Small, Streamlit-independent helpers for the batch review lifecycle."""

from collections.abc import MutableMapping
from typing import Any
from uuid import uuid4

BATCH_STATUS_EMPTY = "empty"
BATCH_STATUS_REVIEW = "review"
BATCH_STATUS_SAVING = "saving"
BATCH_STATUS_ERROR = "error"

_VALID_STATUSES = {
    BATCH_STATUS_EMPTY,
    BATCH_STATUS_REVIEW,
    BATCH_STATUS_SAVING,
    BATCH_STATUS_ERROR,
}

_DEFAULTS: dict[str, Any] = {
    "batch_status": BATCH_STATUS_EMPTY,
    "batch_records": None,
    "batch_diagnostics": None,
    "batch_source_text": "",
    "batch_submission_id": None,
    "batch_error": None,
    "batch_retryable": False,
    "batch_editor_version": 0,
}


def _new_submission_id() -> str:
    return uuid4().hex


def ensure_batch_state(
    session_state: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Initialize batch keys and recover a batch interrupted while saving.

    Older sessions have records but no lifecycle status or submission id.  Such
    records are a review draft and receive an id so that a later save can be
    retried safely.  A saving status cannot be trusted after a rerun, so it is
    converted to a retryable error instead of leaving the UI stuck.
    """

    had_records = (
        "batch_records" in session_state
        and session_state.get("batch_records") is not None
    )
    previous_status = session_state.get("batch_status")

    for key, default in _DEFAULTS.items():
        if key not in session_state:
            session_state[key] = default

    if (
        session_state["batch_records"] is not None
        and not str(session_state.get("batch_submission_id") or "").strip()
    ):
        session_state["batch_submission_id"] = _new_submission_id()

    status = session_state.get("batch_status")
    if status == BATCH_STATUS_SAVING:
        session_state["batch_status"] = BATCH_STATUS_ERROR
        session_state["batch_error"] = "上次批次保存可能已中断，可重试。"
        session_state["batch_retryable"] = True
    elif status not in _VALID_STATUSES:
        session_state["batch_status"] = (
            BATCH_STATUS_REVIEW if had_records else BATCH_STATUS_EMPTY
        )
    elif previous_status is None and had_records:
        session_state["batch_status"] = BATCH_STATUS_REVIEW

    return session_state


def start_batch_review(
    session_state: MutableMapping[str, Any],
    source_text: str,
    records: Any,
    diagnostics: Any,
    submission_id: str | None = None,
) -> MutableMapping[str, Any]:
    """Replace the current draft with a newly parsed batch for review."""

    ensure_batch_state(session_state)
    session_state["batch_status"] = BATCH_STATUS_REVIEW
    session_state["batch_source_text"] = source_text
    session_state["batch_records"] = records
    session_state["batch_diagnostics"] = diagnostics
    normalized_submission_id = str(submission_id or "").strip()
    session_state["batch_submission_id"] = (
        normalized_submission_id or _new_submission_id()
    )
    session_state["batch_error"] = None
    session_state["batch_retryable"] = False
    session_state["batch_editor_version"] = (
        int(session_state.get("batch_editor_version") or 0) + 1
    )
    return session_state


def mark_batch_saving(
    session_state: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Mark a reviewed batch as being submitted."""

    ensure_batch_state(session_state)
    session_state["batch_status"] = BATCH_STATUS_SAVING
    session_state["batch_error"] = None
    session_state["batch_retryable"] = False
    return session_state


def mark_batch_error(
    session_state: MutableMapping[str, Any],
    error: Any,
    retryable: bool = True,
) -> MutableMapping[str, Any]:
    """Record a recoverable or terminal batch error while retaining the draft."""

    ensure_batch_state(session_state)
    session_state["batch_status"] = BATCH_STATUS_ERROR
    session_state["batch_error"] = str(error) if error is not None else "批次处理失败。"
    session_state["batch_retryable"] = retryable
    return session_state


def reset_batch_draft(
    session_state: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Discard the current draft and invalidate the editor widget generation."""

    ensure_batch_state(session_state)
    session_state["batch_records"] = None
    session_state["batch_diagnostics"] = None
    session_state["batch_source_text"] = ""
    session_state["batch_submission_id"] = None
    session_state["batch_error"] = None
    session_state["batch_retryable"] = False
    session_state["batch_status"] = BATCH_STATUS_EMPTY
    session_state["batch_editor_version"] = (
        int(session_state.get("batch_editor_version") or 0) + 1
    )
    return session_state
