"""FastAPI dependency providers.

The Mongo client and the file store are built once in the lifespan handler and
held on ``app.state``; these functions hand them to routes. Nothing here
constructs a client at import time - doing so binds it to the wrong event loop
and breaks under pytest.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings
from app.core.llm.base import LlmProvider
from app.core.llm.embeddings import EmbeddingProvider
from app.core.storage import FileStorage
from app.modules.ingestion.ocr import OcrEngine


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> AsyncDatabase[dict[str, Any]]:
    return request.app.state.db


def get_storage(request: Request) -> FileStorage:
    return request.app.state.storage


def get_ocr(request: Request) -> OcrEngine:
    """The OCR engine. Built once at startup, whether or not it can run.

    Availability is not checked here: a document with a usable text layer never
    needs OCR, and refusing every upload because Tesseract is missing would be
    wrong. The check happens at the point a scanned page is actually met.
    """
    return request.app.state.ocr


def get_embeddings(request: Request) -> EmbeddingProvider:
    """The embedding provider. Built once at startup, running or not.

    Separate from :func:`get_llm` because they are separate models: a
    deployment can have the chat model pulled and the embedding model missing,
    and the failure should name whichever one is actually absent.
    """
    return request.app.state.embeddings


def get_llm(request: Request) -> LlmProvider:
    """The local model provider. Built once at startup, running or not.

    Availability is not checked here, for the same reason it is not checked in
    :func:`get_ocr`: a document whose labels all match the canonical spellings
    never needs a model, and refusing every upload because Ollama is down would
    be wrong. The check happens where a label actually has to be interpreted.
    """
    return request.app.state.llm


__all__ = [
    "get_db",
    "get_embeddings",
    "get_llm",
    "get_ocr",
    "get_settings_dep",
    "get_storage",
]
