"""Finding the passages that bear on a question.

Two paths to the same answer, and the fallback is not an apology.

``$vectorSearch`` is the primary: Atlas pre-filters on ``document_id`` in the
engine, so one document's text can never surface in another's answer.

**Exact in-memory scoring is the fallback**, used when the vector index is not
yet queryable. On Atlas M0 an index build is asynchronous and can lag a first
upload by minutes, and a document here holds on the order of fifteen chunks -
at which size brute force is not a degradation, it is *more* accurate than
approximate nearest neighbour and needs no index at all. The same scoring code
is what unit tests run, so the ranking logic is exercised with nothing
installed.

Both paths apply the same floor and return results in **reading order**, not
score order, so quoted passages appear as the document presents them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.core.db import DOCUMENT_CHUNKS, VECTOR_INDEX
from app.core.llm.embeddings import cosine
from app.core.schemas import DocumentChunk, Evidence, EvidenceKind, PageRole

logger = logging.getLogger(__name__)

# How many passages reach the prompt. Five ~600-character chunks is about 3,000
# characters, which sits comfortably beside the structured facts inside
# num_ctx=4096.
TOP_K = 5

# Atlas's documented starting point is roughly 20x the limit: enough candidates
# for good recall, few enough to stay fast on shared M0 compute.
NUM_CANDIDATES = 100

# Raw cosine, not Atlas's rescaled score. Below this a passage is dropped
# rather than padded into the context - and if everything falls below, the text
# path contributed nothing, which the caller treats as a grounding signal
# rather than as an empty success.
#
# A constant with a comment, not a setting: a deployment able to tune this
# could change an answer without changing a version number.
SIMILARITY_FLOOR = 0.55


@dataclass(frozen=True)
class ScoredChunk:
    """A retrieved passage and how well it matched."""

    chunk: DocumentChunk
    score: float


def rank(
    query: list[float],
    chunks: list[DocumentChunk],
    *,
    top_k: int = TOP_K,
    floor: float = SIMILARITY_FLOOR,
) -> list[ScoredChunk]:
    """Score, filter and order chunks against a query vector. Pure, no I/O.

    Ties break on page then position, so ranking is deterministic on a document
    with repeated wording - two identical passages must not swap places between
    runs.
    """
    scored = [ScoredChunk(chunk=chunk, score=cosine(query, chunk.embedding)) for chunk in chunks]
    keep = [entry for entry in scored if entry.score >= floor]
    keep.sort(
        key=lambda entry: (
            -entry.score,
            entry.chunk.page_index,
            entry.chunk.chunk_index,
        )
    )
    return in_reading_order(keep[:top_k])


def in_reading_order(scored: list[ScoredChunk]) -> list[ScoredChunk]:
    """Restore document order after ranking has chosen what to keep.

    Relevance decides *which* passages; the document decides what order they
    are read in. Presenting page 7 above page 2 because it scored higher
    invites the model to narrate the document backwards.
    """
    return sorted(
        scored, key=lambda entry: (entry.chunk.page_index, entry.chunk.chunk_index)
    )


async def search(
    db: AsyncDatabase[dict[str, Any]],
    *,
    document_id: str,
    query: list[float],
    top_k: int = TOP_K,
    page_role: PageRole | None = None,
    floor: float = SIMILARITY_FLOOR,
) -> list[ScoredChunk]:
    """Retrieve passages for one document. Never for any other.

    ``document_id`` is a required keyword argument, not a filter a caller may
    forget: a function that cannot be called without it cannot be called
    wrongly. It is also a declared filter field on the vector index, so the
    scoping happens inside the engine rather than by discarding foreign results
    afterwards.
    """
    conditions: list[dict[str, Any]] = [{"document_id": {"$eq": document_id}}]
    if page_role is not None:
        conditions.append({"page_role": {"$eq": page_role.value}})

    pipeline: list[dict[str, Any]] = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX,
                "path": "embedding",
                "queryVector": query,
                "numCandidates": NUM_CANDIDATES,
                "limit": top_k,
                "filter": conditions[0] if len(conditions) == 1 else {"$and": conditions},
            }
        },
        {"$set": {"score": {"$meta": "vectorSearchScore"}}},
        # The vector is 768 doubles per hit and nothing downstream reads it.
        {"$project": {"embedding": 0}},
    ]

    try:
        # aggregate() is a coroutine in PyMongo's async API and returns the
        # cursor - unlike find(), which returns one directly. Iterating without
        # awaiting silently yields nothing, which here would look exactly like
        # "no relevant passages" rather than like the bug it is.
        cursor = await db[DOCUMENT_CHUNKS].aggregate(pipeline)
        found = [document async for document in cursor]
    except Exception as exc:  # noqa: BLE001 - index missing, still building, unsupported
        logger.warning(
            "Vector search unavailable (%s); scoring %s exactly in memory instead",
            exc,
            document_id,
        )
        return await _exact_search(
            db,
            document_id=document_id,
            query=query,
            top_k=top_k,
            page_role=page_role,
            floor=floor,
        )

    if not found:
        # Approximate nearest neighbour returns the closest `limit` rows
        # whatever their scores, so over a non-empty corpus a working index
        # always returns *something*. Zero rows therefore means the index is
        # missing or still building - which Atlas reports as an empty result
        # rather than an error, and which would otherwise be indistinguishable
        # from "nothing in this document is relevant".
        logger.info(
            "Vector search returned nothing for %s; falling back to exact scoring "
            "in case the index is missing or still building",
            document_id,
        )
        return await _exact_search(
            db,
            document_id=document_id,
            query=query,
            top_k=top_k,
            page_role=page_role,
            floor=floor,
        )

    scored = [
        ScoredChunk(
            chunk=DocumentChunk.model_validate(_decode(document)),
            score=_to_cosine(document.get("score", 0.0)),
        )
        for document in found
    ]
    return in_reading_order([entry for entry in scored if entry.score >= floor])


async def _exact_search(
    db: AsyncDatabase[dict[str, Any]],
    *,
    document_id: str,
    query: list[float],
    top_k: int,
    page_role: PageRole | None,
    floor: float,
) -> list[ScoredChunk]:
    """Brute-force cosine over one document's chunks.

    Correct rather than approximate, and at fifteen-odd chunks per document the
    cost is not worth measuring. The same ``document_id`` scoping applies - it
    is the query filter, so nothing else can be loaded.
    """
    query_filter: dict[str, Any] = {"document_id": document_id}
    if page_role is not None:
        query_filter["page_role"] = page_role.value

    chunks = [
        DocumentChunk.model_validate(_decode(document))
        async for document in db[DOCUMENT_CHUNKS].find(query_filter)
    ]
    return rank(query, chunks, top_k=top_k, floor=floor)


def _to_cosine(score: float) -> float:
    """Convert an Atlas similarity score back to raw cosine.

    Atlas normalises cosine into ``(1 + cosine) / 2`` so scores sit in [0, 1].
    Undoing it keeps ``SIMILARITY_FLOOR`` meaning one thing in both retrieval
    paths - otherwise the same constant would be strict in memory and lax
    against Atlas, and only the fallback would ever be tuned.
    """
    return (2.0 * float(score)) - 1.0


def _decode(document: dict[str, Any]) -> dict[str, Any]:
    """Make a stored chunk validate: ObjectIds become strings."""
    decoded = dict(document)
    for key in ("_id", "document_id"):
        if key in decoded and decoded[key] is not None:
            decoded[key] = str(decoded[key])
    decoded.setdefault("embedding", [])
    return decoded


def to_evidence(scored: list[ScoredChunk], *, start: int = 1) -> list[Evidence]:
    """Tag retrieved passages ``C1``, ``C2``, ... for citation.

    The tag is what the model cites and what resolution later maps back to a
    page and a character range, so it is assigned here, once, in the order the
    passages will appear in the prompt.
    """
    return [
        Evidence(
            id=f"C{position}",
            kind=EvidenceKind.TEXT,
            label=f"page {entry.chunk.page_index + 1}",
            quote=entry.chunk.text,
            page_index=entry.chunk.page_index,
            chunk_id=entry.chunk.id,
        )
        for position, entry in enumerate(scored, start=start)
    ]


__all__ = [
    "NUM_CANDIDATES",
    "SIMILARITY_FLOOR",
    "TOP_K",
    "ScoredChunk",
    "in_reading_order",
    "rank",
    "search",
    "to_evidence",
]
