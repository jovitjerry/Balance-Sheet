from __future__ import annotations
import logging
from typing import Annotated, Any
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from pymongo.asynchronous.database import AsyncDatabase
from app.core.config import Settings
from app.core.db import BALANCE_SHEETS, QA_HISTORY, ensure_vector_index
from app.core.deps import get_db, get_embeddings, get_llm, get_settings_dep, get_storage
from app.core.errors import BalanceSheetError, InvalidUploadError
from app.core.llm.base import LlmProvider
from app.core.llm.embeddings import EmbeddingProvider
from app.core.schemas import Answer, BalanceSheetDocument, DocumentStatus, utcnow
from app.core.storage import FileStorage
from app.modules.insights.context import MAX_HISTORY_TURNS
from app.modules.insights.indexing import index_document
from app.modules.insights.service import answer_question
logger = logging.getLogger(__name__)
router = APIRouter(prefix='/documents', tags=['insights'])
MAX_QUESTION_CHARS = 1000

class DocumentNotFound(BalanceSheetError):
    status_code = status.HTTP_404_NOT_FOUND
    code = 'document_not_found'

class DocumentNotReady(BalanceSheetError):
    status_code = status.HTTP_409_CONFLICT
    code = 'document_not_ready'

class Turn(BaseModel):
    question: str = Field(max_length=MAX_QUESTION_CHARS)
    answer: str = Field(max_length=4000)

class Question(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    history: list[Turn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)

@router.post('/{document_id}/ask', response_model=Answer)
async def ask(document_id: str, body: Question, db: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_db)], llm: Annotated[LlmProvider, Depends(get_llm)], embeddings: Annotated[EmbeddingProvider, Depends(get_embeddings)], storage: Annotated[FileStorage, Depends(get_storage)], settings: Annotated[Settings, Depends(get_settings_dep)]) -> Answer:
    document = await _load(db, document_id)
    if document.extracted is None:
        raise DocumentNotReady('This document has not finished processing, so there is nothing to ask about yet.')
    if document.status is DocumentStatus.REJECTED:
        raise DocumentNotReady('This document was rejected during validation, so its figures are not answerable.')
    answer = await answer_question(document, body.question, provider=llm, embeddings=embeddings, db=db, storage=storage, settings=settings, history=[(turn.question, turn.answer) for turn in body.history])
    await _record(db, answer)
    return answer

@router.post('/{document_id}/index', status_code=status.HTTP_202_ACCEPTED)
async def reindex(document_id: str, db: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_db)], embeddings: Annotated[EmbeddingProvider, Depends(get_embeddings)], storage: Annotated[FileStorage, Depends(get_storage)], settings: Annotated[Settings, Depends(get_settings_dep)]) -> dict[str, Any]:
    document = await _load(db, document_id)
    await ensure_vector_index(db, dimensions=settings.embedding_dim)
    state = await index_document(db, document, embeddings=embeddings, storage=storage)
    if state is None:
        return {'indexed': False, 'chunks': 0, 'reason': 'no extractable page text'}
    return {'indexed': True, 'chunks': state.chunk_count, 'embedding_model': state.embedding_model, 'chunk_spec_version': state.chunk_spec_version}

async def _load(db: AsyncDatabase[dict[str, Any]], document_id: str) -> BalanceSheetDocument:
    try:
        oid = ObjectId(document_id)
    except (InvalidId, TypeError) as exc:
        raise InvalidUploadError('Not a valid document id.') from exc
    found = await db[BALANCE_SHEETS].find_one({'_id': oid})
    if found is None:
        raise DocumentNotFound(f'No document with id {document_id}.')
    return BalanceSheetDocument.from_mongo(found)

async def _record(db: AsyncDatabase[dict[str, Any]], answer: Answer) -> None:
    try:
        await db[QA_HISTORY].insert_one({'document_id': answer.document_id, 'question': answer.question, 'answer': answer.answer, 'status': answer.status.value, 'route': answer.route.value, 'reason': answer.reason, 'model': answer.model, 'spec_version': answer.spec_version, 'citations': [{'id': citation.id, 'chunk_id': citation.chunk_id} for citation in answer.citations], 'verification': answer.verification.model_dump(mode='python'), 'created_at': utcnow()})
    except Exception as exc:
        logger.warning('Could not record the Q&A history entry: %s', exc)
__all__ = ['Question', 'Turn', 'router']
