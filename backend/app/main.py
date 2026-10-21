from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.core.config import get_settings
from app.db.client import connect_db, close_db
from app.db.indexes import create_indexes
from app.db.client import get_db
from app.api import auth, profile, jobs, settings, admin, pipeline

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    settings_cfg = get_settings()
    await connect_db()
    await create_indexes(get_db())
    logger.info("Sleepy Apply backend started", env=settings_cfg.environment)
    yield
    # Shutdown
    await close_db()
    logger.info("Sleepy Apply backend stopped")


def create_app() -> FastAPI:
    cfg = get_settings()
    app = FastAPI(
        title="Sleepy Apply API",
        version="0.1.0",
        docs_url="/docs" if not cfg.is_production else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    # CORS — allow frontend origins
    origins = list(dict.fromkeys([cfg.frontend_url, "http://localhost:3000", "http://localhost:3002"]))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(auth.router, prefix="/api")
    app.include_router(profile.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api")
    app.include_router(settings.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")
    app.include_router(pipeline.router, prefix="/api")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
