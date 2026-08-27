"""The embedding provider seam.

Separate from :class:`~app.core.llm.base.LlmProvider` on purpose. Embedding and
generation are different models doing different jobs on different schedules -
Module 4 embeds once per document and generates once per question - and the two
choices must be able to move independently. Folding them into one Protocol
would oblige every generation stub in the test suite to implement ``embed``,
and would quietly imply that picking a chat model picks a retriever too.

Ollama returns **L2-normalised** vectors, which is worth knowing rather than
discovering: cosine similarity is therefore the dot product, so ranking can be
scored in a few lines of pure Python with no numpy anywhere in the project.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

import httpx

from app.core.llm.base import LlmUnavailable

logger = logging.getLogger(__name__)

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_TIMEOUT_S = 60.0
_AVAILABILITY_TIMEOUT_S = 2.0

# Ollama takes an array of inputs and returns an array of vectors, so a whole
# document's chunks go in one request. Capped so an unusually long filing does
# not build a single enormous body.
MAX_BATCH = 32


@runtime_checkable
class EmbeddingProvider(Protocol):
    """A local model that turns text into vectors."""

    name: str
    model: str
    dimensions: int

    def available(self) -> bool:
        """Whether the embedding model can be reached right now."""
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed each text, returning one vector per input, in order.

        Raises on transport failure; the caller decides what that means.
        """
        ...


class OllamaEmbeddings:
    """An embedding model served by Ollama.

    Deliberately a separate class from ``OllamaProvider`` rather than another
    method on it: they are configured with different models, called at
    different times, and either can be swapped without touching the other.
    """

    name = "ollama"

    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        model: str,
        dimensions: int,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._host = host.rstrip("/")
        self.model = model
        self.dimensions = dimensions
        self._timeout_s = timeout_s
        self._transport = transport

    def available(self) -> bool:
        """Whether Ollama answers. Reports rather than raises - it is a question."""
        try:
            with httpx.Client(
                timeout=_AVAILABILITY_TIMEOUT_S, transport=self._transport
            ) as client:
                return client.get(f"{self._host}/api/tags").status_code == 200
        except Exception as exc:  # noqa: BLE001 - any failure means unusable
            logger.warning("Ollama is not reachable for embeddings: %s", exc)
            return False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts, preserving order.

        :raises LlmUnavailable: the service is unreachable, the model is not
            pulled, or it returned something unusable.
        """
        if not texts:
            return []

        vectors: list[list[float]] = []
        for start in range(0, len(texts), MAX_BATCH):
            vectors.extend(await self._embed_batch(texts[start : start + MAX_BATCH]))
        return vectors

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        body = {"model": self.model, "input": batch}
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_s, transport=self._transport
            ) as client:
                response = await client.post(f"{self._host}/api/embed", json=body)
        except httpx.HTTPError as exc:
            raise LlmUnavailable(
                f"Could not reach the local model service at {self._host}."
            ) from exc

        if response.status_code == 404:
            # Running, but this model was never pulled - the commonest
            # first-run failure, so the message names the fix.
            raise LlmUnavailable(
                f"The embedding model {self.model!r} is not available locally. "
                f"Pull it with 'ollama pull {self.model}', or set "
                "EMBEDDING_MODEL to a model that is installed."
            )
        if response.status_code != 200:
            # The body may carry server paths. Logged, never forwarded.
            logger.error(
                "Ollama embeddings returned %s: %s",
                response.status_code,
                response.text[:500],
            )
            raise LlmUnavailable("The local model service returned an error.")

        vectors = response.json().get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(batch):
            raise LlmUnavailable(
                "The local model service returned an unusable embedding response."
            )

        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != self.dimensions:
                # A dimension mismatch means the configured EMBEDDING_DIM and
                # the model disagree. Caught here rather than at insert time,
                # where it would surface as an opaque vector-index rejection.
                raise LlmUnavailable(
                    f"The embedding model {self.model!r} returned "
                    f"{len(vector) if isinstance(vector, list) else 'no'} "
                    f"dimensions; EMBEDDING_DIM is set to {self.dimensions}."
                )
        return vectors


def build_embedding_provider(
    *,
    host: str = DEFAULT_HOST,
    model: str,
    dimensions: int,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> OllamaEmbeddings:
    """Construct the configured embedding provider.

    Returned whether or not Ollama is running, exactly as the OCR engine and
    the generation provider are: availability is asked where the model is
    needed, not made a reason to refuse to start.
    """
    return OllamaEmbeddings(
        host=host, model=model, dimensions=dimensions, timeout_s=timeout_s
    )


def cosine(left: list[float], right: list[float]) -> float:
    """Cosine similarity between two embeddings.

    Ollama returns unit vectors, so this is the dot product - which is why the
    project needs no numerical dependency to rank retrieval results, and why
    ranking is unit-testable with nothing installed.
    """
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_TIMEOUT_S",
    "MAX_BATCH",
    "EmbeddingProvider",
    "OllamaEmbeddings",
    "build_embedding_provider",
    "cosine",
]
