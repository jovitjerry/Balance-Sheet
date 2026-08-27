"""Building and refreshing a document's retrieval corpus.

**Indexing is lazy.** It happens on the first question asked about a document,
not at upload. Upload therefore stays exactly as fast as it was and still works
with Ollama stopped, and embedding cost is paid only for documents somebody
actually asks about - which, in a system where most uploads are never queried,
is most of the cost avoided.

**Re-indexing is decided by comparison, not by a timestamp.** A chunking change
and an embedding-model change both invalidate stored vectors, and
:class:`~app.core.schemas.ChunkIndexState` records enough to tell which
happened. Chunks are replaced wholesale rather than patched: it is one delete
and one insert, and a half-updated corpus would retrieve a mixture of two
embedding spaces, which is worse than either.
"""

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


async def ensure_indexed(
    db: AsyncDatabase[dict[str, Any]],
    document: BalanceSheetDocument,
    *,
    embeddings: EmbeddingProvider,
    storage: FileStorage | None = None,
) -> ChunkIndexState | None:
    """Index ``document`` if it has not been indexed with the current settings.

    Returns the state in force, or ``None`` when there was nothing to index -
    a document with no extractable text is a real case, not a failure.
    """
    current = document.chunk_index
    if current is not None and not current.is_stale(
        embedding_model=embeddings.model, chunk_spec_version=CHUNK_SPEC_VERSION
    ):
        return current

    if current is not None:
        logger.info(
            "Re-indexing %s: built with %s/%s, now %s/%s",
            document.id,
            current.embedding_model,
            current.chunk_spec_version,
            embeddings.model,
            CHUNK_SPEC_VERSION,
        )

    return await index_document(
        db, document, embeddings=embeddings, storage=storage
    )


async def index_document(
    db: AsyncDatabase[dict[str, Any]],
    document: BalanceSheetDocument,
    *,
    embeddings: EmbeddingProvider,
    storage: FileStorage | None = None,
) -> ChunkIndexState | None:
    """Chunk, embed and store ``document``'s text, replacing anything stored.

    The two halves stay apart deliberately: chunking is deterministic and needs
    nothing installed, embedding needs a model and a network call. So a
    chunking bug is reproducible without Ollama, and an embedding failure
    cannot leave half a corpus behind - nothing is deleted until the vectors
    are in hand.
    """
    if document.id is None:
        raise ValueError("Cannot index a document that has not been stored.")

    # Rehydrate first: a document read back from Mongo carries no inline
    # preliminary if Module 1 spilled it to the file store.
    hydrated = document
    if document.preliminary is None and document.preliminary_ref is not None:
        preliminary = await load_preliminary(document, storage=storage)
        hydrated = document.model_copy(update={"preliminary": preliminary})

    chunks = chunks_for(hydrated)
    if not chunks:
        logger.info("Nothing to index for %s: no extractable page text", document.id)
        return None

    vectors = await embeddings.embed([chunk.text for chunk in chunks])

    stamped = [
        chunk.model_copy(
            update={
                "embedding": vector,
                "embedding_model": embeddings.model,
                "embedding_dim": len(vector),
            }
        )
        for chunk, vector in zip(chunks, vectors)
    ]

    # Only now is the old corpus dropped. An embedding failure above leaves the
    # previous chunks intact and still answerable.
    await delete_chunks(db, document.id)
    await db[DOCUMENT_CHUNKS].insert_many(
        [_to_mongo(chunk) for chunk in stamped]
    )

    await _ensure_vector_index_once(db, dimensions=embeddings.dimensions)

    state = ChunkIndexState(
        indexed_at=utcnow(),
        embedding_model=embeddings.model,
        embedding_dim=embeddings.dimensions,
        chunk_spec_version=CHUNK_SPEC_VERSION,
        chunk_count=len(stamped),
    )
    await _record_state(db, document.id, state)
    document.chunk_index = state
    logger.info("Indexed %s chunk(s) for %s", len(stamped), document.id)
    return state


# Whether this process has already asked for the vector index. Attempted once
# rather than on every document, for two reasons: listing search indexes on each
# index operation is a round trip bought for nothing, and repeatedly creating
# and dropping one across a test run leaves Atlas doing asynchronous index
# cleanup that can outlive the database it belonged to.
_vector_index_attempted = False


async def _ensure_vector_index_once(
    db: AsyncDatabase[dict[str, Any]], *, dimensions: int
) -> None:
    """Ask for the vector index the first time this process indexes anything.

    Here rather than at startup because it is only needed once there is
    something to search, and the build is asynchronous so boot must not wait on
    it. Never fatal: retrieval scores exactly in memory until the index serves,
    which at this corpus size is more accurate anyway.
    """
    global _vector_index_attempted
    if _vector_index_attempted:
        return
    _vector_index_attempted = True
    await ensure_vector_index(db, dimensions=dimensions)


async def delete_chunks(db: AsyncDatabase[dict[str, Any]], document_id: str) -> int:
    """Remove every chunk belonging to one document. Returns how many went."""
    result = await db[DOCUMENT_CHUNKS].delete_many({"document_id": document_id})
    return int(result.deleted_count)


def _to_mongo(chunk: DocumentChunk) -> dict[str, Any]:
    """Dump a chunk for insertion.

    Not routed through ``encode_for_mongo``: a chunk holds no monetary value.
    Its embedding is genuinely floating point - a direction in vector space,
    not an amount of money - so the Decimal rule that governs every figure in
    this project does not apply and would corrupt the vector if it did.
    """
    data = chunk.model_dump(by_alias=True, exclude_none=True, mode="python")
    data.pop("_id", None)
    return data


async def _record_state(
    db: AsyncDatabase[dict[str, Any]], document_id: str, state: ChunkIndexState
) -> None:
    """Note on the document what its chunks were built from."""
    await db[BALANCE_SHEETS].update_one(
        {"_id": ObjectId(document_id)},
        {
            "$set": {
                "chunk_index": state.model_dump(mode="python"),
                "updated_at": utcnow(),
            }
        },
    )


__all__ = ["delete_chunks", "ensure_indexed", "index_document"]
