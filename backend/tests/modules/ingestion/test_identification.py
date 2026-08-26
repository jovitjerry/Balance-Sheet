"""Module 1 identification: is this a Balance Sheet, and where are its totals?

Pure - no cluster, no OCR binary. Documents are built through the real parser
so these exercise what the pipeline actually sees.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.config import Settings
from app.modules.ingestion.identification import (
    _total_kind,
    detect_units,
    is_balance_sheet,
    locate_totals,
    select_period,
)
from app.modules.ingestion.parsing import parse
from app.modules.ingestion.validation import UploadKind
from tests.modules.ingestion.fixtures import (
    Text,
    comparative_balance_sheet_pdf,
    footer_balance_sheet_pdf,
    side_by_side_balance_sheet_pdf,
    make_text_pdf,
    make_xlsx,
    simple_balance_sheet_pdf,
    simple_balance_sheet_xlsx,
)
from tests.modules.ingestion.test_parsing import PDF_SOURCE, XLSX_SOURCE


async def parsed_pdf(data: bytes, settings: Settings):
    return await parse(data, PDF_SOURCE, settings=settings)


async def parsed_xlsx(data: bytes, settings: Settings):
    return await parse(data, XLSX_SOURCE, kind=UploadKind.XLSX, settings=settings)


def text_pdf(lines: list[tuple[str, str | None]]) -> bytes:
    runs: list[Text] = []
    y = 740.0
    for label, value in lines:
        runs.append(Text(72, y, label))
        if value is not None:
            runs.append(Text(420, y, value))
        y -= 18.0
    return make_text_pdf([runs])


class TestIsBalanceSheet:
    async def test_a_balance_sheet_pdf_is_recognised(self, settings: Settings) -> None:
        evidence = is_balance_sheet(await parsed_pdf(simple_balance_sheet_pdf(), settings))

        assert evidence.is_balance_sheet is True
        assert evidence.score >= evidence.threshold

    async def test_a_balance_sheet_workbook_is_recognised(
        self, settings: Settings
    ) -> None:
        evidence = is_balance_sheet(
            await parsed_xlsx(simple_balance_sheet_xlsx(), settings)
        )
        assert evidence.is_balance_sheet is True

    async def test_the_reasoning_is_recorded_not_just_the_verdict(
        self, settings: Settings
    ) -> None:
        """A rejection nobody can argue with is not auditable."""
        evidence = is_balance_sheet(await parsed_pdf(simple_balance_sheet_pdf(), settings))

        kinds = {signal.kind for signal in evidence.signals}
        assert "title" in kinds
        assert "total_line" in kinds
        assert all(signal.source.page_index == 0 for signal in evidence.signals)

    async def test_statement_of_financial_position_counts_as_a_title(
        self, settings: Settings
    ) -> None:
        """The IFRS name for the same statement."""
        pdf = text_pdf(
            [
                ("Statement of Financial Position as at 31 March 2024", None),
                ("Total Assets", "150,000"),
                ("Total Liabilities", "90,000"),
                ("Total Equity", "60,000"),
            ]
        )
        assert is_balance_sheet(await parsed_pdf(pdf, settings)).is_balance_sheet is True

    async def test_an_income_statement_is_not_a_balance_sheet(
        self, settings: Settings
    ) -> None:
        pdf = text_pdf(
            [
                ("Statement of Profit and Loss for the year ended 31 March 2024", None),
                ("Revenue from operations", "500,000"),
                ("Cost of materials consumed", "300,000"),
                ("Profit before tax", "80,000"),
                ("Total expenses for the period", "420,000"),
            ]
        )
        evidence = is_balance_sheet(await parsed_pdf(pdf, settings))

        assert evidence.is_balance_sheet is False
        assert evidence.score < evidence.threshold

    async def test_an_unrelated_document_is_not_a_balance_sheet(
        self, settings: Settings
    ) -> None:
        pdf = text_pdf(
            [
                ("Minutes of the Annual General Meeting held on 12 August 2024", None),
                ("The Chairman welcomed the members present at the meeting", None),
                ("Resolutions were passed unanimously by a show of hands", None),
            ]
        )
        assert is_balance_sheet(await parsed_pdf(pdf, settings)).is_balance_sheet is False

    async def test_an_annual_report_is_not_disqualified_by_its_other_statements(
        self, settings: Settings
    ) -> None:
        """A Balance Sheet does not stop being one because a Cash Flow Statement
        is printed three pages later. The penalty applies only when no Balance
        Sheet title was found at all.
        """
        pdf = make_text_pdf(
            [
                [Text(72, 700, "Cash Flow Statement for the year ended 31 March 2024")],
                [
                    Text(72, 740, "Balance Sheet as at 31 March 2024"),
                    Text(72, 700, "Total Assets"),
                    Text(420, 700, "150,000"),
                    Text(72, 680, "Total Liabilities"),
                    Text(420, 680, "90,000"),
                    Text(72, 660, "Total Equity"),
                    Text(420, 660, "60,000"),
                ],
            ]
        )
        assert is_balance_sheet(await parsed_pdf(pdf, settings)).is_balance_sheet is True

    async def test_a_typographic_apostrophe_does_not_break_matching(
        self, settings: Settings
    ) -> None:
        """A PDF's font encoding renders ' as U+2019.

        ``SHAREHOLDERS' EQUITY`` comes back as ``SHAREHOLDERS’ EQUITY``, and a
        literal comparison would fail on a perfectly ordinary document.
        """
        pdf = text_pdf(
            [
                ("Balance Sheet", None),
                ("Total Assets", "150,000"),
                ("Total Liabilities", "90,000"),
                ("Total Shareholders’ Equity", "60,000"),
            ]
        )
        totals = locate_totals(await parsed_pdf(pdf, settings))
        assert totals.equity is not None
        assert totals.equity.value == Decimal("60000")


class TestLocateTotals:
    async def test_it_finds_all_three_totals(self, settings: Settings) -> None:
        totals = locate_totals(await parsed_pdf(simple_balance_sheet_pdf(), settings))

        assert totals.complete
        assert totals.assets.value == Decimal("150000")
        assert totals.liabilities.value == Decimal("90000")
        assert totals.equity.value == Decimal("60000")

    async def test_it_finds_totals_in_a_workbook(self, settings: Settings) -> None:
        totals = locate_totals(await parsed_xlsx(simple_balance_sheet_xlsx(), settings))

        assert totals.complete
        assert totals.assets.value == Decimal("150000")

    async def test_the_printed_form_is_kept_beside_the_parsed_value(
        self, settings: Settings
    ) -> None:
        totals = locate_totals(await parsed_pdf(simple_balance_sheet_pdf(), settings))

        assert totals.assets.raw == "150,000"
        assert totals.assets.value == Decimal("150000")
        assert totals.assets.label.startswith("Total Assets")

    async def test_each_total_records_where_it_came_from(
        self, settings: Settings
    ) -> None:
        totals = locate_totals(await parsed_pdf(simple_balance_sheet_pdf(), settings))
        assert totals.assets.source.page_index == 0
        assert totals.assets.source.row is not None

    async def test_a_workbook_total_records_its_sheet(self, settings: Settings) -> None:
        totals = locate_totals(await parsed_xlsx(simple_balance_sheet_xlsx(), settings))
        assert totals.assets.source.sheet_name == "Balance Sheet"

    async def test_a_missing_total_is_reported_not_invented(
        self, settings: Settings
    ) -> None:
        pdf = text_pdf(
            [
                ("Balance Sheet as at 31 March 2024", None),
                ("Total Assets", "150,000"),
                ("Total Liabilities", "90,000"),
            ]
        )
        totals = locate_totals(await parsed_pdf(pdf, settings))

        assert totals.complete is False
        assert totals.missing == ["equity"]
        assert totals.equity is None

    async def test_the_balancing_footer_is_not_read_as_total_liabilities(
        self, settings: Settings
    ) -> None:
        """The trap this module exists to avoid.

        "Total Liabilities and Shareholders' Equity" is the balancing footer -
        it equals Total Assets. It also *contains* the text "Total
        Liabilities", so a careless matcher reads it as the liabilities total,
        inflating liabilities by the whole of equity and failing a sheet that
        balances perfectly.
        """
        pdf = text_pdf(
            [
                ("Balance Sheet as at 31 March 2024", None),
                ("Total Assets", "150,000"),
                ("Total Liabilities", "90,000"),
                ("Total Shareholders' Equity", "60,000"),
                ("Total Liabilities and Shareholders' Equity", "150,000"),
            ]
        )
        totals = locate_totals(await parsed_pdf(pdf, settings))

        assert totals.liabilities.value == Decimal("90000"), (
            "the balancing footer was mistaken for the liabilities total"
        )
        assert totals.equity.value == Decimal("60000")

    async def test_total_equity_and_liabilities_is_also_ruled_out(
        self, settings: Settings
    ) -> None:
        """Schedule III prints the footer the other way round."""
        pdf = text_pdf(
            [
                ("Balance Sheet as at 31 March 2024", None),
                ("Total Assets", "150,000"),
                ("Total Liabilities", "90,000"),
                ("Total Equity", "60,000"),
                ("Total Equity and Liabilities", "150,000"),
            ]
        )
        totals = locate_totals(await parsed_pdf(pdf, settings))
        assert totals.liabilities.value == Decimal("90000")
        assert totals.equity.value == Decimal("60000")

    async def test_a_negative_equity_total_is_read_as_negative(
        self, settings: Settings
    ) -> None:
        """Accumulated losses are ordinary and print in parentheses."""
        pdf = text_pdf(
            [
                ("Balance Sheet as at 31 March 2024", None),
                ("Total Assets", "50,000"),
                ("Total Liabilities", "70,000"),
                ("Total Equity", "(20,000)"),
            ]
        )
        totals = locate_totals(await parsed_pdf(pdf, settings))
        assert totals.equity.value == Decimal("-20000")
        assert totals.equity.raw == "(20,000)"


class TestSelectPeriod:
    async def test_a_single_period_sheet_reports_one_period(
        self, settings: Settings
    ) -> None:
        period = select_period(await parsed_pdf(simple_balance_sheet_pdf(), settings))

        assert period is not None
        assert period.selected.year == 2024
        assert len(period.candidates) == 1

    async def test_the_period_end_date_is_parsed_when_printed(
        self, settings: Settings
    ) -> None:
        from datetime import date

        period = select_period(await parsed_pdf(simple_balance_sheet_pdf(), settings))
        assert period.selected.end_date == date(2024, 3, 31)

    async def test_a_comparative_sheet_selects_only_the_most_recent(
        self, settings: Settings
    ) -> None:
        period = select_period(await parsed_pdf(comparative_balance_sheet_pdf(), settings))

        assert period is not None
        assert period.selected.year == 2024
        assert len(period.candidates) == 2
        assert {c.year for c in period.candidates} == {2023, 2024}

    async def test_the_unselected_period_is_recorded_but_not_analysed(
        self, settings: Settings
    ) -> None:
        """Single-period scope. The prior year is evidence, never an input."""
        preliminary = await parsed_pdf(comparative_balance_sheet_pdf(), settings)
        period = select_period(preliminary)
        totals = locate_totals(preliminary, period=period)

        assert totals.assets.value == Decimal("150000"), (
            "the prior-year column was read instead of the current one"
        )
        assert totals.liabilities.value == Decimal("90000")
        assert totals.equity.value == Decimal("60000")

    async def test_the_selection_says_why(self, settings: Settings) -> None:
        period = select_period(await parsed_pdf(comparative_balance_sheet_pdf(), settings))
        assert "Most recent" in period.reason
        assert "2" in period.reason

    async def test_the_selected_period_records_its_source(
        self, settings: Settings
    ) -> None:
        period = select_period(await parsed_pdf(comparative_balance_sheet_pdf(), settings))
        assert period.selected.source.page_index == 0
        assert period.selected.source.column is not None

    async def test_an_undated_sheet_reports_no_period_rather_than_guessing(
        self, settings: Settings
    ) -> None:
        pdf = text_pdf(
            [
                ("Balance Sheet", None),
                ("Total Assets", "150,000"),
                ("Total Liabilities", "90,000"),
                ("Total Equity", "60,000"),
            ]
        )
        assert select_period(await parsed_pdf(pdf, settings)) is None


class TestDetectUnits:
    async def test_currency_is_recorded(self, settings: Settings) -> None:
        units = detect_units(await parsed_pdf(simple_balance_sheet_pdf(), settings))
        assert units is not None
        assert units.currency == "INR"

    async def test_a_scale_is_recorded_but_never_applied(
        self, settings: Settings
    ) -> None:
        """A sheet 'in thousands' keeps its printed figures.

        Scaling is a normalisation decision and belongs to Module 2. Applying it
        here would silently multiply every figure by a thousand at a layer whose
        contract is to preserve what was printed.
        """
        workbook = make_xlsx(
            {
                "BS": [
                    ["Balance Sheet as at 31 March 2024"],
                    ["(All amounts in thousands of INR)"],
                    ["Total Assets", "150"],
                    ["Total Liabilities", "90"],
                    ["Total Equity", "60"],
                ]
            }
        )
        preliminary = await parsed_xlsx(workbook, settings)
        units = detect_units(preliminary)
        totals = locate_totals(preliminary)

        assert units.scale_label == "in thousands"
        assert units.scale_factor == Decimal("1000")
        assert totals.assets.value == Decimal("150"), "the scale factor was applied"
        assert totals.assets.raw == "150"

    async def test_lakhs_and_crores_are_understood(self, settings: Settings) -> None:
        workbook = make_xlsx(
            {"BS": [["Balance Sheet"], ["Rs in lakhs"], ["Total Assets", "150"]]}
        )
        units = detect_units(await parsed_xlsx(workbook, settings))
        assert units.scale_factor == Decimal("100000")

    async def test_a_document_with_no_units_reports_none(
        self, settings: Settings
    ) -> None:
        workbook = make_xlsx(
            {"BS": [["Balance Sheet"], ["Total Assets", "150000"]]}
        )
        assert detect_units(await parsed_xlsx(workbook, settings)) is None


class TestCombinedTotalVariants:
    """The balancing footer, written every way a real filing writes it.

    The fixture balances: 2,300,000 = 1,350,000 + 950,000. Reading the footer
    as the liabilities total therefore does not merely record a wrong number,
    it makes a Balance Sheet that balances perfectly fail the equation check -
    which is exactly what was reported against
    ``ABC_Manufacturing_Balance_Sheet_2026.pdf``.
    """

    FOOTERS = [
        "TOTAL LIABILITIES + EQUITY",
        "Total Liabilities & Shareholders' Equity",
        "Total Liabilities + Shareholders' Equity",
        "Total Equity & Liabilities",
        "Total Liabilities and Net Worth",
        "Total Liabilities and Equity",
    ]

    @pytest.mark.parametrize("footer", FOOTERS)
    async def test_the_footer_never_becomes_the_liabilities_total(
        self, footer: str, settings: Settings
    ) -> None:
        totals = locate_totals(
            await parsed_pdf(footer_balance_sheet_pdf(footer), settings)
        )

        assert totals.liabilities.value == Decimal("1350000"), (
            f"the footer {footer!r} was mistaken for the liabilities total"
        )
        assert totals.equity.value == Decimal("950000")
        assert totals.assets.value == Decimal("2300000")
        assert totals.complete

    @pytest.mark.parametrize("footer", FOOTERS)
    async def test_the_sheet_is_still_recognised_as_a_balance_sheet(
        self, footer: str, settings: Settings
    ) -> None:
        """Ruling the footer out of the totals must not discard it as evidence."""
        evidence = is_balance_sheet(
            await parsed_pdf(footer_balance_sheet_pdf(footer), settings)
        )

        assert evidence.is_balance_sheet is True


class TestTotalKindGuard:
    """A standalone section total and the balancing footer, side by side.

    Asserted at the ``_total_kind`` level and in one class deliberately: the
    two requirements pull against each other. Rule the footer out too weakly
    and it becomes the liabilities total; rule it out too broadly and the
    genuine ``Total Liabilities`` line goes with it.
    """

    @pytest.mark.parametrize(
        ("label", "expected"),
        [
            ("Total Liabilities", "liabilities"),
            ("TOTAL LIABILITIES", "liabilities"),
            ("Total Assets", "assets"),
            ("Total Equity", "equity"),
            ("Total Shareholders' Equity", "equity"),
        ],
    )
    def test_a_standalone_section_total_keeps_its_kind(
        self, label: str, expected: str
    ) -> None:
        assert _total_kind(label) == expected

    @pytest.mark.parametrize(
        "label",
        [
            "Total Liabilities + Equity",
            "Total Liabilities & Equity",
            "Total Liabilities and Equity",
            "TOTAL LIABILITIES + EQUITY",
            "Total Liabilities and Shareholders' Equity",
            "Total Equity and Liabilities",
        ],
    )
    def test_a_combined_total_is_never_a_section_total(self, label: str) -> None:
        assert _total_kind(label) is None


class TestSideBySideLayout:
    """Assets down the left of the page, Liabilities and Equity down the right.

    Every total but one shares its visual row with an unrelated label, so a
    locator that reads only the leading cell finds nothing on the right - and
    reports a Balance Sheet that balances as missing its liabilities.
    """

    async def test_all_three_totals_are_found(self, settings: Settings) -> None:
        totals = locate_totals(await parsed_pdf(side_by_side_balance_sheet_pdf(), settings))

        assert totals.complete, f"missing {totals.missing}"
        assert totals.assets.value == Decimal("2300000")
        assert totals.equity.value == Decimal("950000")

    async def test_a_total_in_the_right_hand_column_is_located(
        self, settings: Settings
    ) -> None:
        """``Total Liabilities`` is printed opposite ``Intangible assets``."""
        totals = locate_totals(await parsed_pdf(side_by_side_balance_sheet_pdf(), settings))

        assert totals.liabilities is not None, (
            "the liabilities total was invisible because it is not the first "
            "cell on its row"
        )
        assert totals.liabilities.value == Decimal("1350000")
        assert totals.liabilities.label.startswith("Total Liabilities")

    async def test_a_figure_is_taken_from_the_label_it_sits_beside(
        self, settings: Settings
    ) -> None:
        """``TOTAL ASSETS 2,300,000`` shares its row with ``Retained earnings 350,000``."""
        totals = locate_totals(await parsed_pdf(side_by_side_balance_sheet_pdf(), settings))

        assert totals.assets.value == Decimal("2300000"), (
            "the assets total took a figure from the other column"
        )

    async def test_the_footer_is_still_ruled_out(self, settings: Settings) -> None:
        """Reading it here would put 2,300,000 back into liabilities."""
        totals = locate_totals(await parsed_pdf(side_by_side_balance_sheet_pdf(), settings))

        assert totals.liabilities.value != Decimal("2300000")

    async def test_the_document_is_still_recognised_as_a_balance_sheet(
        self, settings: Settings
    ) -> None:
        evidence = is_balance_sheet(
            await parsed_pdf(side_by_side_balance_sheet_pdf(), settings)
        )

        assert evidence.is_balance_sheet is True
