"""Every figure in an answer must trace back to one the model was shown.

This exists because of a measured failure, not a hypothetical one. On this
project's own Q&A benchmark, ``qwen3:8b`` summed current assets as 550,000
against a true 850,000 and concluded the company could not pay its short-term
bills - the exact opposite of the truth, stated fluently. Module 3 computes the
figures; this makes sure the model only repeats them.

The check has to be tolerant enough not to fire on honest restatement -
rounding, percentages, "2.3 million" - or it would refuse good answers and be
switched off, which is the usual fate of a noisy guard.
"""

from __future__ import annotations

from decimal import Decimal

from app.modules.insights.context import build_context
from app.modules.insights.routing import route
from app.modules.insights.structured import facts_for
from app.modules.insights.verification import (
    allowed_figures,
    extract_numbers,
    verify,
)
from tests.modules.insights.fixtures import analyzed_document


def _allowed() -> frozenset[Decimal]:
    facts = facts_for(analyzed_document(), decision=route("Tell me everything"))
    return allowed_figures(build_context(facts=facts, extracts=[]))


class TestExtraction:
    def test_it_finds_plain_and_grouped_figures(self) -> None:
        found = extract_numbers("Assets are 2,300,000 and inventory is 350000.")
        assert Decimal("2300000") in found
        assert Decimal("350000") in found

    def test_it_finds_decimals(self) -> None:
        assert Decimal("1.307692") in extract_numbers("The ratio is 1.307692.")

    def test_it_understands_indian_grouping(self) -> None:
        assert Decimal("2300000") in extract_numbers("Assets are 23,00,000.")

    def test_it_ignores_currency_symbols(self) -> None:
        for text in ("Rs 350,000", "INR 350,000", "350,000"):
            assert Decimal("350000") in extract_numbers(text)

    def test_a_parenthesised_figure_is_negative(self) -> None:
        assert Decimal("-2300") in extract_numbers("A contra balance of (2,300).")

    def test_scale_words_are_expanded(self) -> None:
        assert Decimal("2300000") in extract_numbers("Assets are 2.3 million.")

    def test_prose_with_no_figures_yields_none(self) -> None:
        assert extract_numbers("Inventory is valued at cost.") == set()


class TestTheBenchmarkFailure:
    """The case this module was built for."""

    def test_an_invented_sum_is_caught(self) -> None:
        answer = (
            "Current assets total 550,000 against current liabilities of "
            "650,000, so the company may struggle to pay its short-term bills."
        )
        result = verify(answer, figures_used=["550,000"], allowed=_allowed())

        assert not result.passed
        assert "550000" in result.unverified

    def test_the_true_figure_passes(self) -> None:
        answer = (
            "Current assets are 850000 against current liabilities of 650000, "
            "so short-term obligations are covered."
        )
        assert verify(answer, figures_used=[], allowed=_allowed()).passed


class TestHonestRestatementIsNotPunished:
    def test_a_rounded_ratio(self) -> None:
        """1.307692 quoted as 1.31, or as 1.3."""
        for text in ("The current ratio is 1.31.", "The current ratio is about 1.3."):
            assert verify(text, figures_used=[], allowed=_allowed()).passed, text

    def test_a_percentage_of_a_stored_ratio(self) -> None:
        """debt_ratio 0.586957 stated as 58.7%."""
        result = verify(
            "Creditors fund 58.7% of the asset base.",
            figures_used=[],
            allowed=_allowed(),
        )
        assert result.passed

    def test_a_figure_in_millions(self) -> None:
        assert verify(
            "Total assets are 2.3 million.", figures_used=[], allowed=_allowed()
        ).passed

    def test_indian_grouping_of_a_stored_figure(self) -> None:
        assert verify(
            "Total assets are 23,00,000.", figures_used=[], allowed=_allowed()
        ).passed

    def test_a_page_number_is_not_an_invented_figure(self) -> None:
        assert verify(
            "Inventory is 350000 (page 1).", figures_used=[], allowed=_allowed()
        ).passed

    def test_an_answer_with_no_figures_passes(self) -> None:
        result = verify(
            "The document does not state an accounting policy for inventory.",
            figures_used=[],
            allowed=_allowed(),
        )
        assert result.passed
        assert result.verified == ()


