"""PDF / Excel parsing and OCR for Module 1.

Produces a :class:`~app.core.schemas.PreliminaryExtraction`: raw per-page text
and tables, with table cells kept as **strings exactly as printed**, plus OCR
metadata and word positions.

Nothing here normalises or interprets a value. ``"(2,300)"`` stays
``"(2,300)"`` - the parenthetical negative and the thousands separator are
evidence about how the document was printed, and Module 2 re-derives structured
data from this output. Coercing to numbers at this layer would destroy the
thing it exists to preserve.

The parser choices are fixed: **pdfplumber** for digital PDF text and tables,
**pypdfium2 + Tesseract** for scanned pages, **openpyxl** for ``.xlsx``.
"""

from __future__ import annotations

import io
import logging
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from app.core.config import Settings
from app.core.errors import UnreadableDocumentError
from app.core.schemas import (
    ParserKind,
    PositionedWord,
    PreliminaryExtraction,
    RawTable,
    SourceFile,
    SourcePage,
)
from app.modules.ingestion.ocr import (
    OcrEngine,
    OcrUnavailable,
    render_pdf_page,
)
from app.modules.ingestion.validation import UploadKind, looks_like_pdf

logger = logging.getLogger(__name__)

# Guard against a document that is technically readable but absurd to process.
MAX_PAGES = 200


async def parse(
    data: bytes,
    source: SourceFile,
    *,
    kind: UploadKind | None = None,
    settings: Settings | None = None,
    ocr: OcrEngine | None = None,
) -> PreliminaryExtraction:
    """Parse an uploaded file into raw text and tables.

    Routes to the PDF or Excel reader, and within a PDF decides *per page*
    whether the text layer is usable or the page has to be rasterised and read
    by OCR.

    :raises UnreadableDocumentError: the container opened but yielded nothing.
    :raises OcrUnavailable: a page needs OCR and no engine can run.
    """
    from app.core.config import get_settings

    config = settings or get_settings()
    resolved = kind or (UploadKind.PDF if looks_like_pdf(data) else UploadKind.XLSX)

    if resolved is UploadKind.PDF:
        return _parse_pdf(data, config, ocr)
    return _parse_xlsx(data)


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------


def _parse_pdf(
    data: bytes, settings: Settings, ocr: OcrEngine | None
) -> PreliminaryExtraction:
    import pdfplumber

    pages: list[SourcePage] = []
    warnings: list[str] = []

    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - pdfminer raises a wide family
        logger.warning("PDF could not be opened: %s", exc)
        raise UnreadableDocumentError(
            "The PDF could not be opened. It may be corrupt, or password "
            "protected."
        ) from exc

    try:
        if not pdf.pages:
            raise UnreadableDocumentError("The PDF contains no pages.")
        if len(pdf.pages) > MAX_PAGES:
            raise UnreadableDocumentError(
                f"The PDF has more than {MAX_PAGES} pages, which is beyond what "
                "this system processes."
            )

        for index, page in enumerate(pdf.pages):
            pages.append(_parse_pdf_page(data, page, index, settings, ocr, warnings))
    finally:
        pdf.close()

    if not any(page.text.strip() for page in pages):
        raise UnreadableDocumentError(
            "No readable text could be extracted from the document."
        )

    ocr_pages = sum(1 for page in pages if page.ocr_used)
    if ocr_pages == 0:
        parser = ParserKind.PDF_TEXT
    elif ocr_pages == len(pages):
        parser = ParserKind.PDF_OCR
    else:
        parser = ParserKind.PDF_MIXED

    return PreliminaryExtraction(parser=parser, pages=pages, warnings=warnings)


def _parse_pdf_page(
    data: bytes,
    page: object,
    index: int,
    settings: Settings,
    ocr: OcrEngine | None,
    warnings: list[str],
) -> SourcePage:
    """Read one page, falling back to OCR when its text layer is unusable."""
    text = (page.extract_text() or "").strip()  # type: ignore[attr-defined]
    char_count = len(page.chars)  # type: ignore[attr-defined]

    if char_count >= settings.ocr_min_chars_per_page and text:
        return SourcePage(
            index=index,
            text=text,
            tables=_extract_pdf_tables(page, warnings, index),
            ocr_used=False,
            words=_extract_pdf_words(page, index, warnings),
            page_width=float(page.width),  # type: ignore[attr-defined]
            page_height=float(page.height),  # type: ignore[attr-defined]
        )

    # Scanned. Detection is per page: a filing can mix an exported statement
    # with a scanned signature page, and treating the whole document as one or
    # the other loses half of it either way.
    return _ocr_pdf_page(data, index, settings, ocr, warnings)


