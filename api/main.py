from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.routes.analysis import router as analysis_router
from api.routes.auth import router as auth_router
from api.routes.configuration import router as configuration_router
from api.routes.cross_period import router as cross_period_router
from api.routes.entries import router as entries_router
from api.routes.home import router as home_router
from api.routes.meals import router as meals_router
from api.routes.pending import router as pending_router
from api.routes.runtime import router as runtime_router
from api.routes.settings import router as settings_router
from api.routes.todos import router as todos_router
from api.routes.transactions import router as transactions_router
from core.db import init_db
from core.settings_store import initialize_settings


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
                    {"loc": e["loc"], "msg": e["msg"], "type": e["type"]}
                    for e in exc.errors()
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
                return JSONResponse(
                    status_code=403, content={"detail": "不允许跨站写入"}
                )
        return await call_next(request)

    application.include_router(analysis_router)
    application.include_router(auth_router)
    application.include_router(configuration_router)
    application.include_router(cross_period_router)
    application.include_router(entries_router)
    application.include_router(home_router)
    application.include_router(meals_router)
    application.include_router(pending_router)
    application.include_router(runtime_router)
    application.include_router(settings_router)
    application.include_router(transactions_router)
    application.include_router(todos_router)

    @application.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

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
