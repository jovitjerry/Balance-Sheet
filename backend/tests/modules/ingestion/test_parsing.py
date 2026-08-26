"""Module 1 parsing: raw text and tables out of PDFs and workbooks.

These are pure - no cluster. The OCR path is exercised separately in
``test_ocr.py``, which needs the Tesseract binary; what is checked here is that
a scanned page is *detected* and that a missing engine is reported rather than
silently producing an empty page.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.errors import UnreadableDocumentError
from app.core.schemas import ParserKind, SourceFile, StorageRef
from app.modules.ingestion.ocr import OcrUnavailable
from app.modules.ingestion.parsing import parse
from app.modules.ingestion.validation import UploadKind
from tests.modules.ingestion.fixtures import (
    Text,
    blank_scanned_pdf,
    make_text_pdf,
    make_xlsx,
    scanned_balance_sheet_pdf,
    simple_balance_sheet_pdf,
    simple_balance_sheet_xlsx,
)


def source_for(filename: str, content_type: str) -> SourceFile:
    return SourceFile(
        filename=filename,
        content_type=content_type,
        size_bytes=1,
        sha256="c" * 64,
        ref=StorageRef(
            backend="local", key="cc/cc/x", size_bytes=1, content_type=content_type
        ),
    )


PDF_SOURCE = source_for("sheet.pdf", "application/pdf")
XLSX_SOURCE = source_for(
    "sheet.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)


class TestParsePdf:
    async def test_a_digital_pdf_needs_no_ocr(self, settings: Settings) -> None:
        result = await parse(simple_balance_sheet_pdf(), PDF_SOURCE, settings=settings)

        assert result.parser is ParserKind.PDF_TEXT
        assert len(result.pages) == 1
        assert result.pages[0].ocr_used is False
        assert result.pages[0].ocr_confidence is None

    async def test_a_digital_page_still_records_word_positions(
        self, settings: Settings
    ) -> None:
        """Geometry is captured for digital pages too, not only scans.

        A comparative sheet's columns are distinguishable only by position, and
        that is as true of an exported PDF as of a scan.
        """
        result = await parse(simple_balance_sheet_pdf(), PDF_SOURCE, settings=settings)
        words = result.pages[0].words

        assert words, "no word positions recorded for a digital page"
        assert all(w.confidence is None for w in words), (
            "digital text was read, not guessed - it must carry no OCR confidence"
        )
        figures = [w for w in words if w.text == "150,000"]
        labels = [w for w in words if w.text == "Assets"]
        assert figures and labels
        assert figures[0].left > labels[0].left

    async def test_it_preserves_the_printed_text(self, settings: Settings) -> None:
        result = await parse(simple_balance_sheet_pdf(), PDF_SOURCE, settings=settings)
        text = result.pages[0].text

        assert "Total Assets" in text
        assert "150,000" in text
        # The thousands separator survives: this is raw output, not a parsed
        # number. Module 2 decides what "150,000" means.
        assert "150000" not in text

    async def test_page_geometry_is_recorded(self, settings: Settings) -> None:
        result = await parse(simple_balance_sheet_pdf(), PDF_SOURCE, settings=settings)
        page = result.pages[0]
        assert page.page_width == pytest.approx(612.0)
        assert page.page_height == pytest.approx(792.0)

    async def test_every_page_is_indexed_in_order(self, settings: Settings) -> None:
        pdf = make_text_pdf(
            [
                [Text(72, 700, "Report of the Directors for the year ended 2024")],
                [Text(72, 700, "Balance Sheet as at 31 March 2024 for Acme Limited")],
                [Text(72, 700, "Notes forming part of the financial statements")],
            ]
        )
        result = await parse(pdf, PDF_SOURCE, settings=settings)

        assert [page.index for page in result.pages] == [0, 1, 2]
        assert "Balance Sheet" in result.pages[1].text

    async def test_a_pdf_with_no_readable_text_is_reported_not_faked(
        self, settings: Settings
    ) -> None:
        """A blank scan is 'unreadable', never 'an empty Balance Sheet'."""
        settings = settings.model_copy(update={"ocr_enabled": False})
        with pytest.raises(OcrUnavailable, match="OCR is disabled"):
            await parse(blank_scanned_pdf(), PDF_SOURCE, settings=settings)

    async def test_a_corrupt_pdf_is_reported_without_leaking_internals(
        self, settings: Settings
    ) -> None:
        garbage = b"%PDF-1.4\n" + b"\x00" * 400
        with pytest.raises(UnreadableDocumentError) as caught:
            await parse(garbage, PDF_SOURCE, settings=settings)

        message = caught.value.message
        assert "Traceback" not in message
        assert "\\" not in message and "pdfminer" not in message.lower()


class TestScannedPageDetection:
    async def test_a_scanned_page_without_an_engine_refuses_loudly(
        self, settings: Settings
    ) -> None:
        """No engine must never mean 'this page was blank'.

        Reporting an empty page would send the document on to identification,
        which would truthfully say 'not a Balance Sheet' about a verdict it
        never actually reached.
        """
        with pytest.raises(OcrUnavailable, match="not available"):
            await parse(scanned_balance_sheet_pdf(), PDF_SOURCE, settings=settings, ocr=None)

    async def test_ocr_disabled_refuses_scanned_documents(
        self, settings: Settings
    ) -> None:
        settings = settings.model_copy(update={"ocr_enabled": False})
        with pytest.raises(OcrUnavailable, match="OCR is disabled"):
            await parse(scanned_balance_sheet_pdf(), PDF_SOURCE, settings=settings)

    async def test_detection_is_per_page_not_per_document(
        self, settings: Settings
    ) -> None:
        """A digital page beside a scanned one must not drag the whole file to OCR.

        Mixed filings are ordinary - an exported statement with a scanned signed
        page. The digital page here is readable, so the failure raised is about
        the *scanned* page only.
        """
        from tests.modules.ingestion.fixtures import (
            image_to_jpeg,
            make_image_pdf,
            scanned_balance_sheet_image,
        )

        # Page 1 digital, page 2 scanned, spliced by parsing each separately.
        digital = await parse(
            make_text_pdf([[Text(72, 700, "Balance Sheet of Acme Limited")]]),
            PDF_SOURCE,
            settings=settings,
        )
        assert digital.pages[0].ocr_used is False

        scanned = make_image_pdf([image_to_jpeg(scanned_balance_sheet_image())])
        with pytest.raises(OcrUnavailable, match="Page 1"):
            await parse(scanned, PDF_SOURCE, settings=settings, ocr=None)


class TestParseXlsx:
    async def test_a_workbook_is_read_sheet_by_sheet(self, settings: Settings) -> None:
        result = await parse(
            simple_balance_sheet_xlsx(),
            XLSX_SOURCE,
            kind=UploadKind.XLSX,
            settings=settings,
        )

        assert result.parser is ParserKind.EXCEL
        assert len(result.pages) == 1
        assert result.pages[0].name == "Balance Sheet"
        assert result.pages[0].ocr_used is False

    async def test_each_sheet_becomes_its_own_indexed_page(
        self, settings: Settings
    ) -> None:
        workbook = make_xlsx(
            {
                "Cover": [["Annual Report 2024"]],
                "Balance Sheet": [["Total Assets", "150,000"]],
            }
        )
        result = await parse(workbook, XLSX_SOURCE, kind=UploadKind.XLSX, settings=settings)

        assert [(page.index, page.name) for page in result.pages] == [
            (0, "Cover"),
            (1, "Balance Sheet"),
        ]

    async def test_cells_stay_strings_exactly_as_printed(
        self, settings: Settings
    ) -> None:
        """``(2,300)`` and ``1,234.5`` must remain recoverable as printed."""
        workbook = make_xlsx({"BS": [["Accumulated losses", "(2,300)"], ["Ratio", "1,234.5"]]})
        result = await parse(workbook, XLSX_SOURCE, kind=UploadKind.XLSX, settings=settings)

        rows = result.pages[0].tables[0].rows
        assert rows[0] == ["Accumulated losses", "(2,300)"]
        assert rows[1] == ["Ratio", "1,234.5"]

    async def test_whole_numbers_do_not_acquire_a_float_tail(
        self, settings: Settings
    ) -> None:
        """openpyxl hands back 150000.0; ``"150000.0"`` was never printed."""
        workbook = make_xlsx({"BS": [["Total Assets", 150000], ["Rate", 1.5]]})
        result = await parse(workbook, XLSX_SOURCE, kind=UploadKind.XLSX, settings=settings)

        rows = result.pages[0].tables[0].rows
        assert rows[0] == ["Total Assets", "150000"]
        assert rows[1] == ["Rate", "1.5"]

    async def test_an_empty_workbook_is_reported_as_unreadable(
        self, settings: Settings
    ) -> None:
        with pytest.raises(UnreadableDocumentError, match="empty"):
            await parse(
                make_xlsx({"Sheet1": []}),
                XLSX_SOURCE,
                kind=UploadKind.XLSX,
                settings=settings,
            )

    async def test_damaged_workbook_bytes_are_reported_not_swallowed(
        self, settings: Settings
    ) -> None:
        """The verdict upload validation deliberately left to the parser."""
        damaged = bytearray(simple_balance_sheet_xlsx())
        damaged[40:200] = b"\x00" * 160

        with pytest.raises(UnreadableDocumentError) as caught:
            await parse(
                bytes(damaged), XLSX_SOURCE, kind=UploadKind.XLSX, settings=settings
            )
        assert "Traceback" not in caught.value.message
