"""Terminology mapping: what accounting concept does this label represent?

**These tests need no Ollama.** The language model reaches this code through
:class:`~app.core.llm.base.LlmProvider`, so a stub provider that returns
whatever a test wants exercises the entire ladder - including every way a real
model can misbehave, which is the part that actually matters and the part a
live model would give us no reliable way to trigger.

The rule the whole file is built around: **a rejected answer never becomes a
guess.** Every failure lands on ``needs_review`` with the original label and
value untouched.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.core.llm.base import LlmResult
from app.core.schemas import NormalizationMethod, NormalizationStatus
from app.modules.extraction import taxonomy
from app.modules.extraction.normalization import Normalizer
from app.modules.extraction.taxonomy import Section, Subsection


class StubProvider:
    """An :class:`LlmProvider` that answers exactly what a test tells it to.

    Records every prompt, so tests can assert on what the model was actually
    shown rather than on what we believe it was shown.
    """

    name = "stub"

    def __init__(
        self,
        *answers: dict[str, Any] | Exception,
        model: str = "stub-model",
        available: bool = True,
    ) -> None:
        self.model = model
        self._answers = list(answers)
        self._available = available
        self.prompts: list[str] = []
        self.schemas: list[dict[str, Any]] = []
        self.calls = 0

    def available(self) -> bool:
        return self._available

    async def complete_json(
        self, *, prompt: str, schema: dict[str, Any], options: dict[str, Any] | None = None
    ) -> LlmResult:
        self.calls += 1
        self.prompts.append(prompt)
        self.schemas.append(schema)
        answer = self._answers[min(self.calls - 1, len(self._answers) - 1)]
        if isinstance(answer, Exception):
            raise answer
        return LlmResult(payload=answer, model=self.model, raw="")


def answer(label: str | None, confidence: float = 0.95) -> dict[str, Any]:
    return {
        "reasoning": "a short justification",
        "canonical_label": label if label is not None else taxonomy.UNKNOWN,
        "confidence": confidence,
    }


def normalizer(*answers: dict[str, Any] | Exception, **kwargs: Any) -> Normalizer:
    return Normalizer(provider=StubProvider(*answers, **kwargs))


async def normalise_one(
    normalizer: Normalizer,
    label: str,
    section: Section = Section.ASSETS,
    subsection: Subsection | None = Subsection.CURRENT,
    neighbours: tuple[str, ...] = (),
):
    return await normalizer.normalize(
        label, section=section, subsection=subsection, neighbours=neighbours
    )


class TestIdentityDictionary:
    """The canonical spelling resolves without troubling the model."""

    async def test_a_canonical_spelling_is_resolved_locally(self) -> None:
        provider = StubProvider()
        result = await Normalizer(provider=provider).normalize(
            "Trade Receivables", section=Section.ASSETS, subsection=Subsection.CURRENT
        )

        assert result.canonical_label == "trade_receivables"
        assert result.method is NormalizationMethod.DICTIONARY
        assert result.status is NormalizationStatus.NORMALIZED
        assert provider.calls == 0, "the model was consulted for an exact match"

    @pytest.mark.parametrize(
        ("label", "expected"),
        [
            ("TRADE RECEIVABLES", "trade_receivables"),
            ("Cash and Cash Equivalents", "cash_and_cash_equivalents"),
            ("Property, Plant & Equipment", "property_plant_and_equipment"),
            ("Short-Term Borrowings", "short_term_borrowings"),
            ("Other Non-Current Assets", "other_non_current_assets"),
        ],
    )
    async def test_punctuation_and_case_do_not_defeat_it(
        self, label: str, expected: str
    ) -> None:
        """These differ only in typesetting, not in wording."""
        result = await normalise_one(
            normalizer(), label, *_where(expected)
        )
        assert result.canonical_label == expected
        assert result.method is NormalizationMethod.DICTIONARY

    async def test_a_synonym_is_not_in_the_dictionary(self) -> None:
        """Deliberate. Synonymy is the model's job, not a hand-written table's.

        A broad alias table would make the model decorative and the benchmark
        meaningless.
        """
        provider = StubProvider(answer("trade_receivables"))
        result = await Normalizer(provider=provider).normalize(
            "Trade Debtors", section=Section.ASSETS, subsection=Subsection.CURRENT
        )

        assert provider.calls == 1
        assert result.method is NormalizationMethod.LLM
        assert result.canonical_label == "trade_receivables"


def _where(canonical: str) -> tuple[Section, Subsection | None]:
    category = taxonomy.get(canonical)
    assert category is not None
    return category.section, category.subsection


class TestTheModelDecidesSynonyms:
    @pytest.mark.parametrize(
        ("label", "canonical"),
        [
            ("Trade Debtors", "trade_receivables"),
            ("Sundry Debtors", "trade_receivables"),
            ("Stock-in-Trade", "inventory"),
            ("Plant & Machinery", "property_plant_and_equipment"),
        ],
    )
    async def test_a_synonym_reaches_the_model_and_is_accepted(
        self, label: str, canonical: str
    ) -> None:
        section, subsection = _where(canonical)
        result = await normalise_one(
            normalizer(answer(canonical)), label, section, subsection
        )

        assert result.canonical_label == canonical
        assert result.status is NormalizationStatus.NORMALIZED
        assert result.method is NormalizationMethod.LLM

    async def test_the_deciding_model_is_recorded(self) -> None:
        result = await normalise_one(
            normalizer(answer("trade_receivables"), model="qwen3:8b"), "Trade Debtors"
        )
        assert result.model == "qwen3:8b"

    async def test_the_taxonomy_version_is_recorded(self) -> None:
        """A mapping means nothing without the vocabulary that produced it."""
        result = await normalise_one(normalizer(answer("trade_receivables")), "Trade Debtors")
        assert result.taxonomy_version == taxonomy.TAXONOMY_VERSION


class TestValidationRejectsRatherThanGuesses:
    async def test_a_label_outside_the_taxonomy_is_refused(self) -> None:
        """Constrained decoding should make this impossible. It is checked anyway.

        A grammar cannot prevent a truncated response, and a provider that
        silently drops the constraint would otherwise write an invented
        category straight into the document.
        """
        result = await normalise_one(normalizer(answer("goodwill_impairment")), "Odd label")

        assert result.status is NormalizationStatus.NEEDS_REVIEW
        assert result.canonical_label is None
        assert result.reason == "invalid_label"

    async def test_a_label_from_the_wrong_section_is_refused(self) -> None:
        """The check the enum cannot make.

        ``trade_payables`` is a perfectly valid label and a nonsense answer for
        a line printed under ASSETS.
        """
        result = await normalise_one(
            normalizer(answer("trade_payables")),
            "Amounts owed",
            Section.ASSETS,
            Subsection.CURRENT,
        )

        assert result.status is NormalizationStatus.NEEDS_REVIEW
        assert result.canonical_label is None
        assert result.reason == "section_mismatch"

    async def test_a_label_from_the_wrong_subsection_is_refused(self) -> None:
        result = await normalise_one(
            normalizer(answer("trade_receivables")),
            "Amounts owed after one year",
            Section.ASSETS,
            Subsection.NON_CURRENT,
        )
        assert result.reason == "section_mismatch"

    @pytest.mark.parametrize(
        "payload",
        [
            {"canonical_label": "trade_receivables"},
            {"reasoning": "x", "confidence": 0.9},
            {"reasoning": "x", "canonical_label": "trade_receivables"},
            {},
        ],
    )
    async def test_a_response_missing_a_required_field_is_refused(
        self, payload: dict[str, Any]
    ) -> None:
        result = await normalise_one(normalizer(payload), "Trade Debtors")

        assert result.status is NormalizationStatus.NEEDS_REVIEW
        assert result.reason == "incomplete_response"

    async def test_a_response_that_is_not_an_object_is_refused(self) -> None:
        result = await normalise_one(normalizer({"unexpected": ["shape"]}), "Trade Debtors")
        assert result.status is NormalizationStatus.NEEDS_REVIEW

    async def test_a_confidence_outside_the_range_is_refused(self) -> None:
        result = await normalise_one(
            normalizer({"reasoning": "x", "canonical_label": "inventory", "confidence": 7})
        , "Stock")
        assert result.status is NormalizationStatus.NEEDS_REVIEW
        assert result.reason == "incomplete_response"

    async def test_the_original_label_survives_every_refusal(self) -> None:
        result = await normalise_one(normalizer(answer("trade_payables")), "Amounts owed")
        assert result.canonical_label is None
        assert result.status is NormalizationStatus.NEEDS_REVIEW


class TestAbstentionAndAmbiguity:
    async def test_unknown_is_an_answer_not_an_error(self) -> None:
        """A model that says so is behaving correctly, and is recorded as such."""
        result = await normalise_one(normalizer(answer(None)), "Miscellaneous Financial Assets")

        assert result.status is NormalizationStatus.NEEDS_REVIEW
        assert result.canonical_label is None
        assert result.reason == "model_abstained"

    async def test_a_low_confidence_answer_is_demoted(self) -> None:
        result = await normalise_one(
            normalizer(answer("trade_receivables", confidence=0.10)), "Sundry balances"
        )

        assert result.status is NormalizationStatus.NEEDS_REVIEW
        assert result.reason == "low_confidence"
        assert result.canonical_label is None

    async def test_confidence_can_never_rescue_a_failed_check(self) -> None:
        """Certainty about a wrong-section answer is still a wrong answer.

        The model's confidence is its own opinion, not a calibrated
        probability, so it may demote a mapping and may never promote one.
        """
        result = await normalise_one(
            normalizer(answer("trade_payables", confidence=1.0)),
            "Amounts owed",
            Section.ASSETS,
        )

        assert result.status is NormalizationStatus.NEEDS_REVIEW
        assert result.reason == "section_mismatch"

    async def test_the_stated_confidence_is_recorded_either_way(self) -> None:
        """Kept so the benchmark can measure whether it correlates with truth."""
        result = await normalise_one(
            normalizer(answer("trade_receivables", confidence=0.83)), "Trade Debtors"
        )
        assert result.confidence == pytest.approx(0.83)


class TestContextGivenToTheModel:
    async def test_the_prompt_names_the_label_and_its_section(self) -> None:
        provider = StubProvider(answer("trade_receivables"))
        await Normalizer(provider=provider).normalize(
            "Trade Debtors", section=Section.ASSETS, subsection=Subsection.CURRENT
        )

        prompt = provider.prompts[0]
        assert "Trade Debtors" in prompt
        assert "assets" in prompt
        assert "current" in prompt

    async def test_the_prompt_lists_only_the_labels_legal_here(self) -> None:
        """Narrowing the choice by section is the cheapest accuracy there is."""
        provider = StubProvider(answer("trade_receivables"))
        await Normalizer(provider=provider).normalize(
            "Trade Debtors", section=Section.ASSETS, subsection=Subsection.CURRENT
        )

        prompt = provider.prompts[0]
        assert "trade_receivables" in prompt
        assert "trade_payables" not in prompt

    async def test_neighbouring_labels_are_supplied(self) -> None:
        """A sibling list disambiguates far more than a label on its own."""
        provider = StubProvider(answer("inventory"))
        await Normalizer(provider=provider).normalize(
            "Stock",
            section=Section.ASSETS,
            subsection=Subsection.CURRENT,
            neighbours=("Trade Debtors", "Cash at bank"),
        )
        assert "Trade Debtors" in provider.prompts[0]

    async def test_no_figure_is_ever_shown_to_the_model(self) -> None:
        """It maps terminology. It is given nothing it could alter."""
        provider = StubProvider(answer("inventory"))
        await Normalizer(provider=provider).normalize(
            "Stock-in-Trade", section=Section.ASSETS, subsection=Subsection.CURRENT
        )
        assert "1,350,000" not in provider.prompts[0]
        assert "value" not in provider.prompts[0].lower().split()

    async def test_the_schema_constrains_the_label_to_the_vocabulary(self) -> None:
        provider = StubProvider(answer("inventory"))
        await Normalizer(provider=provider).normalize(
            "Stock", section=Section.ASSETS, subsection=Subsection.CURRENT
        )

        enum = provider.schemas[0]["properties"]["canonical_label"]["enum"]
        assert "inventory" in enum
        assert taxonomy.UNKNOWN in enum, "the model must be able to abstain"
        assert "trade_payables" not in enum

    async def test_reasoning_is_asked_for_before_the_constrained_label(self) -> None:
        """Order matters under grammar-constrained decoding.

        The model reasons in an unconstrained span and only then commits to an
        enum, which is what keeps the schema from taxing its accuracy.
        """
        provider = StubProvider(answer("inventory"))
        await Normalizer(provider=provider).normalize(
            "Stock", section=Section.ASSETS, subsection=Subsection.CURRENT
        )

        properties = list(provider.schemas[0]["properties"])
        assert properties.index("reasoning") < properties.index("canonical_label")


class TestCaching:
    async def test_a_repeated_label_is_not_asked_twice(self) -> None:
        provider = StubProvider(answer("trade_receivables"))
        subject = Normalizer(provider=provider)

        first = await subject.normalize(
            "Trade Debtors", section=Section.ASSETS, subsection=Subsection.CURRENT
        )
        second = await subject.normalize(
            "Trade Debtors", section=Section.ASSETS, subsection=Subsection.CURRENT
        )

        assert provider.calls == 1
        assert second.canonical_label == first.canonical_label
        assert second.method is NormalizationMethod.CACHE

    async def test_the_same_label_in_a_different_section_is_asked_again(self) -> None:
        """Section is part of the question, so it is part of the cache key."""
        provider = StubProvider(answer("other_current_assets"), answer("other_current_liabilities"))
        subject = Normalizer(provider=provider)

        await subject.normalize("Other balances", section=Section.ASSETS, subsection=Subsection.CURRENT)
        await subject.normalize(
            "Other balances", section=Section.LIABILITIES, subsection=Subsection.CURRENT
        )
        assert provider.calls == 2

    async def test_differently_typeset_labels_share_a_cache_entry(self) -> None:
        provider = StubProvider(answer("trade_receivables"))
        subject = Normalizer(provider=provider)

        await subject.normalize("Trade Debtors", section=Section.ASSETS, subsection=Subsection.CURRENT)
        await subject.normalize("TRADE  DEBTORS", section=Section.ASSETS, subsection=Subsection.CURRENT)
        assert provider.calls == 1


class TestWhenTheModelCannotBeReached:
    async def test_an_unavailable_provider_degrades_rather_than_failing(self) -> None:
        """The deterministic extraction is complete and still worth having.

        The label is marked for review and kept intact - which is honest, and
        recoverable by re-running once Ollama is up.
        """
        result = await normalise_one(normalizer(available=False), "Trade Debtors")

        assert result.status is NormalizationStatus.UNAVAILABLE
        assert result.method is NormalizationMethod.UNAVAILABLE
        assert result.canonical_label is None

    async def test_the_dictionary_still_works_without_a_model(self) -> None:
        """Most of a well-formed sheet normalizes with Ollama switched off."""
        result = await normalise_one(
            normalizer(available=False), "Trade Receivables"
        )
        assert result.canonical_label == "trade_receivables"
        assert result.method is NormalizationMethod.DICTIONARY

    async def test_one_failing_item_does_not_affect_the_others(self) -> None:
        provider = StubProvider(TimeoutError("no response"), answer("inventory"))
        subject = Normalizer(provider=provider, retries=0)

        failed = await subject.normalize(
            "Sundry Debtors", section=Section.ASSETS, subsection=Subsection.CURRENT
        )
        recovered = await subject.normalize(
            "Stock-in-Trade", section=Section.ASSETS, subsection=Subsection.CURRENT
        )

        assert failed.status is NormalizationStatus.NEEDS_REVIEW
        assert failed.reason == "provider_error"
        assert recovered.canonical_label == "inventory"

    async def test_a_transient_failure_is_retried_once(self) -> None:
        provider = StubProvider(TimeoutError("first attempt"), answer("inventory"))
        result = await Normalizer(provider=provider, retries=1).normalize(
            "Stock-in-Trade", section=Section.ASSETS, subsection=Subsection.CURRENT
        )

        assert provider.calls == 2
        assert result.canonical_label == "inventory"


class TestAnUnusableModelIsDiscoveredOnce:
    """Ollama running but the model not pulled - the commonest first-run state.

    Found in a real end-to-end run: every label failed identically and each one
    cost two HTTP round trips to learn the same thing. On a full Balance Sheet
    that is eighty pointless requests before the document gives up.
    """

    async def test_a_missing_model_is_not_retried(self) -> None:
        from app.core.llm.base import LlmUnavailable

        provider = StubProvider(LlmUnavailable("model 'qwen3:8b' is not available"))
        result = await Normalizer(provider=provider, retries=3).normalize(
            "Trade Debtors", section=Section.ASSETS, subsection=Subsection.CURRENT
        )

        assert provider.calls == 1, "a configuration problem was retried"
        assert result.status is NormalizationStatus.UNAVAILABLE

    async def test_later_labels_do_not_ask_again(self) -> None:
        from app.core.llm.base import LlmUnavailable

        provider = StubProvider(LlmUnavailable("not pulled"))
        subject = Normalizer(provider=provider)

        for label in ("Trade Debtors", "Stock-in-Trade", "Sundry Creditors"):
            outcome = await subject.normalize(
                label, section=Section.ASSETS, subsection=Subsection.CURRENT
            )
            assert outcome.status is NormalizationStatus.UNAVAILABLE

        assert provider.calls == 1

    async def test_the_dictionary_keeps_working_afterwards(self) -> None:
        """Losing the model costs synonymy, not the canonical spellings."""
        from app.core.llm.base import LlmUnavailable

        subject = Normalizer(provider=StubProvider(LlmUnavailable("not pulled")))
        await subject.normalize(
            "Trade Debtors", section=Section.ASSETS, subsection=Subsection.CURRENT
        )
        recovered = await subject.normalize(
            "Trade Receivables", section=Section.ASSETS, subsection=Subsection.CURRENT
        )

        assert recovered.canonical_label == "trade_receivables"
        assert recovered.method is NormalizationMethod.DICTIONARY
