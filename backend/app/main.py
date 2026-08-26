"""FastAPI application entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.db import create_client, ensure_indexes, get_database, ping
from app.core.errors import register_exception_handlers
from app.core.pipeline import STAGES
from app.core.storage import build_storage
from app.modules.ingestion.ocr import build_ocr_engine
from app.modules.ingestion.router import router as ingestion_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build and tear down the Mongo client and file store.

    The client is created here rather than at import time: an import-time
    client binds to the wrong event loop and breaks under pytest.
    """
    settings = get_settings()
    client = create_client(settings)
    app.state.settings = settings
    app.state.client = client
    app.state.db = get_database(client, settings)
    app.state.storage = build_storage(settings.storage_backend, settings.storage_dir)
    app.state.ocr = build_ocr_engine(settings.ocr_language)
    if settings.ocr_enabled and not app.state.ocr.available():
        # A warning, not a failure. Documents with a usable text layer are
        # unaffected; only a scanned page will be refused, and it is refused at
        # the point it is met rather than by taking the API down at boot.
        logger.warning(
            "Tesseract is not available - scanned documents will be refused. "
            "The pytesseract pip package alone is not enough; install the "
            "Tesseract system binary."
        )

    try:
        await ping(client)
        await ensure_indexes(app.state.db)
        logger.info("Connected to MongoDB database %r", settings.mongodb_db)
    except Exception:
        # Do not take the API down because Atlas is unreachable - /health is
        # what reports connectivity, and it must stay callable to do so.
        logger.exception("MongoDB unavailable at startup")

    try:
        yield
    finally:
        await client.close()


app = FastAPI(
    title="BalanceSheet API",
    description=(
        "A Multi-Agent AI Framework for Automated Balance Sheet Review. "
        "Scope: Balance Sheet only, single reporting period."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

api = APIRouter(prefix=API_PREFIX)


@api.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    """Report API and database status.

    The database check is a real ``ping`` round-trip against Atlas under Stable
    API v1, not a cached flag.
    """
    try:
        await ping(app.state.client)
        database = "connected"
    except Exception as exc:  # noqa: BLE001 - the status IS the payload here
        logger.warning("Health check could not reach MongoDB: %s", exc)
        database = "unavailable"
    return {"status": "ok", "database": database}


@api.get("/pipeline", tags=["meta"])
async def pipeline_status() -> dict[str, object]:
    """Report which modules are actually implemented.

    Exists so "not built yet" is visible from the outside rather than being
    something a caller has to infer from a failure.
    """
    return {
        "stages": [
            {
                "stage": info.stage.value,
                "module": info.module,
                "description": info.description,
                "state": info.state.value,
            }
            for info in STAGES
        ]
    }


api.include_router(ingestion_router)
app.include_router(api)


__all__ = ["app"]
