from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

from app.core.logging import setup_logging
from app.services.factcheck_tasks import start_factcheck_worker


def _load_environment() -> None:
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env")


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core.config import get_settings

    start_factcheck_worker(get_settings())
    yield


def create_app() -> FastAPI:
    _load_environment()
    setup_logging()

    app = FastAPI(title="FactCheck Multi-Agent", version="0.1.0", lifespan=lifespan)

    from app.routes import router

    app.include_router(router)
    return app


app = create_app()
