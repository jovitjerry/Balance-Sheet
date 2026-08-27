"""The embedding provider, against a mocked transport.

Pure unit tests: no Ollama, no network. The live round trip is a separate,
opt-in test - what matters here is the request shape and, more importantly,
that every failure mode reports something a reader can act on rather than a
half-usable result.
"""

from __future__ import annotations

import json
import math

import httpx
import pytest

from app.core.llm.base import LlmUnavailable
from app.core.llm.embeddings import MAX_BATCH, EmbeddingProvider, OllamaEmbeddings, cosine

DIM = 4


def _provider(handler, *, dimensions: int = DIM) -> OllamaEmbeddings:
    return OllamaEmbeddings(
        host="http://ollama.test",
        model="nomic-embed-text",
        dimensions=dimensions,
        transport=httpx.MockTransport(handler),
    )


def _vectors(count: int, dimensions: int = DIM) -> list[list[float]]:
    return [[0.5] * dimensions for _ in range(count)]


def _ok(count: int, dimensions: int = DIM):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": _vectors(count, dimensions)})

    return handler


class TestItSatisfiesTheProtocol:
    def test_the_concrete_provider_is_an_embedding_provider(self) -> None:
        assert isinstance(_provider(_ok(1)), EmbeddingProvider)

    def test_it_is_not_confused_with_the_generation_provider(self) -> None:
        """Two seams, deliberately: the two model choices move independently."""
        from app.core.llm.base import LlmProvider

        assert not isinstance(_provider(_ok(1)), LlmProvider)


class TestRequestShape:
    async def test_it_posts_the_batch_to_the_embed_endpoint(self) -> None:
        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"embeddings": _vectors(2)})

        await _provider(handler).embed(["one", "two"])

        assert seen["url"] == "http://ollama.test/api/embed"
        assert seen["body"] == {"model": "nomic-embed-text", "input": ["one", "two"]}

    async def test_it_returns_one_vector_per_input_in_order(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            count = len(json.loads(request.content)["input"])
            return httpx.Response(
                200,
                json={"embeddings": [[float(n)] * DIM for n in range(count)]},
            )

        vectors = await _provider(handler).embed(["a", "b", "c"])

        assert [vector[0] for vector in vectors] == [0.0, 1.0, 2.0]

    async def test_an_empty_input_makes_no_request(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("embedding nothing must not call the service")

        assert await _provider(handler).embed([]) == []

    async def test_a_large_batch_is_split(self) -> None:
        """One enormous body is a failure mode; several ordinary ones are not."""
        batches: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            count = len(json.loads(request.content)["input"])
            batches.append(count)
            return httpx.Response(200, json={"embeddings": _vectors(count)})

        await _provider(handler).embed([f"chunk {n}" for n in range(MAX_BATCH + 5)])

        assert len(batches) == 2
        assert batches == [MAX_BATCH, 5]


class TestFailuresAreLoudAndActionable:
    async def test_an_unpulled_model_names_the_fix(self) -> None:
        provider = _provider(lambda request: httpx.Response(404, json={}))

        with pytest.raises(LlmUnavailable) as caught:
            await provider.embed(["text"])

        assert "ollama pull nomic-embed-text" in str(caught.value)
        assert "EMBEDDING_MODEL" in str(caught.value)

    async def test_an_unreachable_service_says_so(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        with pytest.raises(LlmUnavailable, match="Could not reach"):
            await _provider(handler).embed(["text"])

    async def test_a_server_error_leaks_nothing(self) -> None:
        provider = _provider(
            lambda request: httpx.Response(
                500, text="Traceback: /home/user/ollama/server.go:213 secret"
            )
        )

        with pytest.raises(LlmUnavailable) as caught:
            await provider.embed(["text"])

        message = str(caught.value)
        assert "Traceback" not in message
        assert "/home/user" not in message
        assert "secret" not in message

    async def test_a_dimension_mismatch_is_caught_here_not_at_insert_time(self) -> None:
        """Otherwise it surfaces as an opaque vector-index rejection later."""
        provider = _provider(_ok(1, dimensions=768), dimensions=384)

        with pytest.raises(LlmUnavailable) as caught:
            await provider.embed(["text"])

        assert "768" in str(caught.value)
        assert "EMBEDDING_DIM" in str(caught.value)

    async def test_a_short_response_is_refused_rather_than_zipped_wrongly(self) -> None:
        """Two inputs and one vector would silently mis-pair chunks to embeddings."""
        provider = _provider(_ok(1))

        with pytest.raises(LlmUnavailable, match="unusable"):
            await provider.embed(["one", "two"])

    async def test_a_malformed_body_is_refused(self) -> None:
        provider = _provider(lambda request: httpx.Response(200, json={"data": []}))

        with pytest.raises(LlmUnavailable, match="unusable"):
            await provider.embed(["text"])


class TestAvailability:
    def test_it_reports_rather_than_raises(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        assert _provider(handler).available() is False

    def test_a_reachable_service_is_available(self) -> None:
        assert _provider(lambda request: httpx.Response(200, json={"models": []})).available()


class TestCosine:
    def test_identical_unit_vectors_score_one(self) -> None:
        unit = [0.5, 0.5, 0.5, 0.5]  # length 1
        assert cosine(unit, unit) == pytest.approx(1.0)

    def test_orthogonal_vectors_score_zero(self) -> None:
        assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors_score_minus_one(self) -> None:
        assert cosine([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_mismatched_or_empty_vectors_score_zero_rather_than_raising(self) -> None:
        assert cosine([1.0], [1.0, 2.0]) == 0.0
        assert cosine([], []) == 0.0

    def test_it_needs_no_numerical_dependency(self) -> None:
        """Ollama returns unit vectors, so the dot product is the whole job."""
        assert math.isclose(cosine([0.6, 0.8], [0.6, 0.8]), 1.0, rel_tol=1e-9)
