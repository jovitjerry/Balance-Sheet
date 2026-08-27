"""Module 4 HTTP routes.

Same conventions as Module 1: the module owns its router, dependencies arrive
through ``Depends``, and every error a caller can see is a message this codebase
wrote. No path, connection string, model internal or stack trace reaches a
response.

**A refusal is a 200.** "A Balance Sheet does not report profit" is the correct
answer to that question, not a failure - so it comes back as an answer carrying
a machine-readable ``reason``, and a caller branches on the payload rather than
on a status code that would misdescribe what happened.
"""

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

router = APIRouter(prefix="/documents", tags=["insights"])

# A question longer than this is not a question. Capped before anything is
# embedded or prompted, so an oversized body cannot become an oversized prompt.
MAX_QUESTION_CHARS = 1000


class DocumentNotFound(BalanceSheetError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "document_not_found"


class DocumentNotReady(BalanceSheetError):
    """Asked about a document Modules 2-3 have not finished with."""

    status_code = status.HTTP_409_CONFLICT
    code = "document_not_ready"


class Turn(BaseModel):
    """One earlier exchange, supplied by the client."""

    question: str = Field(max_length=MAX_QUESTION_CHARS)
    answer: str = Field(max_length=4000)


class Question(BaseModel):
    """A question about one stored document.

    History is sent by the client rather than held on the server: every turn
    re-retrieves from the document anyway, so there is no session state worth
    keeping, and none to get wrong.
    """

    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    history: list[Turn] = Field(default_factory=list, max_length=MAX_HISTORY_TURNS)


@router.post("/{document_id}/ask", response_model=Answer)
async def ask(
    document_id: str,
    body: Question,
    db: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_db)],
    llm: Annotated[LlmProvider, Depends(get_llm)],
    embeddings: Annotated[EmbeddingProvider, Depends(get_embeddings)],
    storage: Annotated[FileStorage, Depends(get_storage)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> Answer:
    """Ask a question about a processed Balance Sheet.

    Answers from the figures Modules 1-3 computed and, where the question calls
    for it, from passages of the document's own text. The model explains; it
    never calculates, and every figure in the reply is checked against the
    context before the reply is returned.

    **200** - answered. ``status`` distinguishes three outcomes: ``answered``;
    ``refused``, which is a correct result for a question this document cannot
    support and carries a ``reason``; and ``degraded``, meaning the local model
    was unreachable so the stored figures are returned without prose.

    **404** - no such document. **409** - the document has not been extracted
    yet. **503** - ``LLM_REQUIRED`` is set and the model is unreachable.
    """
    document = await _load(db, document_id)

    if document.extracted is None:
        raise DocumentNotReady(
            "This document has not finished processing, so there is nothing to "
            "ask about yet."
        )
    if document.status is DocumentStatus.REJECTED:
        # Module 1 refused it. Answering questions about figures nobody should
        # be reading would lend them a credibility the verdict denied them.
        raise DocumentNotReady(
            "This document was rejected during validation, so its figures are "
            "not answerable."
        )

    answer = await answer_question(
        document,
        body.question,
        provider=llm,
        embeddings=embeddings,
        db=db,
        storage=storage,
        settings=settings,
        history=[(turn.question, turn.answer) for turn in body.history],
    )

    await _record(db, answer)
    return answer


@router.post("/{document_id}/index", status_code=status.HTTP_202_ACCEPTED)
async def reindex(
    document_id: str,
    db: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_db)],
    embeddings: Annotated[EmbeddingProvider, Depends(get_embeddings)],
    storage: Annotated[FileStorage, Depends(get_storage)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> dict[str, Any]:
    """Rebuild a document's retrieval corpus.

    Not needed in normal use - the first question indexes lazily. This exists
    for the case where the chunking rules or the embedding model changed and
    you would rather pay the cost now than on somebody's next question.
    """
    document = await _load(db, document_id)
    await ensure_vector_index(db, dimensions=settings.embedding_dim)
    state = await index_document(
        db, document, embeddings=embeddings, storage=storage
    )

    if state is None:
        return {"indexed": False, "chunks": 0, "reason": "no extractable page text"}
    return {
        "indexed": True,
        "chunks": state.chunk_count,
        "embedding_model": state.embedding_model,
        "chunk_spec_version": state.chunk_spec_version,
    }


async def _load(
    db: AsyncDatabase[dict[str, Any]], document_id: str
) -> BalanceSheetDocument:
    try:
        oid = ObjectId(document_id)
    except (InvalidId, TypeError) as exc:
        raise InvalidUploadError("Not a valid document id.") from exc

    found = await db[BALANCE_SHEETS].find_one({"_id": oid})
    if found is None:
        raise DocumentNotFound(f"No document with id {document_id}.")
    return BalanceSheetDocument.from_mongo(found)


async def _record(db: AsyncDatabase[dict[str, Any]], answer: Answer) -> None:
    """Keep the question, the answer and how it was grounded.

    Small and reference-only: citations are stored as their tags and chunk ids,
    never as copies of the passages, which already exist one collection away.
    Kept for audit and because "show the grounding for this answer" is a thing
    the report needs to be able to do.

    A failure here must never lose an answer the caller is waiting on, so it is
    logged rather than raised.
    """
    try:
        await db[QA_HISTORY].insert_one(
            {
                "document_id": answer.document_id,
                "question": answer.question,
                "answer": answer.answer,
                "status": answer.status.value,
                "route": answer.route.value,
                "reason": answer.reason,
                "model": answer.model,
                "spec_version": answer.spec_version,
                "citations": [
                    {"id": citation.id, "chunk_id": citation.chunk_id}
                    for citation in answer.citations
                ],
                "verification": answer.verification.model_dump(mode="python"),
                "created_at": utcnow(),
            }
        )
    except Exception as exc:  # noqa: BLE001 - never lose an answer over an audit write
        logger.warning("Could not record the Q&A history entry: %s", exc)


__all__ = ["Question", "Turn", "router"]
