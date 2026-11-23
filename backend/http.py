"""Shared HTTP request requirements for idempotent writes."""

from typing import Annotated

from fastapi import Header

IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8)]
