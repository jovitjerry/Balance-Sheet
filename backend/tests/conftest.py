"""Shared test fixtures.

The suite has two kinds of test:

**Unit tests** - equation, money, storage, schemas, pipeline, health, parsing,
identification - need nothing external and always run.

**Integration tests** need a reachable MongoDB cluster. They are exactly the
tests that use the ``test_db`` fixture, and the ``integration`` marker is
applied to them automatically (see :func:`pytest_collection_modifyitems`), so
nobody has to remember to mark one.

**OCR tests** need the Tesseract *system binary*. They are exactly the tests
that use the ``ocr_engine`` fixture, and are marked ``ocr`` the same way.

**LLM tests** need a running Ollama with the configured model pulled. They are
exactly the tests that use the ``ollama_provider`` fixture, and are marked
``llm`` the same way. Almost nothing needs this: the normalization ladder is
exercised end to end against a stub provider, so what remains here is the
transport itself.

    pytest                              # everything; integration and ocr skip if unavailable
    pytest -m "not integration and not ocr and not llm"   # pure unit; nothing external
    pytest -m integration --require-mongo    # integration only; unreachable Atlas FAILS
    pytest -m ocr --require-ocr              # OCR only; missing Tesseract FAILS
    pytest -m "llm and not benchmark" --require-ollama   # transport check only
    pytest -m benchmark --require-ollama     # the model comparison; slow, opt-in

``--require-mongo`` and ``--require-ocr`` exist because a skip is the right
default for local unit work but the wrong answer in CI or when you are
deliberately verifying that dependency: there, a missing binary or a failed
connection silently passing as "skipped" would be a false green. The flags turn
those skips into hard failures.
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
from app.modules.ingestion.ocr import OcrEngine, TesseractOcrEngine

REQUIRE_MONGO = "--require-mongo"
REQUIRE_OCR = "--require-ocr"
REQUIRE_OLLAMA = "--require-ollama"


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
    parser.addoption(
        REQUIRE_OCR,
        action="store_true",
        default=False,
        help=(
            "Fail OCR tests when the Tesseract binary is missing instead of "
            "skipping them. Use in CI and when verifying the OCR install."
        ),
    )


    parser.addoption(
        REQUIRE_OLLAMA,
        action="store_true",
        default=False,
        help=(
            "Fail LLM tests when Ollama is unreachable or the model is not "
            "pulled, instead of skipping them. Use in CI and when verifying "
            "the local model setup."
        ),
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Mark tests by the external dependency their fixtures imply.

    Derived from fixture usage rather than hand-applied markers, so a new test
    cannot be miscategorised by forgetting the decorator.
    """
    for item in items:
        fixtures = getattr(item, "fixturenames", ())
        if "test_db" in fixtures:
            item.add_marker(pytest.mark.integration)
        if "ocr_engine" in fixtures:
            item.add_marker(pytest.mark.ocr)
        if "ollama_provider" in fixtures:
            item.add_marker(pytest.mark.llm)


@pytest.fixture
def settings() -> Settings:
    return get_settings()


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(tmp_path / "uploads")


@pytest.fixture
def ocr_engine(request: pytest.FixtureRequest) -> OcrEngine:
    """A Tesseract engine, or a clear stop if the binary is not installed.

    OCR needs the **Tesseract system binary**; the ``pytesseract`` pip package
    is only a wrapper around a command line. When it is missing this skips by
    default, or fails loudly under ``--require-ocr``.
    """
    engine = TesseractOcrEngine(language=get_settings().ocr_language)
    if not engine.available():
        message = (
            "Tesseract is not installed or not on PATH. The pytesseract pip "
            "package alone is not enough - install the Tesseract binary."
        )
        if request.config.getoption(REQUIRE_OCR):
            pytest.fail(f"{message} ({REQUIRE_OCR} was passed)", pytrace=False)
        pytest.skip(message)
    return engine


@pytest.fixture
def ollama_provider(request: pytest.FixtureRequest):
    """A real Ollama provider, or a clear stop if it cannot serve the model.

    Almost no test needs this. The normalization ladder - every validation
    rule, every failure mode - runs against a stub provider, because a live
    model gives no reliable way to produce a malformed answer on demand. What
    is left here is the transport, which only a live server can prove.
    """
    from app.core.llm.ollama import build_llm_provider

    config = get_settings()
    provider = build_llm_provider(
        host=config.ollama_host,
        model=config.ollama_model,
        timeout_s=config.ollama_timeout_s,
        num_ctx=config.ollama_num_ctx,
    )
    installed = provider.installed_models()
    if installed is None:
        message = (
            f"Ollama is not reachable at {config.ollama_host}. Install it from "
            "https://ollama.com and start it."
        )
    elif config.ollama_model not in installed:
        # A running server with nothing pulled is what a fresh install looks
        # like, and it fails quite differently from a server that is down.
        # Saying which one it is turns a confusing 404 into an instruction.
        message = (
            f"Ollama is running but {config.ollama_model!r} is not pulled. Run "
            f"'ollama pull {config.ollama_model}'."
            + (f" Installed: {', '.join(installed)}." if installed else " Nothing is installed yet.")
        )
    else:
        return provider

    if request.config.getoption(REQUIRE_OLLAMA):
        pytest.fail(f"{message} ({REQUIRE_OLLAMA} was passed)", pytrace=False)
    pytest.skip(message)


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
async def api_client(
    test_db: AsyncDatabase[dict[str, Any]], storage: LocalFileStorage
) -> AsyncIterator[AsyncClient]:
    """An HTTP client whose routes use the throwaway database and storage.

    The dependencies are overridden rather than the app being reconfigured, so
    a route test can never write to the real ``balancesheet`` database.
    """
    from app.core.deps import get_db, get_storage

    async with app.router.lifespan_context(app):
        app.dependency_overrides[get_db] = lambda: test_db
        app.dependency_overrides[get_storage] = lambda: storage
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as http:
                yield http
        finally:
            app.dependency_overrides.clear()


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
