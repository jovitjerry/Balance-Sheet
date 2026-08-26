"""The canonical vocabulary Module 2 maps onto.

Pure data and pure lookups - no parser, no cluster, no model.

Two properties matter more than the contents of the list. The vocabulary is
**closed**, because it is handed to a language model as the complete set of
permitted answers and an open set would let the model invent a category. And
every entry declares the section it can legally appear in, because that is the
check the model's own output cannot make for itself.
"""

from __future__ import annotations

import pytest

from app.modules.extraction import taxonomy
from app.modules.extraction.taxonomy import Section, Subsection


class TestVocabulary:
    def test_it_is_versioned(self) -> None:
        """A mapping is only reproducible if you know which vocabulary made it."""
        assert taxonomy.TAXONOMY_VERSION
        assert taxonomy.TAXONOMY_VERSION.count(".") == 2

    def test_labels_are_unique(self) -> None:
        labels = [category.label for category in taxonomy.CATEGORIES]
        assert len(labels) == len(set(labels))

    def test_labels_are_snake_case_identifiers(self) -> None:
        for label in taxonomy.labels():
            assert label.islower()
            assert label.replace("_", "").isalnum(), label

    def test_every_category_describes_itself(self) -> None:
        """The description is what the prompt shows the model.

        Keeping it on the category rather than in the prompt is what stops the
        vocabulary and its documentation drifting apart.
        """
        for category in taxonomy.CATEGORIES:
            assert category.description.strip()

    def test_unknown_is_not_a_category(self) -> None:
        """It is the model's way of abstaining, not somewhere to file a line."""
        assert taxonomy.UNKNOWN not in taxonomy.labels()
        assert taxonomy.get(taxonomy.UNKNOWN) is None

    @pytest.mark.parametrize(
        ("section", "subsection"),
        [
            (Section.ASSETS, Subsection.CURRENT),
            (Section.ASSETS, Subsection.NON_CURRENT),
            (Section.LIABILITIES, Subsection.CURRENT),
            (Section.LIABILITIES, Subsection.NON_CURRENT),
        ],
    )
    def test_every_group_has_a_residual_category(
        self, section: Section, subsection: Subsection
    ) -> None:
        """A real sheet prints "Other current assets" as its own line.

        That is a residual the document itself declared - quite different from
        a label we could not understand, which becomes needs_review instead.
        """
        labels = taxonomy.labels_for(section, subsection)
        assert any(label.startswith("other_") for label in labels), labels

    def test_equity_has_a_residual_category(self) -> None:
        assert any(
            label.startswith("other_") for label in taxonomy.labels_for(Section.EQUITY)
        )

    def test_the_ratios_module_3_needs_are_all_expressible(self) -> None:
        """The taxonomy is sized by what Module 3 will have to compute.

        Current and quick ratios need the current/non-current split and
        inventory; the debt ratios need borrowings separated from payables.
        Module 2 does not compute any of these - it must simply not make them
        impossible.
        """
        required = {
            "cash_and_cash_equivalents",
            "trade_receivables",
            "inventory",
            "trade_payables",
            "short_term_borrowings",
            "long_term_borrowings",
            "share_capital",
            "retained_earnings",
        }
        assert required <= set(taxonomy.labels())


class TestSectionConsistency:
    def test_every_category_names_a_real_section(self) -> None:
        for category in taxonomy.CATEGORIES:
            assert isinstance(category.section, Section)

    def test_asset_and_liability_categories_declare_a_subsection(self) -> None:
        """The current/non-current split is what the liquidity ratios rest on."""
        for category in taxonomy.CATEGORIES:
            if category.section in (Section.ASSETS, Section.LIABILITIES):
                assert category.subsection is not None, category.label

    def test_equity_categories_have_no_subsection(self) -> None:
        """Equity is not split into current and non-current on a Balance Sheet."""
        for category in taxonomy.CATEGORIES:
            if category.section is Section.EQUITY:
                assert category.subsection is None, category.label


class TestFits:
    """The check the enum constraint cannot make for the model."""

    def test_a_category_fits_its_own_section(self) -> None:
        assert taxonomy.fits("trade_receivables", Section.ASSETS, Subsection.CURRENT)

    def test_a_liability_category_does_not_fit_the_assets_section(self) -> None:
        """The failure this guard exists for.

        A model that answers `trade_payables` for a line printed under ASSETS
        has produced a structurally valid label and a wrong one.
        """
        assert not taxonomy.fits("trade_payables", Section.ASSETS, Subsection.CURRENT)

    def test_a_current_category_does_not_fit_a_non_current_line(self) -> None:
        assert not taxonomy.fits(
            "trade_receivables", Section.ASSETS, Subsection.NON_CURRENT
        )

    def test_an_unknown_subsection_checks_only_the_section(self) -> None:
        """Plenty of sheets print no current/non-current headings at all.

        Refusing every mapping on those documents would be wrong; the section
        is still known and is still checked.
        """
        assert taxonomy.fits("trade_receivables", Section.ASSETS, None)
        assert not taxonomy.fits("trade_payables", Section.ASSETS, None)

    def test_an_unrecognised_label_never_fits(self) -> None:
        assert not taxonomy.fits("goodwill_impairment", Section.ASSETS, None)
        assert not taxonomy.fits(taxonomy.UNKNOWN, Section.ASSETS, None)


class TestHeaders:
    """Section and subsection headings, as a Balance Sheet actually prints them."""

    @pytest.mark.parametrize(
        ("label", "section", "subsection"),
        [
            ("ASSETS", Section.ASSETS, None),
            ("Assets", Section.ASSETS, None),
            ("LIABILITIES", Section.LIABILITIES, None),
            ("EQUITY", Section.EQUITY, None),
            ("Shareholders' Equity", Section.EQUITY, None),
            ("Current Assets", Section.ASSETS, Subsection.CURRENT),
            ("CURRENT LIABILITIES", Section.LIABILITIES, Subsection.CURRENT),
            ("Non-Current Assets", Section.ASSETS, Subsection.NON_CURRENT),
            ("Non Current Liabilities", Section.LIABILITIES, Subsection.NON_CURRENT),
            ("Long-Term Liabilities", Section.LIABILITIES, Subsection.NON_CURRENT),
            ("Fixed Assets", Section.ASSETS, Subsection.NON_CURRENT),
        ],
    )
    def test_a_heading_sets_the_context_that_follows_it(
        self, label: str, section: Section, subsection: Subsection | None
    ) -> None:
        header = taxonomy.match_header(label)
        assert header is not None, label
        assert header.section is section
        assert header.subsection is subsection

    def test_a_combined_heading_commits_to_no_section(self) -> None:
        """Schedule III heads one block "EQUITY AND LIABILITIES".

        It announces both sections at once, so it cannot set either. The
        specific headings printed underneath it do that instead - and guessing
        here would file every equity line as a liability.
        """
        assert taxonomy.match_header("EQUITY AND LIABILITIES") is None
        assert taxonomy.match_header("Liabilities and Equity") is None

    @pytest.mark.parametrize(
        "label",
        [
            "Total Assets",
            "Cash and cash equivalents",
            "Trade receivables",
            "Assets pledged as security",
        ],
    )
    def test_a_line_that_merely_mentions_a_section_is_not_a_heading(
        self, label: str
    ) -> None:
        assert taxonomy.match_header(label) is None
