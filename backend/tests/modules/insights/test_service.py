"""The whole flow, against scripted stubs.

No Ollama, no Atlas, no embedding model. Every guard - routing, grounding,
verification, the retry, the refusals - is exercised here, because a real model
gives no reliable way to produce a specific wrong answer on demand, which is
exactly what these tests need to do.
"""

from __future__ import annotations

import json

import pytest

from app.core.config import Settings
from app.core.errors import StageNotImplemented
from app.core.llm.base import LlmResult, LlmUnavailable
from app.core.schemas import AnswerStatus, RetrievalRoute
from app.modules.insights import service
from app.modules.insights.service import RAG_SPEC_VERSION, answer_question
from tests.modules.insights.fixtures import analyzed_document


class ScriptedProvider:
    """A model that says exactly what a test tells it to, in order."""

    name = "scripted"
    model = "test-model"

    def __init__(self, *replies: dict, available: bool = True) -> None:
        self._replies = list(replies)
        self._available = available
        self.prompts: list[str] = []
        self.schemas: list[dict] = []

    def available(self) -> bool:
        return self._available

    async def complete_json(self, *, prompt, schema, options=None) -> LlmResult:
        self.prompts.append(prompt)
        self.schemas.append(schema)
        if not self._replies:
            raise AssertionError("the model was called more times than scripted")
        payload = self._replies.pop(0)
        return LlmResult(payload=payload, model=self.model, raw=json.dumps(payload))


class SilentProvider:
    """A model that must never be consulted."""

    name = "silent"
    model = "none"

    def available(self) -> bool:
        return True

    async def complete_json(self, **kwargs):  # pragma: no cover
        raise AssertionError("this question should never have reached a model")


def _reply(
    answer: str = "Inventory is 350000.",
    *,
    sufficient: bool = True,
    citations: list[str] | None = None,
    figures: list[str] | None = None,
) -> dict:
    return {
        "answer": answer,
        "sufficient": sufficient,
        "citations": citations or [],
        "figures_used": figures or [],
    }


class TestAnsweringAQuestion:
    async def test_a_structured_question_is_answered_and_verified(
        self, settings: Settings
    ) -> None:
        provider = ScriptedProvider(_reply(citations=["F1"], figures=["350000"]))

        answer = await answer_question(
            analyzed_document(),
            "How much inventory is there?",
            provider=provider,
            settings=settings,
        )

        assert answer.status is AnswerStatus.ANSWERED
        assert answer.route is RetrievalRoute.STRUCTURED
        assert answer.verification.passed
        assert "350000" in answer.verification.figures_verified
        assert answer.model == "test-model"
        assert answer.spec_version == RAG_SPEC_VERSION

    async def test_the_supporting_facts_come_back_with_the_answer(
        self, settings: Settings
    ) -> None:
        provider = ScriptedProvider(_reply())
        answer = await answer_question(
            analyzed_document(), "How much inventory?", provider=provider, settings=settings
        )

        labels = {fact.label for fact in answer.supporting_facts}
        assert "Inventory" in labels
        assert "current_ratio" in labels

    async def test_citations_are_resolved_to_their_sources(
        self, settings: Settings
    ) -> None:
        provider = ScriptedProvider(_reply(citations=["F1"]))
        answer = await answer_question(
            analyzed_document(), "What are total assets?", provider=provider, settings=settings
        )

        [citation] = answer.citations
        assert citation.id == "F1"
        assert citation.value == "2300000"

    async def test_an_unresolvable_citation_is_dropped(
        self, settings: Settings
    ) -> None:
        """A citation pointing nowhere is worse than none."""
        provider = ScriptedProvider(_reply(citations=["F1", "C99"]))
        answer = await answer_question(
            analyzed_document(), "What are total assets?", provider=provider, settings=settings
        )

        assert [citation.id for citation in answer.citations] == ["F1"]

    async def test_the_citation_enum_is_closed_to_the_supplied_tags(
        self, settings: Settings
    ) -> None:
        provider = ScriptedProvider(_reply())
        await answer_question(
            analyzed_document(), "How much inventory?", provider=provider, settings=settings
        )

        allowed = provider.schemas[0]["properties"]["citations"]["items"]["enum"]
        assert "F1" in allowed
        assert "C1" not in allowed  # no text was retrieved for this question


