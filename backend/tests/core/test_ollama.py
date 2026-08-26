"""The Ollama provider: transport only, no judgement about the answer.

Pure unit tests. ``httpx.MockTransport`` stands in for the server, so the
request shape, the failure modes and the error messages are all verified
without Ollama installed. A live round trip is a separate, opt-in test.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.core.llm.base import LlmUnavailable
from app.core.llm.ollama import OllamaProvider

ANSWER = {"reasoning": "receivables", "canonical_label": "trade_receivables", "confidence": 0.9}


def provider(handler, **kwargs: Any) -> OllamaProvider:
    return OllamaProvider(
        host="http://localhost:11434",
        model="qwen3:8b",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def chat_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, json={"model": "qwen3:8b", "message": {"content": json.dumps(ANSWER)}}
    )


class TestRequestShape:
    async def test_it_sends_the_schema_as_the_format(self) -> None:
        """This is what makes decoding constrained rather than hopeful."""
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(json.loads(request.content))
            return chat_ok(request)

        schema = {"type": "object", "properties": {"a": {"type": "string"}}}
        await provider(handler).complete_json(prompt="classify this", schema=schema)

        assert seen["format"] == schema

    async def test_it_does_not_stream(self) -> None:
        """A streamed reply would have to be reassembled before it could be parsed."""
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(json.loads(request.content))
            return chat_ok(request)

        await provider(handler).complete_json(prompt="p", schema={})
        assert seen["stream"] is False

    async def test_the_caller_options_reach_the_model(self) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(json.loads(request.content))
            return chat_ok(request)

        await provider(handler).complete_json(
            prompt="p", schema={}, options={"temperature": 0}
        )
        assert seen["options"]["temperature"] == 0

    async def test_the_context_window_is_capped(self) -> None:
        """8 GB of VRAM is the binding constraint; an uncapped context spills."""
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(json.loads(request.content))
            return chat_ok(request)

        await provider(handler, num_ctx=4096).complete_json(prompt="p", schema={})
        assert seen["options"]["num_ctx"] == 4096

    async def test_thinking_is_disabled(self) -> None:
        """Qwen3 reasons at length by default, which costs seconds per label."""
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(json.loads(request.content))
            return chat_ok(request)

        await provider(handler).complete_json(prompt="p", schema={})
        assert seen["think"] is False

    async def test_the_prompt_is_sent_as_a_user_message(self) -> None:
        seen: dict[str, Any] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(json.loads(request.content))
            return chat_ok(request)

        await provider(handler).complete_json(prompt="classify this", schema={})
        assert seen["messages"] == [{"role": "user", "content": "classify this"}]


class TestResponse:
    async def test_it_returns_the_parsed_payload(self) -> None:
        result = await provider(chat_ok).complete_json(prompt="p", schema={})
        assert result.payload == ANSWER

    async def test_it_reports_which_model_answered(self) -> None:
        """A stored mapping has to name the model that decided it."""
        result = await provider(chat_ok).complete_json(prompt="p", schema={})
        assert result.model == "qwen3:8b"

    async def test_a_non_json_body_is_refused_not_guessed_at(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"message": {"content": "I think it is..."}})

        with pytest.raises(ValueError):
            await provider(handler).complete_json(prompt="p", schema={})


class TestFailures:
    async def test_a_missing_model_says_so_and_names_the_setting(self) -> None:
        """The commonest first-run failure: Ollama is up, the model is not pulled."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"error": 'model "qwen3:8b" not found'})

        with pytest.raises(LlmUnavailable) as caught:
            await provider(handler).complete_json(prompt="p", schema={})

        message = str(caught.value)
        assert "qwen3:8b" in message
        assert "OLLAMA_MODEL" in message

    async def test_a_server_error_is_wrapped_not_forwarded(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="traceback: /usr/lib/ollama/internal.go:42")

        with pytest.raises(LlmUnavailable) as caught:
            await provider(handler).complete_json(prompt="p", schema={})

        assert "internal.go" not in str(caught.value), "server internals reached the caller"

    async def test_a_connection_failure_is_wrapped(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        with pytest.raises(LlmUnavailable):
            await provider(handler).complete_json(prompt="p", schema={})


class TestAvailability:
    async def test_a_reachable_server_is_available(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/tags"
            return httpx.Response(200, json={"models": [{"name": "qwen3:8b"}]})

        assert provider(handler).available() is True

    async def test_an_unreachable_server_is_not_available(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        assert provider(handler).available() is False

    async def test_availability_never_raises(self) -> None:
        """It is asked on the happy path, so it reports rather than throws."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        assert provider(handler).available() is False


class TestInstalledModels:
    """A running server with nothing pulled is what a fresh install looks like.

    It fails quite differently from a server that is down, and the two need
    different things done about them - so they are distinguishable rather than
    both collapsing into "unavailable".
    """

    async def test_it_lists_what_the_server_can_serve(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"models": [{"name": "qwen3:8b"}, {"name": "llama3.1:8b"}]}
            )

        assert provider(handler).installed_models() == ["qwen3:8b", "llama3.1:8b"]

    async def test_a_server_with_nothing_pulled_is_still_reachable(self) -> None:
        """An empty list, not None. The distinction is the whole point."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"models": []})

        subject = provider(handler)
        assert subject.installed_models() == []
        assert subject.available() is True

    async def test_an_unreachable_server_reports_none(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        assert provider(handler).installed_models() is None


class TestCompleteText:
    """Free prose, for the Module 4-style benchmark. No schema, no grammar."""

    async def test_it_returns_the_message_content(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert "format" not in body, "prose must not be schema-constrained"
            return httpx.Response(200, json={"message": {"content": "Total assets are 2,300,000."}})

        answer = await provider(handler).complete_text(prompt="what are total assets?")
        assert answer == "Total assets are 2,300,000."

    async def test_a_server_error_is_wrapped(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="internal detail")

        with pytest.raises(LlmUnavailable):
            await provider(handler).complete_text(prompt="p")
