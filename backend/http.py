"""Shared HTTP request types."""

from datetime import date
from typing import Annotated

from fastapi import Header
from pydantic import BeforeValidator

IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8)]


def _iso_date(value: object) -> date:
    if type(value) is date:
        return value
    if isinstance(value, str):
        parsed = date.fromisoformat(value)
        if parsed.isoformat() == value:
            return parsed
    raise ValueError("日期必须为 YYYY-MM-DD")


IsoDate = Annotated[date, BeforeValidator(_iso_date)]
