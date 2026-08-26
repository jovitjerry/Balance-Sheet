"""Deterministic line-item extraction. No model is consulted here.

This is the half of Module 2 that answers "what did the document actually
say?". Terminology mapping is a separate step and a separate file; nothing
below needs Ollama, and nothing below is allowed to guess.

Documents are built through the real Module 1 parser, so these exercise what
the pipeline genuinely sees rather than a hand-made structure.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.config import Settings
from app.core.schemas import ExtractionStatus
from app.modules.extraction.extraction import extract_line_items
from app.modules.extraction.taxonomy import Section, Subsection
from app.modules.ingestion.identification import select_period
from app.modules.ingestion.parsing import parse
from app.modules.ingestion.validation import UploadKind
from tests.modules.ingestion.fixtures import (
    Text,
    comparative_balance_sheet_pdf,
    make_text_pdf,
    make_xlsx,
    side_by_side_balance_sheet_pdf,
    simple_balance_sheet_pdf,
    simple_balance_sheet_xlsx,
)
from tests.modules.ingestion.test_parsing import PDF_SOURCE, XLSX_SOURCE


async def lines_from_pdf(data: bytes, settings: Settings, *, with_period: bool = True):
    preliminary = await parse(data, PDF_SOURCE, settings=settings)
    period = select_period(preliminary) if with_period else None
    return extract_line_items(preliminary, period=period)


async def lines_from_xlsx(data: bytes, settings: Settings):
    preliminary = await parse(data, XLSX_SOURCE, kind=UploadKind.XLSX, settings=settings)
    return extract_line_items(preliminary, period=select_period(preliminary))


def by_label(items) -> dict[str, object]:
    return {item.label: item for item in items}


def text_pdf(rows: list[tuple[str, str | None]]) -> bytes:
    runs: list[Text] = []
    y = 740.0
    for label, value in rows:
        runs.append(Text(72, y, label))
        if value is not None:
            runs.append(Text(420, y, value))
        y -= 18.0
    return make_text_pdf([runs])


class TestLineItems:
    async def test_it_extracts_every_line_item(self, settings: Settings) -> None:
        items = by_label(await lines_from_pdf(simple_balance_sheet_pdf(), settings))

        assert set(items) == {
            "Cash and cash equivalents",
            "Inventories",
            "Property, plant and equipment",
            "Trade payables",
            "Long-term borrowings",
            "Share capital",
            "Retained earnings",
        }

    async def test_values_are_decimal(self, settings: Settings) -> None:
        items = by_label(await lines_from_pdf(simple_balance_sheet_pdf(), settings))

        assert items["Cash and cash equivalents"].value == Decimal("40000")
        assert isinstance(items["Cash and cash equivalents"].value, Decimal)

    async def test_the_printed_figure_is_kept_beside_the_parsed_one(
        self, settings: Settings
    ) -> None:
        items = by_label(await lines_from_pdf(simple_balance_sheet_pdf(), settings))
        assert items["Cash and cash equivalents"].raw == "40,000"

    async def test_the_original_label_is_kept_exactly_as_printed(
        self, settings: Settings
    ) -> None:
        """Punctuation and case are evidence, not noise."""
        items = by_label(await lines_from_pdf(simple_balance_sheet_pdf(), settings))
        assert "Property, plant and equipment" in items

    async def test_every_item_records_where_it_came_from(
        self, settings: Settings
    ) -> None:
        for item in await lines_from_pdf(simple_balance_sheet_pdf(), settings):
            assert item.source.page_index == 0
            assert item.source.row is not None

    async def test_a_workbook_item_records_its_sheet(self, settings: Settings) -> None:
        items = by_label(await lines_from_xlsx(simple_balance_sheet_xlsx(), settings))
        assert items["Share capital"].source.sheet_name == "Balance Sheet"

    async def test_a_negative_figure_keeps_its_sign(self, settings: Settings) -> None:
        pdf = text_pdf(
            [
                ("Balance Sheet as at 31 March 2024", None),
                ("EQUITY", None),
                ("Accumulated losses", "(20,000)"),
            ]
        )
        items = by_label(await lines_from_pdf(pdf, settings))
        assert items["Accumulated losses"].value == Decimal("-20000")
        assert items["Accumulated losses"].raw == "(20,000)"


class TestTotalsAreNotLineItems:
    """A total is a summary of the lines, not one of them.

    Including it would double every section and make the reconciliation
    between line items and Module 1's total meaningless.
    """

    @pytest.mark.parametrize(
        "total_label",
        ["Total Assets", "Total Liabilities", "Total Shareholders' Equity"],
    )
    async def test_a_section_total_is_excluded(
        self, total_label: str, settings: Settings
    ) -> None:
        items = by_label(await lines_from_pdf(simple_balance_sheet_pdf(), settings))
        assert total_label not in items

    async def test_a_subtotal_is_excluded_too(self, settings: Settings) -> None:
        """Module 1 never located these, so only Module 2 can leave them out."""
        items = by_label(await lines_from_pdf(side_by_side_balance_sheet_pdf(), settings))

        assert "Total Current Liabilities" not in items
        assert "Total Current Assets" not in items
        assert "Total Non-Current Assets" not in items

    async def test_the_balancing_footer_is_excluded(self, settings: Settings) -> None:
        items = by_label(await lines_from_pdf(side_by_side_balance_sheet_pdf(), settings))
        assert "TOTAL LIABILITIES + EQUITY" not in items

    async def test_a_label_merely_starting_with_those_letters_is_kept(
        self, settings: Settings
    ) -> None:
        """"Totalisator" is not a total. The rule is a word, not a prefix."""
        pdf = text_pdf(
            [
                ("Balance Sheet as at 31 March 2024", None),
                ("ASSETS", None),
                ("Totalisator receipts receivable", "5,000"),
            ]
        )
        items = by_label(await lines_from_pdf(pdf, settings))
        assert "Totalisator receipts receivable" in items


class TestSectionContext:
    async def test_items_inherit_the_section_heading_above_them(
        self, settings: Settings
    ) -> None:
        items = by_label(await lines_from_pdf(simple_balance_sheet_pdf(), settings))

        assert items["Cash and cash equivalents"].section is Section.ASSETS
        assert items["Trade payables"].section is Section.LIABILITIES
        assert items["Share capital"].section is Section.EQUITY

    async def test_a_subsection_heading_narrows_the_context(
        self, settings: Settings
    ) -> None:
        items = by_label(await lines_from_pdf(side_by_side_balance_sheet_pdf(), settings))

        assert items["Cash and cash equivalents"].subsection is Subsection.CURRENT
        assert items["Intangible assets"].subsection is Subsection.NON_CURRENT
        assert items["Trade payables"].subsection is Subsection.CURRENT
        assert items["Long-term borrowings"].subsection is Subsection.NON_CURRENT

    async def test_a_sheet_without_the_split_leaves_the_subsection_unknown(
        self, settings: Settings
    ) -> None:
        """Ordinary, and not an error. Guessing here would be the error."""
        items = by_label(await lines_from_pdf(simple_balance_sheet_pdf(), settings))
        assert items["Cash and cash equivalents"].subsection is None

    async def test_lines_above_the_first_heading_are_not_line_items(
        self, settings: Settings
    ) -> None:
        """The entity name and the title belong to no section."""
        items = by_label(await lines_from_pdf(simple_balance_sheet_pdf(), settings))

        assert "Acme Manufacturing Limited" not in items
        assert "Balance Sheet as at 31 March 2024" not in items


class TestSideBySideLayout:
    """The horizontal layout, where a row carries two unrelated labels."""

    async def test_items_in_the_right_hand_column_are_extracted(
        self, settings: Settings
    ) -> None:
        items = by_label(await lines_from_pdf(side_by_side_balance_sheet_pdf(), settings))

        assert items["Trade payables"].value == Decimal("300000")
        assert items["Short-term borrowings"].value == Decimal("200000")
        assert items["Share capital"].value == Decimal("600000")

    async def test_each_label_takes_the_figure_beside_it(
        self, settings: Settings
    ) -> None:
        """``Intangible assets 150,000`` shares a row with ``Total Liabilities``."""
        items = by_label(await lines_from_pdf(side_by_side_balance_sheet_pdf(), settings))
        assert items["Intangible assets"].value == Decimal("150000")

    async def test_the_right_hand_column_gets_its_own_section(
        self, settings: Settings
    ) -> None:
        """Its heading sits in the right-hand column too, on the ASSETS row."""
        items = by_label(await lines_from_pdf(side_by_side_balance_sheet_pdf(), settings))

        assert items["Cash and cash equivalents"].section is Section.ASSETS
        assert items["Trade payables"].section is Section.LIABILITIES
        assert items["Retained earnings"].section is Section.EQUITY


class TestSinglePeriodScope:
    """A comparative sheet has two columns of plausible numbers.

    Extracting the wrong one produces a Balance Sheet that is entirely
    self-consistent and describes the wrong year.
    """

    async def test_only_the_selected_period_is_extracted(
        self, settings: Settings
    ) -> None:
        items = by_label(await lines_from_pdf(comparative_balance_sheet_pdf(), settings))

        assert items["Cash and cash equivalents"].value == Decimal("40000")
        assert items["Property, plant and equipment"].value == Decimal("110000")

    async def test_no_prior_period_figure_appears_anywhere(
        self, settings: Settings
    ) -> None:
        items = await lines_from_pdf(comparative_balance_sheet_pdf(), settings)
        values = {item.value for item in items}

        for prior in (Decimal("35000"), Decimal("85000"), Decimal("70000")):
            assert prior not in values, f"{prior} is the 2023 column"

    async def test_one_item_is_produced_per_label_not_one_per_column(
        self, settings: Settings
    ) -> None:
        items = await lines_from_pdf(comparative_balance_sheet_pdf(), settings)
        labels = [item.label for item in items]
        assert len(labels) == len(set(labels))


class TestUnreadableFigures:
    async def test_a_line_whose_figure_will_not_parse_is_kept(
        self, settings: Settings
    ) -> None:
        """Dropping it would silently shrink the Balance Sheet.

        A line nobody can read is precisely the one a reviewer needs to see, so
        it is recorded with no value and said to be unparsed.
        """
        pdf = text_pdf(
            [
                ("Balance Sheet as at 31 March 2024", None),
                ("ASSETS", None),
                ("Cash and cash equivalents", "40,000"),
                ("Deferred charges", "see note 4"),
            ]
        )
        items = by_label(await lines_from_pdf(pdf, settings))

        assert "Deferred charges" in items
        assert items["Deferred charges"].value is None
        assert items["Deferred charges"].status is ExtractionStatus.UNPARSED_VALUE
        assert items["Deferred charges"].raw == "see note 4"

    async def test_a_readable_line_is_marked_extracted(self, settings: Settings) -> None:
        items = by_label(await lines_from_pdf(simple_balance_sheet_pdf(), settings))
        assert items["Share capital"].status is ExtractionStatus.EXTRACTED

    async def test_a_dash_is_nil_not_unreadable(self, settings: Settings) -> None:
        """Accountants write a dash where the figure is zero."""
        pdf = text_pdf(
            [
                ("Balance Sheet as at 31 March 2024", None),
                ("ASSETS", None),
                ("Short-term investments", "-"),
            ]
        )
        items = by_label(await lines_from_pdf(pdf, settings))
        assert items["Short-term investments"].value == Decimal(0)
        assert items["Short-term investments"].status is ExtractionStatus.EXTRACTED


class TestWorkbooks:
    async def test_a_workbook_yields_the_same_items_as_the_pdf(
        self, settings: Settings
    ) -> None:
        """Same content, different container. The result should not differ."""
        from_pdf = by_label(await lines_from_pdf(simple_balance_sheet_pdf(), settings))
        from_xlsx = by_label(await lines_from_xlsx(simple_balance_sheet_xlsx(), settings))

        assert set(from_pdf) == set(from_xlsx)
        assert from_pdf["Inventories"].value == from_xlsx["Inventories"].value

    async def test_a_heading_row_is_not_an_item(self, settings: Settings) -> None:
        workbook = make_xlsx(
            {
                "BS": [
                    ["Balance Sheet"],
                    ["ASSETS", None],
                    ["Cash", "100"],
                ]
            }
        )
        items = by_label(await lines_from_xlsx(workbook, settings))
        assert "ASSETS" not in items
        assert "Cash" in items


class TestTheStatementEndsAtTheBalancingFooter:
    """A balancing footer restates one whole side against the other.

    Nothing after it is part of the Balance Sheet. Real filings print notes,
    reconciliations and signature blocks below it, and their figures are not
    line items - but they sit under the last heading seen and would otherwise
    inherit it.
    """

    async def test_figures_printed_after_the_footer_are_not_line_items(
        self, settings: Settings
    ) -> None:
        pdf = text_pdf(
            [
                ("Balance Sheet as at 31 March 2024", None),
                ("ASSETS", None),
                ("Cash and cash equivalents", "40,000"),
                ("Total Assets", "40,000"),
                ("LIABILITIES", None),
                ("Trade payables", "15,000"),
                ("EQUITY", None),
                ("Share capital", "25,000"),
                ("Total Liabilities and Equity", "40,000"),
                ("Accounting Equation Check", None),
                ("Difference", "0"),
            ]
        )
        items = by_label(await lines_from_pdf(pdf, settings))

        assert "Difference" not in items
        assert set(items) == {
            "Cash and cash equivalents",
            "Trade payables",
            "Share capital",
        }

    async def test_a_later_statement_can_still_open_its_own_sections(
        self, settings: Settings
    ) -> None:
        """Ending the statement forgets the headings; it does not stop reading."""
        pdf = text_pdf(
            [
                ("Balance Sheet as at 31 March 2024", None),
                ("ASSETS", None),
                ("Cash and cash equivalents", "40,000"),
                ("Total Liabilities and Equity", "40,000"),
                ("ASSETS", None),
                ("Trade receivables", "10,000"),
            ]
        )
        items = by_label(await lines_from_pdf(pdf, settings))

        assert items["Trade receivables"].section is Section.ASSETS
