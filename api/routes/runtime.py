"""Private loopback control used only by the project-owned service runner."""

import hmac
import os
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request

router = APIRouter(prefix="/api/internal/service", include_in_schema=False)


def _controller(request: Request, token: str | None) -> dict:
    runtime = getattr(request.app.state, "service_runtime", None)
    if (
        not runtime
        or not request.client
        or request.client.host not in {"127.0.0.1", "::1"}
        or not token
        or not hmac.compare_digest(token, runtime["token"])
    ):
        raise HTTPException(status_code=404)
    return runtime


@router.get("/identity")
def identity(
    request: Request,
    x_tracker_control: Annotated[str | None, Header()] = None,
) -> dict:
    runtime = _controller(request, x_tracker_control)
    return {"pid": os.getpid(), "instance": runtime["instance"]}


@router.post("/shutdown")
def shutdown(
    request: Request,
    x_tracker_control: Annotated[str | None, Header()] = None,
) -> dict:
    runtime = _controller(request, x_tracker_control)
    runtime["server"].should_exit = True
    return {"ok": True}
