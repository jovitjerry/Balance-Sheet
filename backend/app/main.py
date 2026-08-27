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
from app.core.llm.embeddings import build_embedding_provider
from app.core.llm.ollama import build_llm_provider
from app.core.pipeline import STAGES
from app.core.storage import build_storage
from app.modules.ingestion.ocr import build_ocr_engine
from app.modules.ingestion.router import router as ingestion_router
from app.modules.insights.router import router as insights_router

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
    app.state.llm = build_llm_provider(
        host=settings.ollama_host,
        model=settings.ollama_model,
        timeout_s=settings.ollama_timeout_s,
        num_ctx=settings.ollama_num_ctx,
    )
    # A separate model from the one above, on the same Ollama host. Built here
    # whether or not it is pulled, like every other optional capability.
    app.state.embeddings = build_embedding_provider(
        host=settings.ollama_host,
        model=settings.embedding_model,
        dimensions=settings.embedding_dim,
        timeout_s=settings.embedding_timeout_s,
    )
    if settings.ocr_enabled and not app.state.ocr.available():
        # A warning, not a failure. Documents with a usable text layer are
        # unaffected; only a scanned page will be refused, and it is refused at
        # the point it is met rather than by taking the API down at boot.
        logger.warning(
            "Tesseract is not available - scanned documents will be refused. "
            "The pytesseract pip package alone is not enough; install the "
            "Tesseract system binary."
        )

    if not app.state.llm.available():
        # A warning, not a failure, and for the same reason as OCR above. Every
        # figure Module 2 extracts is deterministic and unaffected; only the
        # terminology mapping needs the model, and the labels it cannot resolve
        # are marked needs_review rather than guessed at. LLM_REQUIRED turns
        # this into a refusal for CI, where a quietly un-normalized document
        # would be a false green.
        logger.warning(
            "Ollama is not reachable at %s - line-item labels will be recorded "
            "for review instead of normalized. Install Ollama and run "
            "'ollama pull %s'.",
            settings.ollama_host,
            settings.ollama_model,
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
    """Report which modules are implemented, and what triggers each.

    Exists so "not built yet" is visible from the outside rather than being
    something a caller has to infer from a failure. ``trigger`` distinguishes
    the stages an upload runs from Module 4, which is built but answers
    questions on request - a distinction ``state`` alone cannot make without
    misreporting one or the other.
    """
    return {
        "stages": [
            {
                "stage": info.stage.value,
                "module": info.module,
                "description": info.description,
                "state": info.state.value,
                "trigger": info.trigger,
            }
            for info in STAGES
        ]
    }


api.include_router(ingestion_router)
api.include_router(insights_router)
app.include_router(api)


__all__ = ["app"]
