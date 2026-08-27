"""Deciding where a question should be answered from, without asking a model.

Routing is rules, not a classifier. Two reasons: a generation round-trip costs
~4 s warm to decide something rules get right on a closed question space, and a
model would make routing non-deterministic - so the same question could route
differently between runs, in a project whose whole point is reproducibility.

The asymmetry that shapes every rule here: **structured retrieval is free** - a
dictionary lookup on an already-loaded document - so a false positive costs
nothing. Only wrongly *skipping* the vector query has a real cost, so the rules
bias towards running it.
"""

from __future__ import annotations

from app.core.schemas import RetrievalRoute
from app.modules.insights.routing import route


class TestPureLookupsSkipTheVectorQuery:
    """A named concept with no narrative wording needs no semantic search."""

    def test_a_line_item_lookup(self) -> None:
        assert route("How much inventory does the company have?").route is (
            RetrievalRoute.STRUCTURED
        )

    def test_a_ratio_lookup(self) -> None:
        assert route("What is the current ratio?").route is RetrievalRoute.STRUCTURED

    def test_a_total_lookup(self) -> None:
        assert route("What are the total assets?").route is RetrievalRoute.STRUCTURED

    def test_a_comparison_between_two_stored_figures(self) -> None:
        decision = route("Which is larger, short-term or long-term borrowing?")
        assert decision.route is RetrievalRoute.STRUCTURED
        assert "short_term_borrowings" in decision.matched_concepts
        assert "long_term_borrowings" in decision.matched_concepts

    def test_a_supplier_question_reaches_trade_payables(self) -> None:
        """'Owes suppliers' is the taxonomy's own description of trade payables."""
        decision = route("How much does it owe suppliers?")
        assert "trade_payables" in decision.matched_concepts


class TestNarrativeQuestionsReachTheText:
    def test_an_accounting_policy_question(self) -> None:
        decision = route("What accounting policy is used for fixed assets?")
        assert decision.route in (RetrievalRoute.TEXT, RetrievalRoute.BOTH)
        assert "policy" in decision.matched_narrative

    def test_a_note_question(self) -> None:
        assert route("What does the note say about depreciation?").route in (
            RetrievalRoute.TEXT,
            RetrievalRoute.BOTH,
        )

    def test_a_description_question(self) -> None:
        assert route("How does the company describe its receivables?").route is (
            RetrievalRoute.BOTH
        )

    def test_a_valuation_basis_question(self) -> None:
        assert route("On what basis is inventory valued?").route is RetrievalRoute.BOTH


class TestInterpretiveQuestionsUseBoth:
    """'Why' needs the figures and whatever the document says about them."""

    def test_why(self) -> None:
        assert route("Why might the high PPE balance matter?").route is (
            RetrievalRoute.BOTH
        )

    def test_is_that_good(self) -> None:
        assert route("Is the current ratio good?").route is RetrievalRoute.BOTH

    def test_explain(self) -> None:
        assert route("Explain what retained earnings means here.").route is (
            RetrievalRoute.BOTH
        )


class TestOutOfScope:
    """A Balance Sheet structurally cannot report these. Knowable without a model."""

    def test_net_profit(self) -> None:
        decision = route("What is the net profit for the year?")
        assert decision.route is RetrievalRoute.OUT_OF_SCOPE
        assert decision.out_of_scope_terms

    def test_revenue(self) -> None:
        assert route("What was the revenue?").route is RetrievalRoute.OUT_OF_SCOPE

    def test_year_over_year_growth(self) -> None:
        """Single-period scope: there is no prior year to compare against."""
        assert route("How did revenue change compared with last year?").route is (
            RetrievalRoute.OUT_OF_SCOPE
        )

    def test_a_forecast(self) -> None:
        assert route("What is next year's expected revenue?").route is (
            RetrievalRoute.OUT_OF_SCOPE
        )

    def test_cash_flow(self) -> None:
        assert route("What was the operating cash flow?").route is (
            RetrievalRoute.OUT_OF_SCOPE
        )

    def test_a_ratio_needing_an_income_statement(self) -> None:
        assert route("What is the interest coverage ratio?").route is (
            RetrievalRoute.OUT_OF_SCOPE
        )


class TestInvestmentAdviceIsRefusedDeterministically:
    """Asking for a recommendation must never reach a model.

    Found by the Module 4 reasoning benchmark: "should I invest in this
    company?" routed to BOTH, reached the model, and two of four candidates
    answered with an avoid recommendation - one of them justifying it with the
    quick ratio. A single-period Balance Sheet supports no investment decision,
    and that is knowable without asking a model, so it is refused here rather
    than left to prompt wording to discourage.

    Unlike the other out-of-scope terms, advice is refused **unconditionally**.
    A missing figure can be worked around when the question also names something
    answerable; a recommendation cannot be half-given.
    """

    def test_the_benchmark_question(self) -> None:
        decision = route("Based on this, should I invest in this company?")
        assert decision.route is RetrievalRoute.OUT_OF_SCOPE
        assert decision.asks_for_advice

    def test_variants(self) -> None:
        for question in (
            "Should I buy shares in this company?",
            "Should I sell my holding?",
            "Is this a good investment?",
            "Would you recommend investing here?",
            "Do you recommend buying?",
            "Is it worth investing in this business?",
            "Should we invest in them?",
            "What is your investment advice?",
            "Should I avoid this company?",
        ):
            assert route(question).route is RetrievalRoute.OUT_OF_SCOPE, question

    def test_advice_is_refused_even_when_the_question_names_a_real_concept(
        self,
    ) -> None:
        """A recommendation cannot be half-given, so a concept match must not
        rescue it the way it rescues a mixed factual question."""
        decision = route("Given inventory of 350,000, should I invest?")
        assert decision.route is RetrievalRoute.OUT_OF_SCOPE
        assert decision.asks_for_advice


