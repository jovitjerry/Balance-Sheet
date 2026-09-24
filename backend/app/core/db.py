from __future__ import annotations
import logging
from typing import Any
from bson.codec_options import CodecOptions
from bson.decimal128 import Decimal128
from pymongo import ASCENDING, DESCENDING, AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.server_api import ServerApi
from app.core.config import Settings
logger = logging.getLogger(__name__)
BALANCE_SHEETS = 'balance_sheets'
DOCUMENT_CHUNKS = 'document_chunks'
QA_HISTORY = 'qa_history'
VECTOR_INDEX = 'chunks_vector_index'
CODEC_OPTIONS: CodecOptions[dict[str, Any]] = CodecOptions(tz_aware=True)

def create_client(settings: Settings) -> AsyncMongoClient[dict[str, Any]]:
    return AsyncMongoClient(settings.mongodb_uri.get_secret_value(), server_api=ServerApi('1', strict=False, deprecation_errors=True), serverSelectionTimeoutMS=settings.mongodb_timeout_ms, tz_aware=True)

def get_database(client: AsyncMongoClient[dict[str, Any]], settings: Settings) -> AsyncDatabase[dict[str, Any]]:
    return client.get_database(settings.mongodb_db, codec_options=CODEC_OPTIONS)

async def ping(client: AsyncMongoClient[dict[str, Any]]) -> None:
    await client.admin.command('ping')

async def ensure_indexes(db: AsyncDatabase[dict[str, Any]]) -> None:
    collection = db[BALANCE_SHEETS]
    await collection.create_index([('source.sha256', ASCENDING)], name='source_sha256')
    await collection.create_index([('status', ASCENDING)], name='status')
    await collection.create_index([('created_at', DESCENDING)], name='created_at_desc')
    chunks = db[DOCUMENT_CHUNKS]
    await chunks.create_index([('document_id', ASCENDING)], name='chunk_document_id')
    await db[QA_HISTORY].create_index([('document_id', ASCENDING), ('created_at', DESCENDING)], name='qa_document_id')
    logger.info('Indexes ensured on %s', db.name)

def vector_index_definition(*, dimensions: int) -> dict[str, Any]:
    return {'fields': [{'type': 'vector', 'path': 'embedding', 'numDimensions': dimensions, 'similarity': 'cosine'}, {'type': 'filter', 'path': 'document_id'}, {'type': 'filter', 'path': 'page_role'}]}

async def ensure_vector_index(db: AsyncDatabase[dict[str, Any]], *, dimensions: int) -> bool:
    collection = db[DOCUMENT_CHUNKS]
    try:
        existing = [index async for index in await collection.list_search_indexes()]
        if any((index.get('name') == VECTOR_INDEX for index in existing)):
            return True
        await collection.create_search_index({'name': VECTOR_INDEX, 'type': 'vectorSearch', 'definition': vector_index_definition(dimensions=dimensions)})
        logger.info('Requested vector index %r on %s; Atlas builds it asynchronously, so the first searches may use exact scoring instead', VECTOR_INDEX, DOCUMENT_CHUNKS)
        return False
    except Exception as exc:
        logger.warning('Could not ensure the vector index: %s', exc)
        return False
__all__ = ['BALANCE_SHEETS', 'DOCUMENT_CHUNKS', 'QA_HISTORY', 'VECTOR_INDEX', 'Decimal128', 'create_client', 'ensure_indexes', 'ensure_vector_index', 'get_database', 'ping', 'vector_index_definition']
