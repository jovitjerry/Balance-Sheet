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
API_PREFIX = '/api/v1'

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    client = create_client(settings)
    app.state.settings = settings
    app.state.client = client
    app.state.db = get_database(client, settings)
    app.state.storage = build_storage(settings.storage_backend, settings.storage_dir)
    app.state.ocr = build_ocr_engine(settings.ocr_language)
    app.state.llm = build_llm_provider(host=settings.ollama_host, model=settings.ollama_model, timeout_s=settings.ollama_timeout_s, num_ctx=settings.ollama_num_ctx)
    app.state.embeddings = build_embedding_provider(host=settings.ollama_host, model=settings.embedding_model, dimensions=settings.embedding_dim, timeout_s=settings.embedding_timeout_s)
    if settings.ocr_enabled and (not app.state.ocr.available()):
        logger.warning('Tesseract is not available - scanned documents will be refused. The pytesseract pip package alone is not enough; install the Tesseract system binary.')
    if not app.state.llm.available():
        logger.warning("Ollama is not reachable at %s - line-item labels will be recorded for review instead of normalized. Install Ollama and run 'ollama pull %s'.", settings.ollama_host, settings.ollama_model)
    try:
        await ping(client)
        await ensure_indexes(app.state.db)
        logger.info('Connected to MongoDB database %r', settings.mongodb_db)
    except Exception:
        logger.exception('MongoDB unavailable at startup')
    try:
        yield
    finally:
        await client.close()
app = FastAPI(title='BalanceSheet API', description='A Multi-Agent AI Framework for Automated Balance Sheet Review. Scope: Balance Sheet only, single reporting period.', version='0.1.0', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().allowed_origins, allow_credentials=True, allow_methods=['*'], allow_headers=['*'])
register_exception_handlers(app)
api = APIRouter(prefix=API_PREFIX)

@api.get('/health', tags=['meta'])
async def health() -> dict[str, str]:
    try:
        await ping(app.state.client)
        database = 'connected'
    except Exception as exc:
        logger.warning('Health check could not reach MongoDB: %s', exc)
        database = 'unavailable'
    return {'status': 'ok', 'database': database}

@api.get('/pipeline', tags=['meta'])
async def pipeline_status() -> dict[str, object]:
    return {'stages': [{'stage': info.stage.value, 'module': info.module, 'description': info.description, 'state': info.state.value, 'trigger': info.trigger} for info in STAGES]}
api.include_router(ingestion_router)
api.include_router(insights_router)
app.include_router(api)
__all__ = ['app']
