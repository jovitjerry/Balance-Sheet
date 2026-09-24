from __future__ import annotations
import logging
from typing import Any
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase
from app.core.db import BALANCE_SHEETS, DOCUMENT_CHUNKS, ensure_vector_index
from app.core.llm.embeddings import EmbeddingProvider
from app.core.preliminary import load_preliminary
from app.core.schemas import BalanceSheetDocument, ChunkIndexState, DocumentChunk, utcnow
from app.core.storage import FileStorage
from app.modules.insights.chunking import CHUNK_SPEC_VERSION, chunks_for
logger = logging.getLogger(__name__)

async def ensure_indexed(db: AsyncDatabase[dict[str, Any]], document: BalanceSheetDocument, *, embeddings: EmbeddingProvider, storage: FileStorage | None=None) -> ChunkIndexState | None:
    current = document.chunk_index
    if current is not None and (not current.is_stale(embedding_model=embeddings.model, chunk_spec_version=CHUNK_SPEC_VERSION)):
        return current
    if current is not None:
        logger.info('Re-indexing %s: built with %s/%s, now %s/%s', document.id, current.embedding_model, current.chunk_spec_version, embeddings.model, CHUNK_SPEC_VERSION)
    return await index_document(db, document, embeddings=embeddings, storage=storage)

async def index_document(db: AsyncDatabase[dict[str, Any]], document: BalanceSheetDocument, *, embeddings: EmbeddingProvider, storage: FileStorage | None=None) -> ChunkIndexState | None:
    if document.id is None:
        raise ValueError('Cannot index a document that has not been stored.')
    hydrated = document
    if document.preliminary is None and document.preliminary_ref is not None:
        preliminary = await load_preliminary(document, storage=storage)
        hydrated = document.model_copy(update={'preliminary': preliminary})
    chunks = chunks_for(hydrated)
    if not chunks:
        logger.info('Nothing to index for %s: no extractable page text', document.id)
        return None
    vectors = await embeddings.embed([chunk.text for chunk in chunks])
    stamped = [chunk.model_copy(update={'embedding': vector, 'embedding_model': embeddings.model, 'embedding_dim': len(vector)}) for chunk, vector in zip(chunks, vectors)]
    await delete_chunks(db, document.id)
    await db[DOCUMENT_CHUNKS].insert_many([_to_mongo(chunk) for chunk in stamped])
    await _ensure_vector_index_once(db, dimensions=embeddings.dimensions)
    state = ChunkIndexState(indexed_at=utcnow(), embedding_model=embeddings.model, embedding_dim=embeddings.dimensions, chunk_spec_version=CHUNK_SPEC_VERSION, chunk_count=len(stamped))
    await _record_state(db, document.id, state)
    document.chunk_index = state
    logger.info('Indexed %s chunk(s) for %s', len(stamped), document.id)
    return state
_vector_index_attempted = False

async def _ensure_vector_index_once(db: AsyncDatabase[dict[str, Any]], *, dimensions: int) -> None:
    global _vector_index_attempted
    if _vector_index_attempted:
        return
    _vector_index_attempted = True
    await ensure_vector_index(db, dimensions=dimensions)

async def delete_chunks(db: AsyncDatabase[dict[str, Any]], document_id: str) -> int:
    result = await db[DOCUMENT_CHUNKS].delete_many({'document_id': document_id})
    return int(result.deleted_count)

def _to_mongo(chunk: DocumentChunk) -> dict[str, Any]:
    data = chunk.model_dump(by_alias=True, exclude_none=True, mode='python')
    data.pop('_id', None)
    return data

async def _record_state(db: AsyncDatabase[dict[str, Any]], document_id: str, state: ChunkIndexState) -> None:
    await db[BALANCE_SHEETS].update_one({'_id': ObjectId(document_id)}, {'$set': {'chunk_index': state.model_dump(mode='python'), 'updated_at': utcnow()}})
__all__ = ['delete_chunks', 'ensure_indexed', 'index_document']
