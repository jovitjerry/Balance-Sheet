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
    """Create the indexes the foundation relies on. Idempotent."""
    collection = db[BALANCE_SHEETS]
    await collection.create_index([("source.sha256", ASCENDING)], name="source_sha256")
    await collection.create_index([("status", ASCENDING)], name="status")
    await collection.create_index([("created_at", DESCENDING)], name="created_at_desc")
    logger.info("Indexes ensured on %s.%s", db.name, BALANCE_SHEETS)


__all__ = [
    "BALANCE_SHEETS",
    "Decimal128",
    "create_client",
    "ensure_indexes",
    "get_database",
    "ping",
]
