"""FastAPI application, service control, middleware, and frontend hosting."""

import hmac
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.auth import router as auth_router
from backend.capture.routes import router as capture_router
from backend.db import init_db
from backend.diet.routes import router as diet_router
from backend.ledger.routes import router as ledger_router
from backend.settings.routes import router as settings_router
from backend.settings.store import initialize_settings
from backend.todos.routes import router as todos_router

runtime_router = APIRouter(prefix="/api/internal/service", include_in_schema=False)


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


@runtime_router.get("/identity")
def identity(
    request: Request,
    x_tracker_control: Annotated[str | None, Header()] = None,
) -> dict:
    runtime = _controller(request, x_tracker_control)
    return {"pid": os.getpid(), "instance": runtime["instance"]}


@runtime_router.post("/shutdown")
def shutdown(
    request: Request,
    x_tracker_control: Annotated[str | None, Header()] = None,
) -> dict:
    runtime = _controller(request, x_tracker_control)
    runtime["server"].should_exit = True
    return {"ok": True}


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_settings()
    init_db()
    yield


def create_app() -> FastAPI:
    application = FastAPI(title="拾记 API", lifespan=lifespan)

    @application.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        # Pydantic's input/context may contain submitted keys or passwords.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()
                ]
            },
        )

    @application.middleware("http")
    async def same_origin_writes(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            expected = str(request.base_url).rstrip("/")
            if request.headers.get("sec-fetch-site") == "cross-site" or (
                origin is not None and origin != expected
            ):
                return JSONResponse(status_code=403, content={"detail": "不允许跨站写入"})
        return await call_next(request)

    application.include_router(auth_router)
    application.include_router(settings_router)
    application.include_router(todos_router)
    application.include_router(diet_router)
    application.include_router(ledger_router)
    application.include_router(capture_router)
    application.include_router(runtime_router)

    @application.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/health", include_in_schema=False)
    async def service_health(request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "schema_version": 1,
                "ok": True,
                "service": "tracker",
                "pid": os.getpid(),
                "port": request.scope["server"][1],
                "detail": "运行中",
            },
            media_type="application/json; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )

    frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    index_file = frontend_dist / "index.html"
    favicon_file = frontend_dist / "favicon.svg"
    assets = frontend_dist / "assets"
    if index_file.is_file() and assets.is_dir():
        application.mount("/assets", StaticFiles(directory=assets), name="assets")

        @application.get("/favicon.svg", include_in_schema=False)
        def favicon() -> FileResponse:
            return FileResponse(favicon_file, media_type="image/svg+xml")

        @application.get("/{frontend_path:path}", include_in_schema=False)
        def frontend(frontend_path: str) -> FileResponse:
            if frontend_path.startswith("api/"):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
            return FileResponse(index_file)

    return application


app = create_app()
