"""Storing and retrieving chunks in MongoDB.

Integration tests: they use the throwaway ``<MONGODB_DB>_test`` database and are
marked automatically. The embedding model is **stubbed** - what is under test is
the storage, the scoping and the isolation, none of which needs a real model,
and all of which needs a real database.
"""

from __future__ import annotations

from typing import Any

import pytest
from pymongo.asynchronous.database import AsyncDatabase

from app.core.db import DOCUMENT_CHUNKS
from app.core.schemas import ChunkIndexState, PageRole
from app.modules.insights.indexing import (
    delete_chunks,
    ensure_indexed,
    index_document,
)
from app.modules.insights.retrieval import search
from tests.modules.insights.fixtures import (
    DOCUMENT_ID,
    OTHER_DOCUMENT_ID,
    analyzed_document,
    document_with_notes,
)

DIM = 8


class StubEmbeddings:
    """Deterministic vectors keyed on the text, so retrieval is predictable.

    A word-presence vector: crude, but it makes "does the query find the right
    passage?" a property of the retrieval code rather than of a model's mood,
    which is what an integration test should be isolating.
    """

    name = "stub"
    model = "stub-embed"
    dimensions = DIM

    WORDS = (
        "inventory",
        "depreciation",
        "receivable",
        "policy",
        "cash",
        "equity",
        "cost",
        "asset",
    )

    def __init__(self) -> None:
        self.calls = 0

    def available(self) -> bool:
        return True

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        lowered = text.lower()
        raw = [1.0 if word in lowered else 0.0 for word in self.WORDS]
        length = sum(value * value for value in raw) ** 0.5
        # Unit length, as a real embedding model returns - so cosine is the dot
        # product and the similarity floor means the same thing here.
        return [value / length for value in raw] if length else [0.0] * DIM


@pytest.fixture
def embeddings() -> StubEmbeddings:
    return StubEmbeddings()


class TestIndexing:
    async def test_chunks_are_stored_with_their_vectors(
        self, test_db: AsyncDatabase[dict[str, Any]], embeddings: StubEmbeddings
    ) -> None:
        state = await index_document(
            test_db, document_with_notes(), embeddings=embeddings
        )

        assert state is not None
        assert state.chunk_count > 0
        stored = await test_db[DOCUMENT_CHUNKS].count_documents({})
        assert stored == state.chunk_count

        one = await test_db[DOCUMENT_CHUNKS].find_one({})
        assert len(one["embedding"]) == DIM
        assert one["embedding_model"] == "stub-embed"

    async def test_page_roles_are_stored(
        self, test_db: AsyncDatabase[dict[str, Any]], embeddings: StubEmbeddings
    ) -> None:
        await index_document(test_db, document_with_notes(), embeddings=embeddings)

        roles = await test_db[DOCUMENT_CHUNKS].distinct("page_role")
        assert set(roles) == {
            PageRole.BALANCE_SHEET.value,
            PageRole.SUPPLEMENTARY.value,
        }

    async def test_re_indexing_replaces_rather_than_duplicates(
        self, test_db: AsyncDatabase[dict[str, Any]], embeddings: StubEmbeddings
    ) -> None:
        document = document_with_notes()
        first = await index_document(test_db, document, embeddings=embeddings)
        second = await index_document(test_db, document, embeddings=embeddings)

        assert first is not None and second is not None
        assert second.chunk_count == first.chunk_count
        assert await test_db[DOCUMENT_CHUNKS].count_documents({}) == first.chunk_count

    async def test_a_document_with_no_text_indexes_nothing(
        self, test_db: AsyncDatabase[dict[str, Any]], embeddings: StubEmbeddings
    ) -> None:
        """Not a failure - a scanned page that OCR could not read is a real case."""
        empty = analyzed_document(pages=["   "])
        assert await index_document(test_db, empty, embeddings=embeddings) is None
        assert await test_db[DOCUMENT_CHUNKS].count_documents({}) == 0


class TestLazyIndexing:
    async def test_the_first_question_indexes(
        self, test_db: AsyncDatabase[dict[str, Any]], embeddings: StubEmbeddings
    ) -> None:
        state = await ensure_indexed(
            test_db, document_with_notes(), embeddings=embeddings
        )
        assert state is not None
        assert embeddings.calls == 1

    async def test_a_second_question_reuses_the_index(
        self, test_db: AsyncDatabase[dict[str, Any]], embeddings: StubEmbeddings
    ) -> None:
        """Re-embedding an unchanged document on every question would be waste."""
        document = document_with_notes()
        first = await ensure_indexed(test_db, document, embeddings=embeddings)
        document.chunk_index = first

        await ensure_indexed(test_db, document, embeddings=embeddings)
        assert embeddings.calls == 1

    async def test_a_changed_embedding_model_forces_a_rebuild(
        self, test_db: AsyncDatabase[dict[str, Any]], embeddings: StubEmbeddings
    ) -> None:
        """Vectors from two models are not comparable, so the old ones must go."""
        document = document_with_notes()
        document.chunk_index = ChunkIndexState(
            embedding_model="some-other-model",
            embedding_dim=DIM,
            chunk_spec_version="1.0.0",
            chunk_count=2,
        )

        await ensure_indexed(test_db, document, embeddings=embeddings)
        assert embeddings.calls == 1

    async def test_a_changed_chunking_version_forces_a_rebuild(
        self, test_db: AsyncDatabase[dict[str, Any]], embeddings: StubEmbeddings
    ) -> None:
        document = document_with_notes()
        document.chunk_index = ChunkIndexState(
            embedding_model="stub-embed",
            embedding_dim=DIM,
            chunk_spec_version="0.9.0",
            chunk_count=2,
        )

        await ensure_indexed(test_db, document, embeddings=embeddings)
        assert embeddings.calls == 1


