"""MongoDB access.

Uses PyMongo's async API (``AsyncMongoClient``) with **Stable API v1**.

Motor is deliberately NOT used: it is deprecated in favour of exactly this
API. Do not reintroduce it.
"""

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

BALANCE_SHEETS = "balance_sheets"
# Module 4's retrieval corpus. A separate collection, not a subdocument: it
# needs its own vector index, it is queried without the document, and a long
# filing's chunks would eventually threaten the 16 MB document cap.
DOCUMENT_CHUNKS = "document_chunks"
# Questions and their grounded answers, kept for audit and for the report.
QA_HISTORY = "qa_history"

VECTOR_INDEX = "chunks_vector_index"

# Decimal128 is how money is stored. Setting the codec options on the database
# handle means every collection reached through it inherits them, rather than
# each module converting ad hoc.
CODEC_OPTIONS: CodecOptions[dict[str, Any]] = CodecOptions(
    # Decimal128 values decode to bson.Decimal128; app.core.money converts to
    # decimal.Decimal at the schema boundary.
    tz_aware=True,
)


def create_client(settings: Settings) -> AsyncMongoClient[dict[str, Any]]:
    """Build an ``AsyncMongoClient`` pinned to Stable API v1.

    ``strict=False`` because Atlas Search index management (needed by Module 4's
    RAG) and ordinary debugging commands such as ``collStats`` sit outside
    Stable API v1; enabling strictness now would only mean disabling it later.
    ``deprecation_errors=True`` surfaces v1-deprecated commands loudly, which is
    what you want during development.

    The client MUST be created inside the FastAPI lifespan handler rather than
    at import time — an import-time client binds to the wrong event loop and
    breaks under pytest.
    """
    return AsyncMongoClient(
        # The one place the credential is unwrapped. Everywhere else the URI
        # stays a SecretStr so it cannot be printed by accident.
        settings.mongodb_uri.get_secret_value(),
        server_api=ServerApi("1", strict=False, deprecation_errors=True),
        serverSelectionTimeoutMS=settings.mongodb_timeout_ms,
        tz_aware=True,
    )


def get_database(
    client: AsyncMongoClient[dict[str, Any]], settings: Settings
) -> AsyncDatabase[dict[str, Any]]:
    """Return the application database with shared codec options applied."""
    return client.get_database(settings.mongodb_db, codec_options=CODEC_OPTIONS)


async def ping(client: AsyncMongoClient[dict[str, Any]]) -> None:
    """Round-trip the server. Raises if the cluster is unreachable.

    ``ping`` is inside Stable API v1, so this works under the pinned API.
    """
    await client.admin.command("ping")


async def ensure_indexes(db: AsyncDatabase[dict[str, Any]]) -> None:
    """Create the ordinary indexes the application relies on. Idempotent.

    The **vector** index is deliberately not created here. Building one on
    Atlas is asynchronous and can take minutes, and startup must not wait on
    it - see :func:`ensure_vector_index`, which is called at the point
    retrieval is first needed.
    """
    collection = db[BALANCE_SHEETS]
    await collection.create_index([("source.sha256", ASCENDING)], name="source_sha256")
    await collection.create_index([("status", ASCENDING)], name="status")
    await collection.create_index([("created_at", DESCENDING)], name="created_at_desc")

    chunks = db[DOCUMENT_CHUNKS]
    # Scoping, deletion and staleness checks all go through document_id, and
    # it is also what the exact-search fallback filters on.
    await chunks.create_index([("document_id", ASCENDING)], name="chunk_document_id")

    await db[QA_HISTORY].create_index(
        [("document_id", ASCENDING), ("created_at", DESCENDING)], name="qa_document_id"
    )
    logger.info("Indexes ensured on %s", db.name)


def vector_index_definition(*, dimensions: int) -> dict[str, Any]:
    """The Atlas Vector Search index Module 4 queries.

    ``document_id`` is declared a **filter** field so that scoping a search to
    one document happens inside the engine, as a pre-filter, rather than by
    fetching neighbours from every document and discarding the foreign ones.
    That is the difference between isolation and a convention.

    One index. Atlas free clusters permit three of any search type, so this
    leaves room without ever approaching the cap.
    """
    return {
        "fields": [
            {
                "type": "vector",
                "path": "embedding",
                "numDimensions": dimensions,
                "similarity": "cosine",
            },
            {"type": "filter", "path": "document_id"},
            {"type": "filter", "path": "page_role"},
        ]
    }


async def ensure_vector_index(
    db: AsyncDatabase[dict[str, Any]], *, dimensions: int
) -> bool:
    """Create the vector index if it is missing. Returns whether it exists now.

    Never raises. A free-tier cluster may refuse, the build is asynchronous and
    may not be queryable yet, and older deployments may not support the command
    at all - none of which should stop a question being answered, because
    retrieval falls back to exact in-memory scoring, which at this corpus size
    is more accurate anyway.
    """
    collection = db[DOCUMENT_CHUNKS]
    try:
        existing = [index async for index in await collection.list_search_indexes()]
        if any(index.get("name") == VECTOR_INDEX for index in existing):
            return True

        await collection.create_search_index(
            {
                "name": VECTOR_INDEX,
                "type": "vectorSearch",
                "definition": vector_index_definition(dimensions=dimensions),
            }
        )
        logger.info(
            "Requested vector index %r on %s; Atlas builds it asynchronously, so "
            "the first searches may use exact scoring instead",
            VECTOR_INDEX,
            DOCUMENT_CHUNKS,
        )
        return False
    except Exception as exc:  # noqa: BLE001 - unsupported, refused, or racing
        logger.warning("Could not ensure the vector index: %s", exc)
        return False


__all__ = [
    "BALANCE_SHEETS",
    "DOCUMENT_CHUNKS",
    "QA_HISTORY",
    "VECTOR_INDEX",
    "Decimal128",
    "create_client",
    "ensure_indexes",
    "ensure_vector_index",
    "get_database",
    "ping",
    "vector_index_definition",
]
