"""The anchor vocabulary and the label matching built on it.

Pure string logic - no parser, no cluster, no OCR binary.

The class that matters here is :class:`TestIsCombinedTotal`. The balancing
footer contains the literal text "total liabilities" by construction, so every
way of failing to recognise it fails in the same direction: liabilities get
inflated by the whole of equity and a sheet that balances perfectly is
rejected. Recognising it must therefore not depend on a hand-written list of
phrasings being complete.
"""

from __future__ import annotations

import pytest

from app.modules.ingestion import anchors


class TestSectionsNamed:
    @pytest.mark.parametrize(
        ("label", "expected"),
        [
            ("Total Assets", {"assets"}),
            ("Total Liabilities", {"liabilities"}),
            ("Total Equity", {"equity"}),
            ("Total Shareholders' Equity", {"equity"}),
            ("Total capital and reserves", {"equity"}),
            ("Total Liabilities and Net Worth", {"liabilities", "equity"}),
            ("TOTAL LIABILITIES + EQUITY", {"liabilities", "equity"}),
            ("Total Equity and Liabilities", {"liabilities", "equity"}),
            ("Cash and cash equivalents", set()),
        ],
    )
    def test_it_reports_which_sections_a_label_mentions(
        self, label: str, expected: set[str]
    ) -> None:
        assert anchors.sections_named(label) == expected


class TestIsCombinedTotal:
    @pytest.mark.parametrize(
        "label",
        [
            "TOTAL LIABILITIES + EQUITY",
            "Total Liabilities & Shareholders' Equity",
            "Total Liabilities + Shareholders\u2019 Equity",
            "Total Equity & Liabilities",
            "Total Liabilities and Net Worth",
            "Total Liabilities and Equity",
            "Total Liabilities and Shareholders' Equity",
            "Total Equity and Liabilities",
            "TOTAL EQUITY & LIABILITIES",
        ],
    )
    def test_a_footer_naming_two_sections_is_a_combined_total(self, label: str) -> None:
        assert anchors.is_combined_total(label) is True

    @pytest.mark.parametrize(
        "label",
        [
            "Total Assets",
            "Total Liabilities",
            "Total Equity",
            "Total Shareholders' Equity",
            "Total non-current liabilities",
            "Net worth",
        ],
    )
    def test_a_single_section_total_is_not(self, label: str) -> None:
        assert anchors.is_combined_total(label) is False

    def test_a_bare_section_heading_is_not_a_total_line(self) -> None:
        """Schedule III heads a block "EQUITY AND LIABILITIES".

        It names two sections but carries no figure and is not a total, so the
        combined-total test must gate on the word "total" as well.
        """
        assert anchors.is_combined_total("EQUITY AND LIABILITIES") is False

    def test_every_canonical_phrase_is_still_recognised(self) -> None:
        """The documented list must stay consistent with the structural rule."""
        for phrase in anchors.COMBINED_TOTAL_PHRASES:
            assert anchors.is_combined_total(phrase) is True, phrase