class TestDocumentIsolation:
    """The requirement with no acceptable failure rate."""

    async def test_a_search_never_returns_another_documents_chunks(
        self, test_db: AsyncDatabase[dict[str, Any]], embeddings: StubEmbeddings
    ) -> None:
        await index_document(test_db, document_with_notes(), embeddings=embeddings)
        other = document_with_notes(document_id=OTHER_DOCUMENT_ID, sha="e" * 64)
        await index_document(test_db, other, embeddings=embeddings)

        [query] = await embeddings.embed(["depreciation cost asset"])
        found = await search(test_db, document_id=DOCUMENT_ID, query=query)

        assert found
        assert all(entry.chunk.document_id == DOCUMENT_ID for entry in found)

    async def test_wording_that_only_exists_in_another_document_finds_nothing(
        self, test_db: AsyncDatabase[dict[str, Any]], embeddings: StubEmbeddings
    ) -> None:
        """The question matches document B's contents; document A must answer nothing."""
        await index_document(
            test_db,
            analyzed_document(pages=["ASSETS\nCash and cash equivalents 125,000"]),
            embeddings=embeddings,
        )
        await index_document(
            test_db,
            analyzed_document(
                document_id=OTHER_DOCUMENT_ID,
                sha="e" * 64,
                pages=["Depreciation policy: straight-line over ten years."],
            ),
            embeddings=embeddings,
        )

        [query] = await embeddings.embed(["depreciation policy"])
        found = await search(test_db, document_id=DOCUMENT_ID, query=query)

        assert found == []

    async def test_deleting_one_documents_chunks_leaves_the_other_alone(
        self, test_db: AsyncDatabase[dict[str, Any]], embeddings: StubEmbeddings
    ) -> None:
        await index_document(test_db, document_with_notes(), embeddings=embeddings)
        other = document_with_notes(document_id=OTHER_DOCUMENT_ID, sha="e" * 64)
        await index_document(test_db, other, embeddings=embeddings)

        removed = await delete_chunks(test_db, DOCUMENT_ID)

        assert removed > 0
        assert await test_db[DOCUMENT_CHUNKS].count_documents(
            {"document_id": OTHER_DOCUMENT_ID}
        ) == removed


class TestSearchQuality:
    async def test_it_finds_the_passage_that_matches(
        self, test_db: AsyncDatabase[dict[str, Any]], embeddings: StubEmbeddings
    ) -> None:
        await index_document(test_db, document_with_notes(), embeddings=embeddings)

        [query] = await embeddings.embed(["depreciation cost asset"])
        found = await search(test_db, document_id=DOCUMENT_ID, query=query)

        assert found
        assert any("depreciation" in entry.chunk.text.lower() for entry in found)
        # The balance sheet page shares only "asset" with the query, and is
        # left out rather than included as the next best thing.
        assert all(entry.chunk.page_index == 1 for entry in found)

    async def test_an_unrelated_query_returns_nothing_rather_than_the_closest_thing(
        self, test_db: AsyncDatabase[dict[str, Any]], embeddings: StubEmbeddings
    ) -> None:
        """Padding the context with near-misses is how a model gets misled."""
        await index_document(
            test_db,
            analyzed_document(pages=["Cash and cash equivalents 125,000"]),
            embeddings=embeddings,
        )

        [query] = await embeddings.embed(["depreciation policy"])
        assert await search(test_db, document_id=DOCUMENT_ID, query=query) == []

    async def test_results_come_back_in_reading_order(
        self, test_db: AsyncDatabase[dict[str, Any]], embeddings: StubEmbeddings
    ) -> None:
        """Relevance chooses which passages; the document chooses their order.

        The floor is lifted here on purpose: this is about ordering, and it
        needs both pages returned to have anything to order.
        """
        await index_document(test_db, document_with_notes(), embeddings=embeddings)

        [query] = await embeddings.embed(["inventory cost asset"])
        found = await search(
            test_db, document_id=DOCUMENT_ID, query=query, floor=-1.0
        )

        pages = [entry.chunk.page_index for entry in found]
        assert pages == [0, 1]
