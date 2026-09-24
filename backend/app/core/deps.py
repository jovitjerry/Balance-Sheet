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
    return request.app.state.ocr

def get_embeddings(request: Request) -> EmbeddingProvider:
    return request.app.state.embeddings

def get_llm(request: Request) -> LlmProvider:
    return request.app.state.llm
__all__ = ['get_db', 'get_embeddings', 'get_llm', 'get_ocr', 'get_settings_dep', 'get_storage']