class TestQuestionsAboutInvestmentsAreNotAdvice:
    """`long_term_investments` and `short_term_investments` are real categories.

    The refusal must key on asking for a recommendation, not on the word
    "invest" - otherwise every question about the investments a company holds
    would be refused, which is a worse failure than the one being fixed.
    """

    def test_asking_about_held_investments_still_routes_to_the_figures(self) -> None:
        for question in (
            "How much is held in long-term investments?",
            "What are the short-term investments worth?",
            "How much has the company invested in subsidiaries?",
        ):
            decision = route(question)
            assert decision.route is not RetrievalRoute.OUT_OF_SCOPE, question
            assert not decision.asks_for_advice, question

    def test_the_investment_categories_are_still_matched(self) -> None:
        decision = route("How much is held in long-term investments?")
        assert "long_term_investments" in decision.matched_concepts


class TestConceptsThatOnlyLookOutOfScope:
    """The traps. Each of these IS on a Balance Sheet and must not be refused."""

    def test_retained_earnings_is_not_an_earnings_question(self) -> None:
        """'Earnings per share' is out of scope; retained earnings is equity."""
        decision = route("How much is in retained earnings?")
        assert decision.route is not RetrievalRoute.OUT_OF_SCOPE
        assert "retained_earnings" in decision.matched_concepts

    def test_accumulated_depreciation_is_not_a_depreciation_expense_question(
        self,
    ) -> None:
        assert route("What is the accumulated depreciation?").route is not (
            RetrievalRoute.OUT_OF_SCOPE
        )

    def test_a_depreciation_policy_question_is_a_notes_question(self) -> None:
        """Policy prose lives in the notes - retrievable, and not out of scope."""
        assert route("What is the depreciation policy?").route in (
            RetrievalRoute.TEXT,
            RetrievalRoute.BOTH,
        )

    def test_cash_is_not_cash_flow(self) -> None:
        decision = route("How much cash is there?")
        assert decision.route is RetrievalRoute.STRUCTURED
        assert "cash_and_cash_equivalents" in decision.matched_concepts

    def test_a_named_concept_beats_an_out_of_scope_word(self) -> None:
        """A mixed question still answers the answerable half.

        The out-of-scope term is recorded so the prompt can say what it could
        not cover, rather than the whole question being refused.
        """
        decision = route("What was the profit, and how much inventory is there?")
        assert decision.route is not RetrievalRoute.OUT_OF_SCOPE
        assert "inventory" in decision.matched_concepts
        assert decision.out_of_scope_terms


class TestTheDefaultIsSafe:
    def test_an_unrecognised_question_still_searches_the_text(self) -> None:
        """Missing a notes answer is worse than one cheap vector query."""
        assert route("What can you tell me about this company?").route is (
            RetrievalRoute.BOTH
        )

    def test_an_empty_question_does_not_crash(self) -> None:
        assert route("   ").route is RetrievalRoute.BOTH


class TestVocabularyIsDerivedNotHandWritten:
    """Module 4 holds no financial synonym list. Module 2 owns terminology."""

    def test_every_matched_concept_is_a_real_canonical_label_or_ratio(self) -> None:
        from app.modules.extraction import taxonomy
        from app.modules.ratios import definitions

        known = set(taxonomy.labels()) | set(definitions.names())
        questions = [
            "How much inventory is there?",
            "What is the current ratio?",
            "How much does it owe suppliers?",
            "What is the working capital?",
            "How much cash and cash equivalents?",
        ]
        for question in questions:
            for concept in route(question).matched_concepts:
                assert concept in known, f"{concept!r} is not a canonical label or ratio"

    def test_a_label_printed_on_this_document_is_recognised(self) -> None:
        """Wording peculiar to one filing routes without a synonym table."""
        from tests.modules.insights.fixtures import analyzed_document

        document = analyzed_document(labels={"assets": [("Sundry Debtors", "280000")]})
        decision = route("How much is in sundry debtors?", document=document)
        assert decision.route is RetrievalRoute.STRUCTURED
        assert "Sundry Debtors" in decision.matched_labels


class TestDeterminism:
    def test_the_same_question_always_routes_the_same_way(self) -> None:
        question = "Why might the high PPE balance matter?"
        first, second = route(question), route(question)
        assert first == second

    def test_routing_calls_no_model(self) -> None:
        """Enforced by signature: there is nowhere to pass a provider."""
        import inspect

        parameters = set(inspect.signature(route).parameters)
        assert parameters == {"question", "document"}
