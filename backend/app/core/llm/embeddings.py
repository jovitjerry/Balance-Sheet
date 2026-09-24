from __future__ import annotations
import logging
from typing import Protocol, runtime_checkable
import httpx
from app.core.llm.base import LlmUnavailable
logger = logging.getLogger(__name__)
DEFAULT_HOST = 'http://localhost:11434'
DEFAULT_TIMEOUT_S = 60.0
_AVAILABILITY_TIMEOUT_S = 2.0
MAX_BATCH = 32

@runtime_checkable
class EmbeddingProvider(Protocol):
    name: str
    model: str
    dimensions: int

    def available(self) -> bool:
        ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        ...

class OllamaEmbeddings:
    name = 'ollama'

    def __init__(self, *, host: str=DEFAULT_HOST, model: str, dimensions: int, timeout_s: float=DEFAULT_TIMEOUT_S, transport: httpx.BaseTransport | None=None) -> None:
        self._host = host.rstrip('/')
        self.model = model
        self.dimensions = dimensions
        self._timeout_s = timeout_s
        self._transport = transport

    def available(self) -> bool:
        try:
            with httpx.Client(timeout=_AVAILABILITY_TIMEOUT_S, transport=self._transport) as client:
                return client.get(f'{self._host}/api/tags').status_code == 200
        except Exception as exc:
            logger.warning('Ollama is not reachable for embeddings: %s', exc)
            return False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), MAX_BATCH):
            vectors.extend(await self._embed_batch(texts[start:start + MAX_BATCH]))
        return vectors

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        body = {'model': self.model, 'input': batch}
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s, transport=self._transport) as client:
                response = await client.post(f'{self._host}/api/embed', json=body)
        except httpx.HTTPError as exc:
            raise LlmUnavailable(f'Could not reach the local model service at {self._host}.') from exc
        if response.status_code == 404:
            raise LlmUnavailable(f"The embedding model {self.model!r} is not available locally. Pull it with 'ollama pull {self.model}', or set EMBEDDING_MODEL to a model that is installed.")
        if response.status_code != 200:
            logger.error('Ollama embeddings returned %s: %s', response.status_code, response.text[:500])
            raise LlmUnavailable('The local model service returned an error.')
        vectors = response.json().get('embeddings')
        if not isinstance(vectors, list) or len(vectors) != len(batch):
            raise LlmUnavailable('The local model service returned an unusable embedding response.')
        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != self.dimensions:
                raise LlmUnavailable(f"The embedding model {self.model!r} returned {(len(vector) if isinstance(vector, list) else 'no')} dimensions; EMBEDDING_DIM is set to {self.dimensions}.")
        return vectors

def build_embedding_provider(*, host: str=DEFAULT_HOST, model: str, dimensions: int, timeout_s: float=DEFAULT_TIMEOUT_S) -> OllamaEmbeddings:
    return OllamaEmbeddings(host=host, model=model, dimensions=dimensions, timeout_s=timeout_s)

def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum((a * b for a, b in zip(left, right)))
__all__ = ['DEFAULT_HOST', 'DEFAULT_TIMEOUT_S', 'MAX_BATCH', 'EmbeddingProvider', 'OllamaEmbeddings', 'build_embedding_provider', 'cosine']
