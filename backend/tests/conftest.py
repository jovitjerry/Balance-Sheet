"""Shared test fixtures.

Unit tests (equation, money, storage, schemas) need nothing external. Tests
that touch MongoDB use the ``test_db`` fixture, which works against a separate
``<db>_test`` database, drops it afterwards, and skips when no cluster is
reachable - so the suite is green offline as well as on.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings, get_settings
from app.core.db import CODEC_OPTIONS, create_client, ping
from app.core.storage import LocalFileStorage
from app.main import app


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "uploads")


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """An HTTP client wired to the app, with the real lifespan running."""
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            yield http


@pytest_asyncio.fixture
async def test_db() -> AsyncIterator[AsyncDatabase[dict[str, Any]]]:
    """A throwaway database, dropped on teardown. Skips if Atlas is unreachable."""
    config = get_settings()
    mongo = create_client(config)
    try:
        await ping(mongo)
    except Exception as exc:  # noqa: BLE001 - any connectivity failure means skip
        await mongo.close()
        pytest.skip(f"MongoDB not reachable: {exc}")

    name = f"{config.mongodb_db}_test"
    try:
        yield mongo.get_database(name, codec_options=CODEC_OPTIONS)
    finally:
        await mongo.drop_database(name)
        await mongo.close()