class TestRefusalsThatNeverReachTheModel:
    """The cheapest correctness there is."""

    async def test_an_out_of_scope_question(self, settings: Settings) -> None:
        answer = await answer_question(
            analyzed_document(),
            "What was the net profit for the year?",
            provider=SilentProvider(),
            settings=settings,
        )

        assert answer.status is AnswerStatus.REFUSED
        assert answer.reason == service.REASON_OUT_OF_SCOPE
        assert answer.model is None
        assert "does not contain" in (answer.answer or "")

    async def test_it_says_what_the_document_does_hold(self, settings: Settings) -> None:
        answer = await answer_question(
            analyzed_document(),
            "How did revenue change compared with last year?",
            provider=SilentProvider(),
            settings=settings,
        )
        assert "liquidity and leverage ratios" in (answer.answer or "")

    async def test_an_unsupported_metric_is_refused_with_the_available_list(
        self, settings: Settings
    ) -> None:
        answer = await answer_question(
            analyzed_document(),
            "What is the Altman Z-score?",
            provider=SilentProvider(),
            settings=settings,
        )

        assert answer.reason == service.REASON_UNSUPPORTED_METRIC
        assert "current ratio" in (answer.answer or "")
        assert "working capital" in (answer.answer or "")

    async def test_every_reason_is_from_the_closed_set(self, settings: Settings) -> None:
        answer = await answer_question(
            analyzed_document(),
            "What is the net profit?",
            provider=SilentProvider(),
            settings=settings,
        )
        assert answer.reason in service.REASONS


class TestTheNumericGuard:
    async def test_an_invented_figure_triggers_a_retry(self, settings: Settings) -> None:
        """The benchmark failure: 550,000 stated for a true 850,000."""
        provider = ScriptedProvider(
            _reply("Current assets are 550,000, so it may struggle."),
            _reply("Current assets are 850000, which covers current liabilities."),
        )

        answer = await answer_question(
            analyzed_document(),
            "Can it pay its short-term bills?",
            provider=provider,
            settings=settings,
        )

        assert answer.status is AnswerStatus.ANSWERED
        assert answer.verification.retried
        assert answer.verification.passed
        assert len(provider.prompts) == 2

    async def test_the_retry_prompt_names_the_offending_figure(
        self, settings: Settings
    ) -> None:
        provider = ScriptedProvider(
            _reply("Current assets are 550,000."), _reply("Current assets are 850000.")
        )
        await answer_question(
            analyzed_document(),
            "Can it pay its bills?",
            provider=provider,
            settings=settings,
        )

        assert "550000" in provider.prompts[1]
        assert "Do not calculate" in provider.prompts[1]

    async def test_a_figure_that_stays_unverifiable_is_refused(
        self, settings: Settings
    ) -> None:
        provider = ScriptedProvider(
            _reply("Current assets are 550,000."),
            _reply("Current assets are still 550,000."),
        )

        answer = await answer_question(
            analyzed_document(),
            "Can it pay its bills?",
            provider=provider,
            settings=settings,
        )

        assert answer.status is AnswerStatus.REFUSED
        assert answer.reason == service.REASON_UNVERIFIABLE_FIGURES
        assert "550000" in answer.verification.figures_unverified
        assert not answer.verification.passed

    async def test_a_refused_answer_still_returns_the_real_figures(
        self, settings: Settings
    ) -> None:
        """The reader gets the facts even when the prose could not be trusted."""
        provider = ScriptedProvider(
            _reply("Current assets are 550,000."), _reply("Still 550,000.")
        )
        answer = await answer_question(
            analyzed_document(),
            "Can it pay its bills?",
            provider=provider,
            settings=settings,
        )

        labels = {fact.label for fact in answer.supporting_facts}
        assert "current_ratio" in labels

    async def test_it_only_retries_once(self, settings: Settings) -> None:
        provider = ScriptedProvider(
            _reply("550,000."), _reply("550,000 again.")
        )
        await answer_question(
            analyzed_document(), "Can it pay?", provider=provider, settings=settings
        )
        assert len(provider.prompts) == 2


class TestMalformedResponses:
    async def test_a_missing_field_is_refused_not_half_used(
        self, settings: Settings
    ) -> None:
        provider = ScriptedProvider({"answer": "Inventory is 350000."})
        answer = await answer_question(
            analyzed_document(), "How much inventory?", provider=provider, settings=settings
        )

        assert answer.status is AnswerStatus.REFUSED
        assert answer.reason == service.REASON_MALFORMED_RESPONSE

    async def test_an_empty_answer_is_refused(self, settings: Settings) -> None:
        provider = ScriptedProvider(_reply(answer="   "))
        answer = await answer_question(
            analyzed_document(), "How much inventory?", provider=provider, settings=settings
        )
        assert answer.reason == service.REASON_MALFORMED_RESPONSE

    async def test_the_model_declining_is_recorded_as_such(
        self, settings: Settings
    ) -> None:
        provider = ScriptedProvider(
            _reply("The document does not say.", sufficient=False)
        )
        answer = await answer_question(
            analyzed_document(),
            "What is the depreciation policy?",
            provider=provider,
            settings=settings,
        )

        assert answer.status is AnswerStatus.REFUSED
        assert answer.reason == service.REASON_INSUFFICIENT_CONTEXT