class TestFiguresUsedIsCheckedToo:
    def test_a_declared_figure_that_is_not_in_context_fails(self) -> None:
        """The model declares its own numbers; those are checked as well as the prose."""
        result = verify(
            "The position is comfortable.",
            figures_used=["999999"],
            allowed=_allowed(),
        )
        assert not result.passed
        assert "999999" in result.unverified

    def test_declared_figures_that_are_real_pass(self) -> None:
        assert verify(
            "Inventory is the largest current asset.",
            figures_used=["350000", "850000"],
            allowed=_allowed(),
        ).passed


class TestTheAllowedSet:
    def test_it_holds_every_figure_the_model_was_shown(self) -> None:
        allowed = _allowed()
        for value in ("2300000", "1350000", "950000", "350000", "1.307692"):
            assert Decimal(value) in allowed, value

    def test_it_includes_ratio_operands(self) -> None:
        """850000 appears only as the current ratio's numerator, and must count."""
        assert Decimal("850000") in _allowed()

    def test_it_includes_numbers_quoted_from_document_text(self) -> None:
        from app.core.schemas import Evidence, EvidenceKind

        extract = Evidence(
            id="C1",
            kind=EvidenceKind.TEXT,
            label="page 2",
            page_index=1,
            quote="Plant and machinery is depreciated over ten years from 2019.",
        )
        allowed = allowed_figures(build_context(facts=[], extracts=[extract]))
        assert Decimal("2019") in allowed

    def test_a_figure_absent_from_context_is_absent_from_the_set(self) -> None:
        assert Decimal("550000") not in _allowed()

    def test_conversation_history_is_not_evidence(self) -> None:
        """A wrong figure must not launder itself into fact by being repeated.

        History is shown to the model so it can resolve "is that good?" back to
        the ratio just named. It is not retrieved evidence, and admitting it
        here would let one bad answer poison every turn that followed.
        """
        facts = facts_for(analyzed_document(), decision=route("Tell me everything"))
        context = build_context(
            facts=facts,
            extracts=[],
            history=[("How much?", "Current assets are 550,000.")],
        )

        assert "550,000" in context.text  # the model can see it
        assert Decimal("550000") not in allowed_figures(context)  # but may not use it

    def test_the_groundable_text_excludes_only_history(self) -> None:
        facts = facts_for(analyzed_document(), decision=route("Tell me everything"))
        context = build_context(
            facts=facts, extracts=[], history=[("Q", "A")]
        )

        assert "AUTHORITATIVE FACTS" in context.groundable
        assert "EARLIER IN THIS CONVERSATION" not in context.groundable


class TestReporting:
    def test_it_names_what_it_verified_and_what_it_did_not(self) -> None:
        result = verify(
            "Inventory is 350000 but goodwill is 42424242.",
            figures_used=[],
            allowed=_allowed(),
        )
        assert "350000" in result.verified
        assert "42424242" in result.unverified
        assert not result.passed

    def test_the_correction_note_names_the_offending_figure(self) -> None:
        """The retry has to say what was wrong, or it is just a re-roll."""
        result = verify(
            "Current assets are 550,000.", figures_used=[], allowed=_allowed()
        )
        note = result.correction()

        assert "550000" in note
        assert "context" in note.lower()

    def test_a_passing_result_has_no_correction(self) -> None:
        assert verify("Inventory is 350000.", figures_used=[], allowed=_allowed()).correction() == ""


class TestDeterminism:
    def test_the_same_answer_verifies_the_same_way(self) -> None:
        allowed = _allowed()
        answer = "Current assets are 550,000 and inventory is 350000."
        assert verify(answer, figures_used=[], allowed=allowed) == verify(
            answer, figures_used=[], allowed=allowed
        )
