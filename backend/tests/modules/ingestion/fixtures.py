"""Synthetic PDF and XLSX documents for Module 1 tests.

These are built byte-by-byte rather than checked in as binary blobs so that
what a test is exercising is *readable in the test*: change a figure here and
you can see exactly which cell moved.

The PDF writer emits a minimal but genuinely valid file - real ``xref`` table,
real offsets - because the point of these fixtures is to drive pdfplumber and
pdfminer.six, which reject a fake.
"""

from __future__ import annotations

import io
import zipfile
from typing import Iterable, NamedTuple

PAGE_WIDTH = 612.0
PAGE_HEIGHT = 792.0


class Text(NamedTuple):
    """A run of text placed at a point on the page, in PDF user space.

    ``y`` grows *upwards* from the bottom of the page, as PDF does it.
    """

    x: float
    y: float
    text: str
    size: float = 10.0


def _escape(text: str) -> bytes:
    escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
    return escaped.encode("latin-1", errors="replace")


def _content_stream(runs: Iterable[Text]) -> bytes:
    parts = [b"BT\n"]
    for run in runs:
        parts.append(
            b"/F1 %s Tf 1 0 0 1 %s %s Tm (%s) Tj\n"
            % (
                f"{run.size:g}".encode(),
                f"{run.x:g}".encode(),
                f"{run.y:g}".encode(),
                _escape(run.text),
            )
        )
    parts.append(b"ET\n")
    return b"".join(parts)


def _assemble(objects: list[bytes]) -> bytes:
    """Serialise numbered objects into a PDF with a correct xref table.

    ``objects[i]`` is the body of object ``i + 1``.
    """
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number
        out += body
        out += b"\nendobj\n"

    xref_at = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\n" % (len(objects) + 1)
    out += b"startxref\n%d\n%%%%EOF\n" % xref_at
    return bytes(out)


def make_text_pdf(pages: list[list[Text]]) -> bytes:
    """Build a digital PDF whose pages carry a real text layer.

    This is what an exported-from-accounting-software filing looks like:
    pdfplumber finds characters and needs no OCR.
    """
    page_count = len(pages)
    # Object layout: 1 catalog, 2 pages tree, 3 font, then per page a page
    # object followed by its content stream.
    first_page_obj = 4
    kids = " ".join(f"{first_page_obj + 2 * i} 0 R" for i in range(page_count))

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids.encode(), page_count),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for index, runs in enumerate(pages):
        page_number = first_page_obj + 2 * index
        content_number = page_number + 1
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %s %s] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>"
            % (f"{PAGE_WIDTH:g}".encode(), f"{PAGE_HEIGHT:g}".encode(), content_number)
        )
        stream = _content_stream(runs)
        objects.append(
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)
        )
    return _assemble(objects)


def make_image_pdf(jpegs: list[tuple[bytes, int, int]]) -> bytes:
    """Build a PDF whose pages are images only - a scanned filing.

    There is no text layer at all, which is precisely what scanned-page
    detection has to notice.

    Each page is sized to its image's aspect ratio. Forcing a letter-shaped
    MediaBox instead would stretch the glyphs when the page is rasterised back
    out, and OCR accuracy falls off a cliff on distorted text - the fixture
    would then be testing Tesseract's tolerance for squashed type rather than
    anything this project owns.
    """
    page_count = len(jpegs)
    first_page_obj = 3
    kids = " ".join(f"{first_page_obj + 3 * i} 0 R" for i in range(page_count))

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids.encode(), page_count),
    ]
    for index, (jpeg, width, height) in enumerate(jpegs):
        page_number = first_page_obj + 3 * index
        content_number = page_number + 1
        image_number = page_number + 2
        box_width = PAGE_WIDTH
        box_height = PAGE_WIDTH * height / width
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %s %s] "
            b"/Resources << /XObject << /Im0 %d 0 R >> >> /Contents %d 0 R >>"
            % (
                f"{box_width:g}".encode(),
                f"{box_height:g}".encode(),
                image_number,
                content_number,
            )
        )
        stream = b"q %s 0 0 %s 0 0 cm /Im0 Do Q" % (
            f"{box_width:g}".encode(),
            f"{box_height:g}".encode(),
        )
        objects.append(
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)
        )
        objects.append(
            b"<< /Type /XObject /Subtype /Image /Width %d /Height %d "
            b"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode "
            b"/Length %d >>\nstream\n%s\nendstream"
            % (width, height, len(jpeg), jpeg)
        )
    return _assemble(objects)


