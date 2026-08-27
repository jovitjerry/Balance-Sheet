"""A real round trip to the configured embedding model.

Marked ``embeddings`` automatically by the fixture, and skipped when the model
is not pulled - or failed loudly under ``--require-embeddings``.

Almost nothing needs this. Chunking, ranking, the similarity floor and reading
order are all exercised with hand-written vectors, because Ollama returns unit
vectors and cosine is then a dot product. What only a live server can prove is
the transport, the dimension the configured model actually produces, and the
property everything else assumes: **that the vectors come back normalised**.
"""

from __future__ import annotations

import math

import pytest

from app.core.config import get_settings


class TestARealRoundTrip:
    async def test_it_returns_one_vector_per_input(self, embedding_provider) -> None:
        vectors = await embedding_provider.embed(
            ["Inventory is valued at the lower of cost and net realisable value.",
             "Total assets"]
        )
        assert len(vectors) == 2

    async def test_the_dimension_matches_the_configuration(
        self, embedding_provider
    ) -> None:
        """EMBEDDING_DIM and the model must agree, or the index rejects inserts."""
        [vector] = await embedding_provider.embed(["Trade receivables"])

        assert len(vector) == get_settings().embedding_dim
        assert len(vector) == embedding_provider.dimensions

    async def test_the_vectors_are_unit_length(self, embedding_provider) -> None:
        """The assumption the whole ranking design rests on.

        If this ever stopped holding, cosine would no longer equal the dot
        product and every similarity score - including the floor - would be
        quietly wrong rather than visibly broken.
        """
        [vector] = await embedding_provider.embed(["Property, plant and equipment"])
        length = math.sqrt(sum(value * value for value in vector))

        assert length == pytest.approx(1.0, abs=1e-3)

    async def test_it_is_deterministic(self, embedding_provider) -> None:
        """Re-embedding an unchanged document must not shuffle retrieval."""
        first = await embedding_provider.embed(["Trade payables"])
        second = await embedding_provider.embed(["Trade payables"])

        assert first[0] == pytest.approx(second[0], abs=1e-6)


class TestItSeparatesRelatedFromUnrelated:
    """The one quality property worth asserting: the ordering, not a threshold.

    Retrieval *quality* is not measured anywhere in this project - there is no
    labelled relevance set - so this claims only that a policy passage is
    closer to a policy question than an unrelated balance-sheet line is. A
    model that failed this would be unusable.
    """

    async def test_a_policy_passage_beats_an_unrelated_line(
        self, embedding_provider
    ) -> None:
        from app.core.llm.embeddings import cosine

        question, related, unrelated = await embedding_provider.embed(
            [
                "What is the depreciation policy for plant and machinery?",
                "Property, plant and equipment is stated at cost less accumulated "
                "depreciation, charged on a straight-line basis over ten years.",
                "Cash and cash equivalents 125,000",
            ]
        )

        assert cosine(question, related) > cosine(question, unrelated)
