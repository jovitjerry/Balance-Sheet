"""Module 3 against the real Balance Sheets Modules 1 and 2 were built on.

The whole chain runs here - parse, identify, select the period, locate the
totals, extract every line item, normalize the terminology, compute the ratios -
and **no language model is involved at any point**. Every label on these
documents already spells its canonical concept, so Module 2's identity
dictionary resolves all of them and the provider is never called. The provider
passed in is one that would raise if it were.

That is what makes these acceptance tests rather than integration tests: the
expected values below are hand-derived from the figures printed on the fixture,
and nothing in the pipeline could have produced them by inference.

    Meridian, side-by-side layout, full current/non-current split
        Current assets      850,000 = 125,000 + 280,000 + 350,000 + 95,000
        Current liabilities 650,000 = 300,000 + 200,000 + 150,000
        Total assets      2,300,000   Total liabilities 1,350,000
        Total equity        950,000

    ABC, single column, NO current/non-current headings at all
        Current assets      300,000 = cash only
        Current liabilities 350,000 = trade payables only
        Total assets      2,300,000   Total liabilities 1,350,000
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.config import Settings
from app.core.schemas import ExtractedBalanceSheet, RatioStatus
from app.modules.extraction.service import extract
from app.modules.ratios.service import compute_ratios
from tests.modules.extraction.fixtures import OfflineProvider, validated_document
from tests.modules.ingestion.fixtures import (
    abc_manufacturing_balance_sheet_pdf,
    side_by_side_balance_sheet_pdf,
)


async def _sheet(data: bytes, settings: Settings) -> ExtractedBalanceSheet:
    """The real pipeline, as far as Module 2, with the model switched off."""
    document = await validated_document(data, settings)
    return await extract(document, provider=OfflineProvider(), settings=settings)


@pytest.fixture
async def meridian(settings: Settings) -> ExtractedBalanceSheet:
    return await _sheet(side_by_side_balance_sheet_pdf(), settings)


@pytest.fixture
async def abc(settings: Settings) -> ExtractedBalanceSheet:
    return await _sheet(abc_manufacturing_balance_sheet_pdf(), settings)


class TestMeridian:
    """A comparative-free horizontal sheet with every subsection printed."""

    async def test_the_derived_subtotals_match_the_sheets_own_printed_subtotals(
        self, meridian: ExtractedBalanceSheet
    ) -> None:
        """The strongest available check that aggregation neither drops nor doubles.

        The document prints "Total Current Assets 850,000" and "Total Current
        Liabilities 650,000". Module 2 discards both, so Module 3 reassembles
        them from the leaves - and has to land on exactly the same figures.
        """
        result = compute_ratios(meridian)
        current = result.get("current_ratio")
        assert current is not None
        assert current.numerator == Decimal("850000")
        assert current.denominator == Decimal("650000")

    async def test_all_seven_ratios(self, meridian: ExtractedBalanceSheet) -> None:
        result = compute_ratios(meridian)

        assert result.get("current_ratio").value == Decimal("1.307692")  # type: ignore[union-attr]
        assert result.get("quick_ratio").value == Decimal("0.769231")  # type: ignore[union-attr]
        assert result.get("cash_ratio").value == Decimal("0.192308")  # type: ignore[union-attr]
        assert result.get("debt_to_equity").value == Decimal("1.421053")  # type: ignore[union-attr]
        assert result.get("debt_ratio").value == Decimal("0.586957")  # type: ignore[union-attr]
        assert result.get("equity_ratio").value == Decimal("0.413043")  # type: ignore[union-attr]
        assert result.get("working_capital").value == Decimal("200000")  # type: ignore[union-attr]

    async def test_every_ratio_is_fully_covered(
        self, meridian: ExtractedBalanceSheet
    ) -> None:
        """Nothing on this document went unclassified, so nothing is partial."""
        result = compute_ratios(meridian)
        for ratio in result.ratios:
            assert ratio.status is RatioStatus.OK, f"{ratio.name}: {ratio.reason}"
        assert result.diagnostics.unclassified == []

    async def test_no_comparative_figure_reaches_a_ratio(
        self, meridian: ExtractedBalanceSheet
    ) -> None:
        """Single-period scope, inherited from Module 2 and re-asserted here.

        Every figure came through core.lines.figure_for, which reads the
        selected column and no other.
        """
        result = compute_ratios(meridian)
        printed = {
            Decimal(cell.replace(",", ""))
            for row in _MERIDIAN_FIGURES
            for cell in row
        }
        for ratio in result.ratios:
            for entry in [*ratio.numerator_inputs, *ratio.denominator_inputs]:
                assert entry.value in printed, entry

    async def test_the_leverage_ratios_rest_on_module_1s_printed_totals(
        self, meridian: ExtractedBalanceSheet
    ) -> None:
        result = compute_ratios(meridian)
        debt = result.get("debt_ratio")
        assert debt is not None
        [total] = debt.denominator_inputs
        assert total.label == "TOTAL ASSETS"
        assert total.value == Decimal("2300000")

    async def test_a_figure_traces_back_to_a_page_and_a_row(
        self, meridian: ExtractedBalanceSheet
    ) -> None:
        result = compute_ratios(meridian)
        current = result.get("current_ratio")
        assert current is not None

        inventory = next(
            entry
            for entry in current.numerator_inputs
            if entry.canonical_label == "inventory"
        )
        assert inventory.label == "Inventory"
        assert inventory.value == Decimal("350000")
        assert inventory.source is not None
        assert inventory.source.page_index == 0
        assert inventory.source.column is not None

    async def test_the_balancing_footer_is_not_a_line_item(
        self, meridian: ExtractedBalanceSheet
    ) -> None:
        """TOTAL LIABILITIES + EQUITY 2,300,000 must contribute to nothing."""
        result = compute_ratios(meridian)
        for ratio in result.ratios:
            for entry in [*ratio.numerator_inputs, *ratio.denominator_inputs]:
                if entry.canonical_label is not None:
                    assert entry.value != Decimal("2300000")


# Every figure printed on the Meridian fixture, for the single-period check.
_MERIDIAN_FIGURES = (
    ("125,000", "300,000"),
    ("280,000", "200,000"),
    ("350,000", "150,000"),
    ("95,000", "650,000"),
    ("850,000", "600,000"),
    ("1,200,000", "100,000"),
    ("150,000", "1,350,000"),
    ("100,000", "600,000"),
    ("1,450,000", "350,000"),
    ("2,300,000", "950,000"),
)


class TestAbcManufacturing:
    """A single-column sheet that prints no current/non-current headings at all.

    The more important of the two documents: every LineItem.subsection here is
    None, so these ratios exist only because classification reads the canonical
    category rather than the printed heading.
    """

    async def test_no_line_item_has_a_printed_subsection(
        self, abc: ExtractedBalanceSheet
    ) -> None:
        for part in (abc.assets, abc.liabilities, abc.equity):
            for line in part.line_items:
                assert line.subsection is None

    async def test_liquidity_is_computed_anyway(self, abc: ExtractedBalanceSheet) -> None:
        result = compute_ratios(abc)

        current = result.get("current_ratio")
        assert current is not None
        assert current.numerator == Decimal("300000")
        assert current.denominator == Decimal("350000")
        assert current.value == Decimal("0.857143")

    async def test_negative_working_capital_is_reported_with_its_sign(
        self, abc: ExtractedBalanceSheet
    ) -> None:
        working = compute_ratios(abc).get("working_capital")
        assert working is not None
        assert working.value == Decimal("-50000")
        assert "negative_result" in working.warnings
        assert working.status is RatioStatus.OK

    async def test_quick_equals_current_when_there_is_no_inventory(
        self, abc: ExtractedBalanceSheet
    ) -> None:
        result = compute_ratios(abc)
        assert result.get("quick_ratio").value == result.get("current_ratio").value  # type: ignore[union-attr]

    async def test_the_leverage_ratios(self, abc: ExtractedBalanceSheet) -> None:
        result = compute_ratios(abc)
        assert result.get("debt_ratio").value == Decimal("0.586957")  # type: ignore[union-attr]
        assert result.get("equity_ratio").value == Decimal("0.413043")  # type: ignore[union-attr]
        assert result.get("debt_to_equity").value == Decimal("1.421053")  # type: ignore[union-attr]


class TestWithoutTheModel:
    """The engine is fully exercised with Ollama absent - because it always is here.

    Both fixtures above already ran against a provider that raises if called.
    This makes the guarantee explicit rather than incidental.
    """

    async def test_the_provider_was_never_consulted(self, settings: Settings) -> None:
        provider = OfflineProvider()
        document = await validated_document(side_by_side_balance_sheet_pdf(), settings)
        sheet = await extract(document, provider=provider, settings=settings)

        # OfflineProvider.complete_json raises AssertionError if reached; that
        # extraction completed at all is the proof it was not.
        result = compute_ratios(sheet)
        assert result.get("current_ratio").value == Decimal("1.307692")  # type: ignore[union-attr]

    async def test_an_unnormalizable_sheet_still_yields_leverage_ratios(
        self, meridian: ExtractedBalanceSheet
    ) -> None:
        """Strip every mapping: the printed totals survive, the derived sums do not.

        This is the shape of a real run with Ollama stopped and labels the
        identity dictionary cannot resolve. Nothing is invented in place of the
        ratios that go missing.
        """
        stripped = meridian.model_copy(deep=True)
        for part in (stripped.assets, stripped.liabilities, stripped.equity):
            for line in part.line_items:
                if line.normalization is not None:
                    line.normalization.canonical_label = None
                    line.normalization.status = line.normalization.status.NEEDS_REVIEW

        result = compute_ratios(stripped)

        for name in ("debt_ratio", "equity_ratio", "debt_to_equity"):
            ratio = result.get(name)
            assert ratio is not None
            assert ratio.status is RatioStatus.OK, name

        for name in ("current_ratio", "quick_ratio", "cash_ratio", "working_capital"):
            ratio = result.get(name)
            assert ratio is not None
            assert ratio.status is RatioStatus.UNAVAILABLE, name
            assert ratio.value is None
            assert ratio.reason == "no_classified_inputs"


class TestIdempotence:
    async def test_recomputing_gives_an_identical_result(
        self, meridian: ExtractedBalanceSheet
    ) -> None:
        first = compute_ratios(meridian)
        second = compute_ratios(meridian)
        assert first.model_dump(exclude={"computed_at"}) == second.model_dump(
            exclude={"computed_at"}
        )
