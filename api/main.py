from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routes.analysis import router as analysis_router
from api.routes.auth import router as auth_router
from api.routes.configuration import router as configuration_router
from api.routes.cross_period import router as cross_period_router
from api.routes.entries import router as entries_router
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
    application.include_router(meals_router)
    application.include_router(pending_router)
    application.include_router(transactions_router)

    @application.get("/api/health", tags=["system"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
