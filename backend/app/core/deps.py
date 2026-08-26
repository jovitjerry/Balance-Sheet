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


__all__ = ["get_db", "get_ocr", "get_settings_dep", "get_storage"]
