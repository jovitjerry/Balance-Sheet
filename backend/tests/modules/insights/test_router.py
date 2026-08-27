"""What a caller sees when asking a question.

Integration tests: they use the throwaway database. The model and the embedder
are stubbed, because what is under test is the HTTP contract - status codes,
payload shape, and the guarantee that nothing internal leaks - none of which
should depend on whether Ollama happens to be running.
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core.db import BALANCE_SHEETS, QA_HISTORY
from app.core.llm.base import LlmResult
from app.core.storage import LocalFileStorage
from app.main import app
from tests.modules.insights.fixtures import document_with_notes
from tests.modules.insights.test_indexing import StubEmbeddings

ASK = "/api/v1/documents/{id}/ask"


class StubLlm:
    name = "stub"
    model = "stub-model"

    def __init__(self, *, answer: str = "Inventory is 350000.", available: bool = True):
        self._answer = answer
        self._available = available

    def available(self) -> bool:
        return self._available

    async def complete_json(self, *, prompt, schema, options=None) -> LlmResult:
        payload = {
            "answer": self._answer,
            "sufficient": True,
            "citations": [schema["properties"]["citations"]["items"]["enum"][0]]
            if schema["properties"]["citations"].get("items", {}).get("enum")
            else [],
            "figures_used": ["350000"],
        }
        return LlmResult(payload=payload, model=self.model, raw=json.dumps(payload))


@pytest_asyncio.fixture
async def ask_client(
    test_db: AsyncDatabase[dict[str, Any]], storage: LocalFileStorage
) -> AsyncIterator[tuple[AsyncClient, str]]:
    """A client, plus the id of a stored, fully processed document."""
    from app.core.deps import get_db, get_embeddings, get_llm, get_storage

    document = document_with_notes()
    stored = document.to_mongo()
    stored.pop("_id", None)
    result = await test_db[BALANCE_SHEETS].insert_one(stored)
    document_id = str(result.inserted_id)

    async with app.router.lifespan_context(app):
        app.dependency_overrides[get_db] = lambda: test_db
        app.dependency_overrides[get_storage] = lambda: storage
        app.dependency_overrides[get_llm] = lambda: StubLlm()
        app.dependency_overrides[get_embeddings] = lambda: StubEmbeddings()
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as http:
                yield http, document_id
        finally:
            app.dependency_overrides.clear()


class TestAsking:
    async def test_a_question_is_answered_with_its_grounding(
        self, ask_client: tuple[AsyncClient, str]
    ) -> None:
        client, document_id = ask_client
        response = await client.post(
            ASK.format(id=document_id), json={"question": "How much inventory?"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "answered"
        assert body["answer"]
        assert body["verification"]["passed"] is True
        assert body["supporting_facts"]
        assert body["spec_version"]

    async def test_figures_are_strings_not_json_numbers(
        self, ask_client: tuple[AsyncClient, str]
    ) -> None:
        """A JSON number is an IEEE double, which is what Decimal exists to avoid."""
        client, document_id = ask_client
        response = await client.post(
            ASK.format(id=document_id), json={"question": "How much inventory?"}
        )

        for fact in response.json()["supporting_facts"]:
            assert fact["value"] is None or isinstance(fact["value"], str)

    async def test_an_out_of_scope_question_is_a_200_with_a_reason(
        self, ask_client: tuple[AsyncClient, str]
    ) -> None:
        """A refusal is a correct answer, not an error."""
        client, document_id = ask_client
        response = await client.post(
            ASK.format(id=document_id), json={"question": "What was the net profit?"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "refused"
        assert body["reason"] == "out_of_scope"
        assert body["model"] is None

    async def test_the_question_comes_back_with_the_answer(
        self, ask_client: tuple[AsyncClient, str]
    ) -> None:
        client, document_id = ask_client
        response = await client.post(
            ASK.format(id=document_id), json={"question": "How much inventory?"}
        )
        assert response.json()["question"] == "How much inventory?"


class TestIndexingThroughTheApi:
    async def test_asking_indexes_lazily(
        self, ask_client: tuple[AsyncClient, str], test_db: AsyncDatabase[dict[str, Any]]
    ) -> None:
        """Nothing is embedded until somebody actually asks something."""
        from app.core.db import DOCUMENT_CHUNKS

        client, document_id = ask_client
        assert await test_db[DOCUMENT_CHUNKS].count_documents({}) == 0

        await client.post(
            ASK.format(id=document_id),
            json={"question": "What does the note say about depreciation?"},
        )
        assert await test_db[DOCUMENT_CHUNKS].count_documents({}) > 0

    async def test_an_explicit_reindex_reports_what_it_built(
        self, ask_client: tuple[AsyncClient, str]
    ) -> None:
        client, document_id = ask_client
        response = await client.post(f"/api/v1/documents/{document_id}/index")

        assert response.status_code == 202
        body = response.json()
        assert body["indexed"] is True
        assert body["chunks"] > 0
        assert body["embedding_model"] == "stub-embed"


class TestHistoryIsRecorded:
    async def test_the_question_and_its_grounding_are_stored(
        self, ask_client: tuple[AsyncClient, str], test_db: AsyncDatabase[dict[str, Any]]
    ) -> None:
        client, document_id = ask_client
        await client.post(
            ASK.format(id=document_id), json={"question": "How much inventory?"}
        )

        entry = await test_db[QA_HISTORY].find_one({"document_id": document_id})
        assert entry is not None
        assert entry["question"] == "How much inventory?"
        assert entry["verification"]["passed"] is True

    async def test_it_stores_references_not_copies_of_the_passages(
        self, ask_client: tuple[AsyncClient, str], test_db: AsyncDatabase[dict[str, Any]]
    ) -> None:
        """The chunks already exist one collection away."""
        client, document_id = ask_client
        await client.post(
            ASK.format(id=document_id), json={"question": "How much inventory?"}
        )

        entry = await test_db[QA_HISTORY].find_one({"document_id": document_id})
        assert entry is not None
        for citation in entry["citations"]:
            assert set(citation) == {"id", "chunk_id"}


class TestErrorCases:
    async def test_an_unknown_document_is_404(
        self, ask_client: tuple[AsyncClient, str]
    ) -> None:
        client, _ = ask_client
        response = await client.post(
            ASK.format(id="652f1a2b3c4d5e6f70819999"), json={"question": "Anything?"}
        )
        assert response.status_code == 404

    async def test_a_malformed_id_is_400(
        self, ask_client: tuple[AsyncClient, str]
    ) -> None:
        client, _ = ask_client
        response = await client.post(
            ASK.format(id="not-an-id"), json={"question": "Anything?"}
        )
        assert response.status_code == 400

    async def test_an_unprocessed_document_is_409(
        self, ask_client: tuple[AsyncClient, str], test_db: AsyncDatabase[dict[str, Any]]
    ) -> None:
        client, _ = ask_client
        bare = document_with_notes().model_copy(update={"extracted": None})
        stored = bare.to_mongo()
        stored.pop("_id", None)
        result = await test_db[BALANCE_SHEETS].insert_one(stored)

        response = await client.post(
            ASK.format(id=str(result.inserted_id)), json={"question": "Anything?"}
        )
        assert response.status_code == 409

    async def test_an_empty_question_is_rejected(
        self, ask_client: tuple[AsyncClient, str]
    ) -> None:
        client, document_id = ask_client
        response = await client.post(ASK.format(id=document_id), json={"question": ""})
        assert response.status_code == 422

    async def test_an_enormous_question_is_rejected_before_anything_runs(
        self, ask_client: tuple[AsyncClient, str]
    ) -> None:
        client, document_id = ask_client
        response = await client.post(
            ASK.format(id=document_id), json={"question": "x" * 5000}
        )
        assert response.status_code == 422


class TestResponsesLeakNothing:
    """The rule Module 1 set, extended to these routes."""

    async def test_no_internals_in_any_error(
        self, ask_client: tuple[AsyncClient, str], test_db: AsyncDatabase[dict[str, Any]]
    ) -> None:
        client, document_id = ask_client
        responses = [
            await client.post(ASK.format(id="not-an-id"), json={"question": "hi"}),
            await client.post(
                ASK.format(id="652f1a2b3c4d5e6f70819999"), json={"question": "hi"}
            ),
            await client.post(ASK.format(id=document_id), json={"question": ""}),
        ]

        for response in responses:
            body = response.text.lower()
            for leak in (
                "traceback",
                "mongodb+srv",
                "c:\\\\users",
                "/home/",
                "password",
                ".py\", line",
                "pymongo",
            ):
                assert leak not in body, f"{leak!r} leaked in {response.status_code}"

    async def test_an_answer_carries_no_connection_details(
        self, ask_client: tuple[AsyncClient, str]
    ) -> None:
        client, document_id = ask_client
        response = await client.post(
            ASK.format(id=document_id), json={"question": "How much inventory?"}
        )

        body = response.text.lower()
        assert "mongodb" not in body
        assert "localhost:11434" not in body


class TestDegradedMode:
    async def test_without_a_model_the_figures_still_come_back(
        self, test_db: AsyncDatabase[dict[str, Any]], storage: LocalFileStorage
    ) -> None:
        """The ratio was computed by Module 3 and stored. Withhold it and nobody wins."""
        from app.core.deps import get_db, get_embeddings, get_llm, get_storage

        stored = document_with_notes().to_mongo()
        stored.pop("_id", None)
        result = await test_db[BALANCE_SHEETS].insert_one(stored)

        async with app.router.lifespan_context(app):
            app.dependency_overrides[get_db] = lambda: test_db
            app.dependency_overrides[get_storage] = lambda: storage
            app.dependency_overrides[get_llm] = lambda: StubLlm(available=False)
            app.dependency_overrides[get_embeddings] = lambda: StubEmbeddings()
            try:
                transport = ASGITransport(app=app)
                async with AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    response = await client.post(
                        ASK.format(id=str(result.inserted_id)),
                        json={"question": "What is the current ratio?"},
                    )
            finally:
                app.dependency_overrides.clear()

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "degraded"
        assert body["answer"] is None

        ratios = {
            fact["label"]: fact["value"]
            for fact in body["supporting_facts"]
            if fact["kind"] == "ratio"
        }
        assert ratios["current_ratio"] == "1.307692"
