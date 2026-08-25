"""Shared test fixtures.

The suite has two kinds of test:

**Unit tests** - equation, money, storage, schemas, pipeline, health - need
nothing external and always run.

**Integration tests** need a reachable MongoDB cluster. They are exactly the
tests that use the ``test_db`` fixture, and the ``integration`` marker is
applied to them automatically (see :func:`pytest_collection_modifyitems`), so
nobody has to remember to mark one.

    pytest                              # everything; integration skips if Atlas is down
    pytest -m "not integration"         # unit tests only, no cluster needed
    pytest -m integration --require-mongo   # integration only; unreachable Atlas FAILS

``--require-mongo`` exists because a skip is the right default for local unit
work but the wrong answer in CI or when you are deliberately verifying Atlas:
there, a connection failure silently passing as "skipped" would be a false
green. The flag turns that skip into a hard failure.
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

REQUIRE_MONGO = "--require-mongo"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        REQUIRE_MONGO,
        action="store_true",
        default=False,
        help=(
            "Fail integration tests when MongoDB is unreachable instead of "
            "skipping them. Use in CI and when verifying Atlas connectivity."
        ),
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Mark every test that needs a live cluster as ``integration``.

    Derived from fixture usage rather than hand-applied markers, so a new
    integration test cannot be miscategorised by forgetting the decorator.
    """
    for item in items:
        if "test_db" in getattr(item, "fixturenames", ()):
            item.add_marker(pytest.mark.integration)


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "uploads")


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """An HTTP client wired to the app, with the real lifespan running.

    Not an integration fixture: the app boots and ``/health`` answers truthfully
    whether or not the cluster is reachable.
    """
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            yield http


@pytest_asyncio.fixture
async def test_db(
    request: pytest.FixtureRequest,
) -> AsyncIterator[AsyncDatabase[dict[str, Any]]]:
    """A throwaway database, dropped on teardown.

    Uses ``<MONGODB_DB>_test`` so a test run can never touch real data. When the
    cluster is unreachable this skips by default, or fails under
    ``--require-mongo``.
    """
    config = get_settings()
    mongo = create_client(config)
    try:
        await ping(mongo)
    except Exception as exc:  # noqa: BLE001 - any connectivity failure counts
        await mongo.close()
        message = f"MongoDB not reachable: {exc}"
        if request.config.getoption(REQUIRE_MONGO):
            pytest.fail(f"{message} ({REQUIRE_MONGO} was passed)", pytrace=False)
        pytest.skip(message)

    name = f"{config.mongodb_db}_test"
    try:
        yield mongo.get_database(name, codec_options=CODEC_OPTIONS)
    finally:
        await mongo.drop_database(name)
        await mongo.close()
