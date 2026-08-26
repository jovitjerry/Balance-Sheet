"""OCR: reading scanned Balance Sheet pages.

Every test using the ``ocr_engine`` fixture is marked ``ocr`` automatically and
needs the **Tesseract system binary**. Without it these skip - or fail loudly
under ``--require-ocr``:

    pytest -m ocr --require-ocr

The line-grouping tests below are pure and run everywhere, because that logic
is ours and is where the interesting failures are.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.schemas import PositionedWord, ParserKind
from app.core.lines import group_into_lines
from app.modules.ingestion.ocr import (
    OcrEngine,
    OcrUnavailable,
    TesseractOcrEngine,
    render_pdf_page,
)
from app.modules.ingestion.parsing import parse
from tests.modules.ingestion.fixtures import (
    render_rows_to_image,
    scanned_balance_sheet_image,
    scanned_balance_sheet_pdf,
)
from tests.modules.ingestion.test_parsing import PDF_SOURCE


def word(text: str, left: int, top: int, width: int = 40, height: int = 20) -> PositionedWord:
    return PositionedWord(
        text=text, left=left, top=top, width=width, height=height, confidence=95.0
    )


class TestGroupIntoLines:
    """Rebuilding rows from word boxes. Pure - no Tesseract needed."""

    def test_no_words_makes_no_lines(self) -> None:
        assert group_into_lines([]) == []

    def test_words_on_one_row_become_one_line_ordered_left_to_right(self) -> None:
        words = [word("150,000", 700, 100), word("Total", 60, 100), word("Assets", 130, 100)]
        lines = group_into_lines(words)

        assert len(lines) == 1
        assert lines[0].text == "Total Assets 150,000"

    def test_separate_rows_stay_separate(self) -> None:
        lines = group_into_lines(
            [
                word("Total", 60, 100),
                word("Assets", 130, 100),
                word("Total", 60, 160),
                word("Liabilities", 130, 160),
            ]
        )
        assert [line.text for line in lines] == ["Total Assets", "Total Liabilities"]

    def test_a_label_far_from_its_figure_still_shares_a_row(self) -> None:
        """The whole point: a Balance Sheet's figure sits far to the right.

        Horizontal distance says nothing about row membership - only the
        vertical position does.
        """
        lines = group_into_lines([word("Total Assets", 60, 100), word("150,000", 1900, 100)])
        assert len(lines) == 1
        assert lines[0].text == "Total Assets 150,000"

    def test_baseline_jitter_does_not_split_a_row(self) -> None:
        """Scans are not pixel-perfect; a couple of pixels of drift is normal."""
        lines = group_into_lines(
            [word("Total", 60, 100), word("Assets", 130, 103), word("150,000", 700, 98)]
        )
        assert len(lines) == 1

    def test_lines_are_returned_top_to_bottom(self) -> None:
        lines = group_into_lines(
            [word("third", 60, 300), word("first", 60, 100), word("second", 60, 200)]
        )
        assert [line.text for line in lines] == ["first", "second", "third"]

    def test_a_line_can_report_the_words_in_a_later_column(self) -> None:
        """Column relationships survive, which is what period selection needs."""
        lines = group_into_lines(
            [word("Total Assets", 60, 100), word("150,000", 700, 100), word("120,000", 1000, 100)]
        )
        later = lines[0].words_right_of(650)
        assert [w.text for w in later] == ["150,000", "120,000"]


class TestTesseractEngine:
    def test_it_reads_words_with_positions(self, ocr_engine: OcrEngine) -> None:
        result = ocr_engine.recognise(scanned_balance_sheet_image())

        assert result.words, "OCR returned no words at all"
        texts = [w.text for w in result.words]
        assert "Assets" in texts
        assert any(w.width > 0 and w.height > 0 for w in result.words)

    def test_positions_are_preserved_not_discarded(self, ocr_engine: OcrEngine) -> None:
        """Figures sit far right of labels; the boxes have to show that."""
        result = ocr_engine.recognise(scanned_balance_sheet_image())
        labels = [w for w in result.words if w.text == "Assets"]
        figures = [w for w in result.words if w.text == "150,000"]

        assert labels and figures
        assert min(f.left for f in figures) > max(lbl.left for lbl in labels)

    def test_a_label_and_its_figure_land_on_the_same_reconstructed_line(
        self, ocr_engine: OcrEngine
    ) -> None:
        """This is the failure geometric grouping exists to prevent.

        Tesseract's own reading order puts a two-column table's labels in one
        block and its figures in another, so the pairing between them is lost.
        """
        result = ocr_engine.recognise(scanned_balance_sheet_image())
        totals = [line for line in result.lines if line.text.startswith("Total Assets")]

        assert totals, f"no 'Total Assets' line in {[l.text for l in result.lines]}"
        assert "150,000" in totals[0].text

    def test_confidence_is_recorded(self, ocr_engine: OcrEngine) -> None:
        result = ocr_engine.recognise(scanned_balance_sheet_image())
        assert result.confidence is not None
        assert 0 <= result.confidence <= 100

    def test_a_blank_page_yields_no_words_rather_than_noise(
        self, ocr_engine: OcrEngine
    ) -> None:
        from PIL import Image

        result = ocr_engine.recognise(Image.new("RGB", (800, 600), "white"))
        assert result.words == []
        assert result.confidence is None


class TestRasterisation:
    def test_a_pdf_page_renders_to_an_image(self, ocr_engine: OcrEngine) -> None:
        image = render_pdf_page(scanned_balance_sheet_pdf(), 0, dpi=200)
        assert image.width > 0 and image.height > 0

    def test_higher_dpi_produces_a_larger_image(self, ocr_engine: OcrEngine) -> None:
        low = render_pdf_page(scanned_balance_sheet_pdf(), 0, dpi=100)
        high = render_pdf_page(scanned_balance_sheet_pdf(), 0, dpi=300)
        assert high.width > low.width


class TestScannedPdfEndToEnd:
    async def test_a_scanned_pdf_is_read_through_ocr(
        self, ocr_engine: OcrEngine, settings: Settings
    ) -> None:
        result = await parse(
            scanned_balance_sheet_pdf(), PDF_SOURCE, settings=settings, ocr=ocr_engine
        )

        assert result.parser is ParserKind.PDF_OCR
        page = result.pages[0]
        assert page.ocr_used is True
        assert page.words, "word positions were not preserved"
        assert page.ocr_confidence is not None
        assert "Total Assets" in page.text

    async def test_the_reconstructed_text_keeps_figures_beside_their_labels(
        self, ocr_engine: OcrEngine, settings: Settings
    ) -> None:
        result = await parse(
            scanned_balance_sheet_pdf(), PDF_SOURCE, settings=settings, ocr=ocr_engine
        )
        lines = result.pages[0].text.splitlines()

        assert any("Total Assets" in line and "150,000" in line for line in lines), (
            f"label and figure were separated: {lines}"
        )

    async def test_page_pixel_dimensions_are_recorded_for_the_boxes(
        self, ocr_engine: OcrEngine, settings: Settings
    ) -> None:
        """Word coordinates are pixels; without the page size they mean nothing."""
        result = await parse(
            scanned_balance_sheet_pdf(), PDF_SOURCE, settings=settings, ocr=ocr_engine
        )
        page = result.pages[0]
        assert page.page_width and page.page_height
        assert all(w.left <= page.page_width for w in page.words)


class TestEngineAvailability:
    def test_a_missing_binary_reports_unavailable_rather_than_crashing(self) -> None:
        engine = TesseractOcrEngine(binary="definitely-not-a-real-binary")
        assert engine.available() is False

    def test_a_missing_binary_surfaces_as_a_clean_error(self) -> None:
        """No paths, no stack trace - this message can reach a caller."""
        engine = TesseractOcrEngine(binary="definitely-not-a-real-binary")
        with pytest.raises(OcrUnavailable) as caught:
            engine.recognise(render_rows_to_image([("Total Assets", "150,000")]))

        message = caught.value.message
        assert "Traceback" not in message
        assert "definitely-not-a-real-binary" not in message
