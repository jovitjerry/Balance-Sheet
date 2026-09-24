from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any
from pymongo.asynchronous.database import AsyncDatabase
from app.core.db import DOCUMENT_CHUNKS, VECTOR_INDEX
from app.core.llm.embeddings import cosine
from app.core.schemas import DocumentChunk, Evidence, EvidenceKind, PageRole
logger = logging.getLogger(__name__)
TOP_K = 5
NUM_CANDIDATES = 100
SIMILARITY_FLOOR = 0.55

@dataclass(frozen=True)
class ScoredChunk:
    chunk: DocumentChunk
    score: float

def rank(query: list[float], chunks: list[DocumentChunk], *, top_k: int=TOP_K, floor: float=SIMILARITY_FLOOR) -> list[ScoredChunk]:
    scored = [ScoredChunk(chunk=chunk, score=cosine(query, chunk.embedding)) for chunk in chunks]
    keep = [entry for entry in scored if entry.score >= floor]
    keep.sort(key=lambda entry: (-entry.score, entry.chunk.page_index, entry.chunk.chunk_index))
    return in_reading_order(keep[:top_k])

def in_reading_order(scored: list[ScoredChunk]) -> list[ScoredChunk]:
    return sorted(scored, key=lambda entry: (entry.chunk.page_index, entry.chunk.chunk_index))

async def search(db: AsyncDatabase[dict[str, Any]], *, document_id: str, query: list[float], top_k: int=TOP_K, page_role: PageRole | None=None, floor: float=SIMILARITY_FLOOR) -> list[ScoredChunk]:
    conditions: list[dict[str, Any]] = [{'document_id': {'$eq': document_id}}]
    if page_role is not None:
        conditions.append({'page_role': {'$eq': page_role.value}})
    pipeline: list[dict[str, Any]] = [{'$vectorSearch': {'index': VECTOR_INDEX, 'path': 'embedding', 'queryVector': query, 'numCandidates': NUM_CANDIDATES, 'limit': top_k, 'filter': conditions[0] if len(conditions) == 1 else {'$and': conditions}}}, {'$set': {'score': {'$meta': 'vectorSearchScore'}}}, {'$project': {'embedding': 0}}]
    try:
        cursor = await db[DOCUMENT_CHUNKS].aggregate(pipeline)
        found = [document async for document in cursor]
    except Exception as exc:
        logger.warning('Vector search unavailable (%s); scoring %s exactly in memory instead', exc, document_id)
        return await _exact_search(db, document_id=document_id, query=query, top_k=top_k, page_role=page_role, floor=floor)
    if not found:
        logger.info('Vector search returned nothing for %s; falling back to exact scoring in case the index is missing or still building', document_id)
        return await _exact_search(db, document_id=document_id, query=query, top_k=top_k, page_role=page_role, floor=floor)
    scored = [ScoredChunk(chunk=DocumentChunk.model_validate(_decode(document)), score=_to_cosine(document.get('score', 0.0))) for document in found]
    return in_reading_order([entry for entry in scored if entry.score >= floor])

async def _exact_search(db: AsyncDatabase[dict[str, Any]], *, document_id: str, query: list[float], top_k: int, page_role: PageRole | None, floor: float) -> list[ScoredChunk]:
    query_filter: dict[str, Any] = {'document_id': document_id}
    if page_role is not None:
        query_filter['page_role'] = page_role.value
    chunks = [DocumentChunk.model_validate(_decode(document)) async for document in db[DOCUMENT_CHUNKS].find(query_filter)]
    return rank(query, chunks, top_k=top_k, floor=floor)

def _to_cosine(score: float) -> float:
    return 2.0 * float(score) - 1.0

def _decode(document: dict[str, Any]) -> dict[str, Any]:
    decoded = dict(document)
    for key in ('_id', 'document_id'):
        if key in decoded and decoded[key] is not None:
            decoded[key] = str(decoded[key])
    decoded.setdefault('embedding', [])
    return decoded

def to_evidence(scored: list[ScoredChunk], *, start: int=1) -> list[Evidence]:
    return [Evidence(id=f'C{position}', kind=EvidenceKind.TEXT, label=f'page {entry.chunk.page_index + 1}', quote=entry.chunk.text, page_index=entry.chunk.page_index, chunk_id=entry.chunk.id) for position, entry in enumerate(scored, start=start)]
__all__ = ['NUM_CANDIDATES', 'SIMILARITY_FLOOR', 'TOP_K', 'ScoredChunk', 'in_reading_order', 'rank', 'search', 'to_evidence']