class TestWithoutTheModel:
    async def test_it_degrades_to_facts_rather_than_failing(
        self, settings: Settings
    ) -> None:
        """The number is already computed; withholding it would help nobody."""
        answer = await answer_question(
            analyzed_document(),
            "What is the current ratio?",
            provider=ScriptedProvider(available=False),
            settings=settings,
        )

        assert answer.status is AnswerStatus.DEGRADED
        assert answer.answer is None
        assert answer.reason == service.REASON_LLM_UNAVAILABLE

        ratios = {
            fact.label: fact.value
            for fact in answer.supporting_facts
            if fact.kind.value == "ratio"
        }
        assert ratios["current_ratio"] == "1.307692"

    async def test_llm_required_turns_that_into_a_failure(
        self, settings: Settings
    ) -> None:
        strict = settings.model_copy(update={"llm_required": True})
        with pytest.raises(LlmUnavailable, match="LLM_REQUIRED"):
            await answer_question(
                analyzed_document(),
                "What is the current ratio?",
                provider=ScriptedProvider(available=False),
                settings=strict,
            )


class TestPromptSelection:
    async def test_a_ratio_question_gets_the_ratio_prompt(
        self, settings: Settings
    ) -> None:
        provider = ScriptedProvider(_reply("It is 1.307692."))
        await answer_question(
            analyzed_document(),
            "What is the current ratio?",
            provider=provider,
            settings=settings,
        )
        assert "already-calculated financial ratio" in provider.prompts[0]

    async def test_a_lookup_gets_the_short_factual_prompt(
        self, settings: Settings
    ) -> None:
        provider = ScriptedProvider(_reply())
        await answer_question(
            analyzed_document(), "How much inventory?", provider=provider, settings=settings
        )
        assert "direct factual question" in provider.prompts[0]

    async def test_every_prompt_forbids_calculation(self, settings: Settings) -> None:
        provider = ScriptedProvider(_reply(), _reply(), _reply())
        for question in (
            "How much inventory?",
            "What is the current ratio?",
            "Why does that matter?",
        ):
            await answer_question(
                analyzed_document(), question, provider=provider, settings=settings
            )
        for prompt in provider.prompts:
            assert "Never calculate" in prompt


class TestConversationFollowUps:
    async def test_history_is_offered_for_reference_only(
        self, settings: Settings
    ) -> None:
        provider = ScriptedProvider(_reply("It is comfortable."))
        await answer_question(
            analyzed_document(),
            "Is that good?",
            provider=provider,
            settings=settings,
            history=[("What is the current ratio?", "It is 1.307692.")],
        )

        prompt = provider.prompts[0]
        assert "EARLIER IN THIS CONVERSATION" in prompt
        assert "NOT a source" in prompt

    async def test_a_figure_from_a_prior_answer_is_not_admissible_by_itself(
        self, settings: Settings
    ) -> None:
        """Otherwise one wrong answer poisons every turn after it."""
        provider = ScriptedProvider(
            _reply("As established, current assets are 550,000."),
            _reply("Current assets are 850000."),
        )
        answer = await answer_question(
            analyzed_document(),
            "Is that good?",
            provider=provider,
            settings=settings,
            history=[("How much?", "Current assets are 550,000.")],
        )

        assert answer.verification.retried

    async def test_every_turn_re_grounds_from_the_document(
        self, settings: Settings
    ) -> None:
        provider = ScriptedProvider(_reply(), _reply())
        for _ in range(2):
            answer = await answer_question(
                analyzed_document(),
                "How much inventory?",
                provider=provider,
                settings=settings,
                history=[("earlier", "earlier answer")],
            )
            assert any(
                fact.label == "Inventory" for fact in answer.supporting_facts
            )


class TestPreconditions:
    async def test_an_unextracted_document_is_refused_clearly(
        self, settings: Settings
    ) -> None:
        document = analyzed_document().model_copy(update={"extracted": None})
        with pytest.raises(StageNotImplemented, match="not been extracted"):
            await answer_question(
                document, "How much inventory?", provider=SilentProvider(), settings=settings
            )

    async def test_the_legacy_explain_entry_point_refuses_rather_than_inventing(
        self, settings: Settings
    ) -> None:
        with pytest.raises(StageNotImplemented, match="answer_question"):
            await service.explain(analyzed_document())


class TestDeterminism:
    async def test_generation_asks_for_temperature_zero(
        self, settings: Settings
    ) -> None:
        """An academic result that moves between runs is not a result."""
        seen: dict = {}

        class Recording(ScriptedProvider):
            async def complete_json(self, *, prompt, schema, options=None):
                seen["options"] = options
                return await super().complete_json(
                    prompt=prompt, schema=schema, options=options
                )

        await answer_question(
            analyzed_document(),
            "How much inventory?",
            provider=Recording(_reply()),
            settings=settings,
        )
        assert seen["options"]["temperature"] == 0