def _ocr_pdf_page(
    data: bytes,
    index: int,
    settings: Settings,
    ocr: OcrEngine | None,
    warnings: list[str],
) -> SourcePage:
    if not settings.ocr_enabled:
        raise OcrUnavailable(
            f"Page {index + 1} is a scanned image and OCR is disabled on this "
            "server, so it cannot be read."
        )
    if ocr is None or not ocr.available():
        raise OcrUnavailable(
            f"Page {index + 1} is a scanned image and requires OCR, which is "
            "not available on this server."
        )

    try:
        image = render_pdf_page(data, index, dpi=settings.ocr_dpi)
    except OcrUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 - PDFium raises its own family
        logger.warning("Could not rasterise page %d: %s", index, exc)
        raise UnreadableDocumentError(
            f"Page {index + 1} could not be rendered for reading."
        ) from exc

    result = ocr.recognise(image)
    if not result.words:
        warnings.append(f"Page {index + 1}: OCR found no legible text.")

    return SourcePage(
        index=index,
        text=result.text,
        tables=[],  # Table structure on a scan is reconstructed from word boxes.
        ocr_used=True,
        ocr_confidence=result.confidence,
        words=result.words,
        page_width=float(result.width),
        page_height=float(result.height),
    )


def _extract_pdf_words(
    page: object, index: int, warnings: list[str]
) -> list[PositionedWord]:
    """Record word boxes from a digital page's text layer.

    The same positioned form OCR produces, so that column handling downstream
    is one code path. A digital PDF's reading order is no more trustworthy than
    a scan's: ``extract_text`` on a two-column comparative sheet can interleave
    the columns, and only the geometry says which figure belongs to which
    reporting period.

    ``confidence`` stays ``None`` - these characters were read from the file,
    not guessed at, and inventing a score would blur that distinction.
    """
    try:
        found = page.extract_words()  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001 - best-effort, text is already captured
        logger.info("Word extraction failed on page %d: %s", index, exc)
        warnings.append(f"Page {index + 1}: word positions could not be extracted.")
        return []

    return [
        PositionedWord(
            text=word["text"],
            left=float(word["x0"]),
            top=float(word["top"]),
            width=max(0.0, float(word["x1"]) - float(word["x0"])),
            height=max(0.0, float(word["bottom"]) - float(word["top"])),
        )
        for word in found
        if word.get("text", "").strip()
    ]


def _extract_pdf_tables(page: object, warnings: list[str], index: int) -> list[RawTable]:
    """Pull tables, keeping every cell a string exactly as printed."""
    try:
        found = page.extract_tables()  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001 - table finding is best-effort
        logger.info("Table extraction failed on page %d: %s", index, exc)
        warnings.append(f"Page {index + 1}: tables could not be extracted.")
        return []

    tables: list[RawTable] = []
    for table in found:
        rows = [
            [None if cell is None else str(cell).strip() for cell in row]
            for row in table
        ]
        if any(any(cell for cell in row) for row in rows):
            tables.append(RawTable(rows=rows))
    return tables


# --------------------------------------------------------------------------
# Excel
# --------------------------------------------------------------------------


def _parse_xlsx(data: bytes) -> PreliminaryExtraction:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(
            io.BytesIO(data),
            # Streams rows instead of materialising the whole sheet, and reads
            # cached values rather than formula strings - the printed figure is
            # what a Balance Sheet reader sees, not "=SUM(B4:B9)".
            read_only=True,
            data_only=True,
        )
    except Exception as exc:  # noqa: BLE001 - openpyxl raises a wide family
        logger.warning("Workbook could not be opened: %s", exc)
        raise UnreadableDocumentError(
            "The Excel workbook could not be read. The file appears to be "
            "corrupt or incomplete."
        ) from exc

    pages: list[SourcePage] = []
    warnings: list[str] = []
    try:
        for index, sheet in enumerate(workbook.worksheets):
            rows = [
                [_cell_to_str(value) for value in row]
                for row in sheet.iter_rows(values_only=True)
            ]
            rows = [row for row in rows if any(cell for cell in row)]
            pages.append(
                SourcePage(
                    index=index,
                    name=sheet.title,
                    text="\n".join(
                        " ".join(cell for cell in row if cell) for row in rows
                    ),
                    tables=[RawTable(rows=rows)] if rows else [],
                    ocr_used=False,
                )
            )
    finally:
        workbook.close()

    if not pages or not any(page.text.strip() for page in pages):
        raise UnreadableDocumentError(
            "The workbook is empty - no readable cells were found."
        )

    return PreliminaryExtraction(
        parser=ParserKind.EXCEL, pages=pages, warnings=warnings
    )


def _cell_to_str(value: object) -> str | None:
    """Render a cell as the string a reader would see, without float artefacts.

    openpyxl hands back Python objects, and a whole-number cell arrives as
    ``150000.0``. Stringifying that directly would write ``"150000.0"`` into the
    raw record - a printed form that never appeared in the document. Routing
    through ``Decimal`` keeps the digits and drops the artificial ``.0``.

    This is the one place a ``float`` is touched, and it is deliberate: it is
    the boundary where a value arrives as one, and the conversion is exact for
    the magnitudes a Balance Sheet contains. No arithmetic is done on it - the
    result is a string, and every later calculation reads ``Decimal``.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        try:
            decimal = Decimal(str(value))
        except InvalidOperation:  # pragma: no cover - str(float) is always valid
            return str(value)
        if decimal == decimal.to_integral_value():
            return str(decimal.quantize(Decimal(1)))
        return str(decimal.normalize())
    return str(value)


__all__ = ["MAX_PAGES", "parse"]