def make_xlsx(sheets: dict[str, list[list[object]]]) -> bytes:
    """Build a real .xlsx workbook in memory via openpyxl."""
    from openpyxl import Workbook

    workbook = Workbook()
    default = workbook.active
    first = True
    for name, rows in sheets.items():
        sheet = default if first else workbook.create_sheet()
        sheet.title = name
        first = False
        for row in rows:
            sheet.append(list(row))

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def make_plain_zip(names: dict[str, bytes] | None = None) -> bytes:
    """A structurally valid ZIP that is not an OOXML workbook."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in (names or {"readme.txt": b"not a workbook"}).items():
            archive.writestr(name, payload)
    return buffer.getvalue()


# --------------------------------------------------------------------------
# Balance Sheet content used across the identification and validation tests
# --------------------------------------------------------------------------

SIMPLE_BALANCE_SHEET_ROWS: list[list[object]] = [
    ["Acme Manufacturing Limited", None],
    ["Balance Sheet as at 31 March 2024", None],
    ["(All figures in INR)", None],
    [None, None],
    ["ASSETS", None],
    ["Cash and cash equivalents", "40,000"],
    ["Inventories", "60,000"],
    ["Property, plant and equipment", "50,000"],
    ["Total Assets", "150,000"],
    [None, None],
    ["LIABILITIES", None],
    ["Trade payables", "30,000"],
    ["Long-term borrowings", "60,000"],
    ["Total Liabilities", "90,000"],
    [None, None],
    ["SHAREHOLDERS' EQUITY", None],
    ["Share capital", "20,000"],
    ["Retained earnings", "40,000"],
    ["Total Shareholders' Equity", "60,000"],
]


def simple_balance_sheet_pdf() -> bytes:
    """A one-page digital Balance Sheet that balances: 150,000 = 90,000 + 60,000."""
    runs: list[Text] = []
    y = 740.0
    for label, value in SIMPLE_BALANCE_SHEET_ROWS:
        if label is not None:
            runs.append(Text(72, y, str(label)))
        if value is not None:
            runs.append(Text(420, y, str(value)))
        y -= 18.0
    return make_text_pdf([runs])


def comparative_balance_sheet_pdf() -> bytes:
    """A two-column comparative sheet: 2024 (current) beside 2023 (prior).

    Only the 2024 column may ever be analysed. The 2023 figures are
    deliberately made to balance too, so a test that reads the wrong column
    fails on the *value*, not on a balance error.
    """
    rows: list[tuple[str | None, str | None, str | None]] = [
        ("Acme Manufacturing Limited", None, None),
        ("Balance Sheet", None, None),
        (None, "31 March 2024", "31 March 2023"),
        ("ASSETS", None, None),
        ("Cash and cash equivalents", "40,000", "35,000"),
        ("Property, plant and equipment", "110,000", "85,000"),
        ("Total Assets", "150,000", "120,000"),
        ("LIABILITIES", None, None),
        ("Trade payables", "90,000", "70,000"),
        ("Total Liabilities", "90,000", "70,000"),
        ("SHAREHOLDERS' EQUITY", None, None),
        ("Share capital", "60,000", "50,000"),
        ("Total Shareholders' Equity", "60,000", "50,000"),
    ]
    runs: list[Text] = []
    y = 740.0
    for label, current, prior in rows:
        if label is not None:
            runs.append(Text(72, y, label))
        if current is not None:
            runs.append(Text(360, y, current))
        if prior is not None:
            runs.append(Text(470, y, prior))
        y -= 20.0
    return make_text_pdf([runs])


def simple_balance_sheet_xlsx() -> bytes:
    return make_xlsx({"Balance Sheet": SIMPLE_BALANCE_SHEET_ROWS})


def footer_balance_sheet_pdf(footer_label: str) -> bytes:
    """A Balance Sheet closing with a combined balancing footer.

    Shaped after a real filing: an uppercase ``TOTAL ASSETS``, a genuine
    ``Total Liabilities`` line, and a footer that restates assets. The footer
    label is a parameter because the trap is that it can be written a dozen
    ways - ``+``, ``&``, ``and``, either ordering - and every one of them
    contains the text "Total Liabilities".

    2,300,000 = 1,350,000 + 950,000, so reading the footer as the liabilities
    total makes a sheet that balances perfectly fail the equation check.
    """
    rows: list[tuple[str, str | None]] = [
        ("ABC Manufacturing Limited", None),
        ("Balance Sheet as at 31 March 2026", None),
        ("ASSETS", None),
        ("Cash and cash equivalents", "300,000"),
        ("Property, plant and equipment", "2,000,000"),
        ("TOTAL ASSETS", "2,300,000"),
        ("LIABILITIES", None),
        ("Trade payables", "350,000"),
        ("Long-term borrowings", "1,000,000"),
        ("Total Liabilities", "1,350,000"),
        ("EQUITY", None),
        ("Share capital", "500,000"),
        ("Retained earnings", "450,000"),
        ("Total Equity", "950,000"),
        (footer_label, "2,300,000"),
    ]
    runs: list[Text] = []
    y = 740.0
    for label, value in rows:
        runs.append(Text(72, y, label))
        if value is not None:
            runs.append(Text(420, y, value))
        y -= 18.0
    return make_text_pdf([runs])


def abc_manufacturing_balance_sheet_pdf() -> bytes:
    """The document shape that exposed the combined-footer bug."""
    return footer_balance_sheet_pdf("TOTAL LIABILITIES + EQUITY")


# Assets down the left of the page, Liabilities and Equity down the right - the
# horizontal ("T-account") layout, ordinary in Indian and UK presentations.
# Every total but one shares its visual row with an unrelated label, so a
# locator that reads only the left-hand cell finds nothing on the right.
#
# It balances: 2,300,000 = 1,350,000 + 950,000.
SIDE_BY_SIDE_ROWS: list[tuple[str | None, str | None, str | None, str | None]] = [
    ("Meridian Industries Limited", None, None, None),
    ("Balance Sheet as at 31 March 2026", None, None, None),
    ("ASSETS", None, "LIABILITIES AND EQUITY", None),
    ("Current Assets", None, "Current Liabilities", None),
    ("Cash and cash equivalents", "125,000", "Trade payables", "300,000"),
    ("Trade receivables", "280,000", "Short-term borrowings", "200,000"),
    ("Inventory", "350,000", "Other current liabilities", "150,000"),
    ("Other current assets", "95,000", "Total Current Liabilities", "650,000"),
    ("Total Current Assets", "850,000", "Non-Current Liabilities", None),
    ("Non-Current Assets", None, "Long-term borrowings", "600,000"),
    ("Property, plant and equipment", "1,200,000", "Other non-current liabilities", "100,000"),
    # The line the defect was reported on: a genuine grand total, printed
    # opposite an unrelated assets line.
    ("Intangible assets", "150,000", "Total Liabilities", "1,350,000"),
    ("Other non-current assets", "100,000", "Equity", None),
    ("Total Non-Current Assets", "1,450,000", "Share capital", "600,000"),
    ("TOTAL ASSETS", "2,300,000", "Retained earnings", "350,000"),
    (None, None, "Total Equity", "950,000"),
    (None, None, "TOTAL LIABILITIES + EQUITY", "2,300,000"),
]


def side_by_side_balance_sheet_pdf() -> bytes:
    """A Balance Sheet printed as two columns of labels rather than one.

    The x positions leave a gap between the assets figure and the liabilities
    label wide enough to read as a column break, which is what the real
    document does and what line reconstruction relies on.
    """
    runs: list[Text] = []
    y = 740.0
    for label, value, right_label, right_value in SIDE_BY_SIDE_ROWS:
        if label is not None:
            runs.append(Text(60, y, label))
        if value is not None:
            runs.append(Text(230, y, value))
        if right_label is not None:
            runs.append(Text(320, y, right_label))
        if right_value is not None:
            runs.append(Text(500, y, right_value))
        y -= 18.0
    return make_text_pdf([runs])


# --------------------------------------------------------------------------
# Rendered-image fixtures, for OCR
# --------------------------------------------------------------------------


def _ocr_font(size: int):
    """A scalable font Tesseract can actually read.

    Pillow's legacy default is a 11px bitmap that OCR mangles. A real system
    face is preferred; ``load_default(size)`` (Pillow 10.1+) returns the
    bundled scalable Aileron face and keeps this working off-Windows.
    """
    from PIL import ImageFont

    for candidate in (
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def render_rows_to_image(
    rows: list[tuple[str, ...]],
    *,
    columns: tuple[int, ...] = (60, 700),
    width: int = 1100,
    row_height: int = 52,
    font_size: int = 30,
):
    """Draw label/figure rows as a black-on-white page image.

    This is what a scanned filing looks like to the system: pixels, no text
    layer. Generous size and spacing are deliberate - the tests are checking
    *our* line and column reconstruction, not Tesseract's limits on bad scans.
    """
    from PIL import Image, ImageDraw

    height = 80 + row_height * len(rows)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = _ocr_font(font_size)

    y = 40
    for row in rows:
        for index, cell in enumerate(row):
            if not cell:
                continue
            x = columns[index] if index < len(columns) else columns[-1]
            draw.text((x, y), cell, fill="black", font=font)
        y += row_height
    return image


def image_to_jpeg(image) -> tuple[bytes, int, int]:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95)
    return buffer.getvalue(), image.width, image.height


SCANNED_ROWS: list[tuple[str, ...]] = [
    ("Acme Manufacturing Limited",),
    ("Balance Sheet as at 31 March 2024",),
    ("ASSETS",),
    ("Cash and cash equivalents", "40,000"),
    ("Property plant and equipment", "110,000"),
    ("Total Assets", "150,000"),
    ("LIABILITIES",),
    ("Trade payables", "90,000"),
    ("Total Liabilities", "90,000"),
    ("EQUITY",),
    ("Share capital", "60,000"),
    ("Total Equity", "60,000"),
]


def scanned_balance_sheet_image():
    """A page image of a Balance Sheet that balances: 150,000 = 90,000 + 60,000."""
    return render_rows_to_image(SCANNED_ROWS)


def scanned_balance_sheet_pdf() -> bytes:
    """A PDF whose single page is that image - no text layer whatsoever."""
    return make_image_pdf([image_to_jpeg(scanned_balance_sheet_image())])


def blank_scanned_pdf() -> bytes:
    """A scanned page carrying no legible content.

    Readable as a container, unreadable as a document - the case that must be
    reported honestly rather than passed off as an empty Balance Sheet.
    """
    from PIL import Image

    return make_image_pdf([image_to_jpeg(Image.new("RGB", (900, 1200), "white"))])


__all__ = [
    "PAGE_HEIGHT",
    "PAGE_WIDTH",
    "SIDE_BY_SIDE_ROWS",
    "SIMPLE_BALANCE_SHEET_ROWS",
    "Text",
    "abc_manufacturing_balance_sheet_pdf",
    "comparative_balance_sheet_pdf",
    "footer_balance_sheet_pdf",
    "make_image_pdf",
    "make_plain_zip",
    "make_text_pdf",
    "make_xlsx",
    "side_by_side_balance_sheet_pdf",
    "simple_balance_sheet_pdf",
    "simple_balance_sheet_xlsx",
]
