from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes.analysis import router as analysis_router
from api.routes.auth import router as auth_router
from api.routes.configuration import router as configuration_router
from api.routes.cross_period import router as cross_period_router
from api.routes.entries import router as entries_router
from api.routes.home import router as home_router
from api.routes.meals import router as meals_router
from api.routes.pending import router as pending_router
from api.routes.transactions import router as transactions_router
from core.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    application = FastAPI(title="personal-tracker API", lifespan=lifespan)
    application.include_router(analysis_router)
    application.include_router(auth_router)
    application.include_router(configuration_router)
    application.include_router(cross_period_router)
    application.include_router(entries_router)
    application.include_router(home_router)
    application.include_router(meals_router)
    application.include_router(pending_router)
    application.include_router(transactions_router)

    @application.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
    index_file = frontend_dist / "index.html"
    assets = frontend_dist / "assets"
    if index_file.is_file() and assets.is_dir():
        application.mount("/assets", StaticFiles(directory=assets), name="assets")

        @application.get("/{frontend_path:path}", include_in_schema=False)
        def frontend(frontend_path: str) -> FileResponse:
            if frontend_path.startswith("api/"):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
            return FileResponse(index_file)

    return application


app = create_app()
