from __future__ import annotations
import json
import logging
from typing import Any
import httpx
from app.core.llm.base import LlmResult, LlmUnavailable
logger = logging.getLogger(__name__)
DEFAULT_HOST = 'http://localhost:11434'
DEFAULT_NUM_CTX = 4096
DEFAULT_TIMEOUT_S = 120.0
_AVAILABILITY_TIMEOUT_S = 2.0

class OllamaProvider:
    name = 'ollama'

    def __init__(self, *, host: str=DEFAULT_HOST, model: str, timeout_s: float=DEFAULT_TIMEOUT_S, num_ctx: int=DEFAULT_NUM_CTX, transport: httpx.BaseTransport | None=None) -> None:
        self._host = host.rstrip('/')
        self.model = model
        self._timeout_s = timeout_s
        self._num_ctx = num_ctx
        self._transport = transport

    def available(self) -> bool:
        return self.installed_models() is not None

    def installed_models(self) -> list[str] | None:
        try:
            with httpx.Client(timeout=_AVAILABILITY_TIMEOUT_S, transport=self._transport) as client:
                response = client.get(f'{self._host}/api/tags')
                if response.status_code != 200:
                    return None
                return [entry.get('name', '') for entry in response.json().get('models', [])]
        except Exception as exc:
            logger.warning('Ollama is not reachable: %s', exc)
            return None

    async def complete_json(self, *, prompt: str, schema: dict[str, Any], options: dict[str, Any] | None=None) -> LlmResult:
        body: dict[str, Any] = {'model': self.model, 'messages': [{'role': 'user', 'content': prompt}], 'stream': False, 'format': schema, 'think': False, 'options': {'num_ctx': self._num_ctx, **(options or {})}}
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s, transport=self._transport) as client:
                response = await client.post(f'{self._host}/api/chat', json=body)
        except httpx.HTTPError as exc:
            raise LlmUnavailable(f'Could not reach the local model service at {self._host}.') from exc
        if response.status_code == 404:
            raise LlmUnavailable(f"The model {self.model!r} is not available locally. Pull it with 'ollama pull {self.model}', or set OLLAMA_MODEL to a model that is installed.")
        if response.status_code != 200:
            logger.error('Ollama returned %s: %s', response.status_code, response.text[:500])
            raise LlmUnavailable('The local model service returned an error.')
        content = response.json().get('message', {}).get('content', '')
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError('The model did not return valid JSON.') from exc
        return LlmResult(payload=payload, model=self.model, raw=content)

    async def complete_text(self, *, prompt: str, options: dict[str, Any] | None=None) -> str:
        body: dict[str, Any] = {'model': self.model, 'messages': [{'role': 'user', 'content': prompt}], 'stream': False, 'think': False, 'options': {'num_ctx': self._num_ctx, **(options or {})}}
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s, transport=self._transport) as client:
                response = await client.post(f'{self._host}/api/chat', json=body)
        except httpx.HTTPError as exc:
            raise LlmUnavailable(f'Could not reach the local model service at {self._host}.') from exc
        if response.status_code != 200:
            logger.error('Ollama returned %s: %s', response.status_code, response.text[:500])
            raise LlmUnavailable('The local model service returned an error.')
        return response.json().get('message', {}).get('content', '')

def build_llm_provider(*, host: str=DEFAULT_HOST, model: str, timeout_s: float=DEFAULT_TIMEOUT_S, num_ctx: int=DEFAULT_NUM_CTX) -> OllamaProvider:
    return OllamaProvider(host=host, model=model, timeout_s=timeout_s, num_ctx=num_ctx)
__all__ = ['DEFAULT_HOST', 'DEFAULT_NUM_CTX', 'DEFAULT_TIMEOUT_S', 'OllamaProvider', 'build_llm_provider']
