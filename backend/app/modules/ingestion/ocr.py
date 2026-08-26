"""OCR for scanned Balance Sheet pages.

A Balance Sheet is a two-dimensional document. The label sits on the left and
its figure sits far to the right, and in a comparative filing *which column*
the figure is in is what decides which reporting period it belongs to. All of
that lives in the geometry, so this module keeps word positions and rebuilds
lines from them rather than accepting Tesseract's flat reading order.

That is not a theoretical concern. Run ``image_to_string`` over a rendered
two-column Balance Sheet and it returns every label, then every figure, in two
separate runs - the pairing between them destroyed. Reconstructing rows from
word boxes is the difference between a usable extraction and a scrambled one.

:class:`OcrEngine` is the seam. Tesseract is what we use; nothing outside this
module names it, so swapping engines means writing one class.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from statistics import median
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from app.core.errors import BalanceSheetError
from app.core.schemas import PositionedWord

if TYPE_CHECKING:  # pragma: no cover - typing only
    from PIL.Image import Image

logger = logging.getLogger(__name__)

# Tesseract reports -1 for non-word boxes and low numbers for noise. Below this
# a "word" is more likely to be a speck of scanner dust than a character.
MIN_WORD_CONFIDENCE = 30.0

# Two words belong to the same visual row when their vertical centres are
# within this fraction of a typical word's height. Loose enough to survive the
# baseline jitter of a scan, tight enough not to merge adjacent rows.
LINE_GROUPING_TOLERANCE = 0.6


class OcrUnavailable(BalanceSheetError):
    """The document needs OCR and no OCR engine can run.

    Deliberately an error. A scanned page silently yielding no text would be
    indistinguishable from a blank page, and the system would go on to report
    'not a Balance Sheet' - a verdict it did not actually reach. Refusing
    loudly is the only honest outcome.
    """

    status_code = 503
    code = "ocr_unavailable"


@dataclass
class OcrLine:
    """One reconstructed visual row, its words ordered left to right."""

    words: list[PositionedWord] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)

    @property
    def top(self) -> float:
        return min(word.top for word in self.words)

    @property
    def bottom(self) -> float:
        return max(word.top + word.height for word in self.words)

    def words_right_of(self, x: float) -> list[PositionedWord]:
        """Words starting to the right of ``x`` - i.e. in a later column."""
        return [word for word in self.words if word.left >= x]


@dataclass
class OcrPage:
    """What one recognised page yielded."""

    words: list[PositionedWord] = field(default_factory=list)
    lines: list[OcrLine] = field(default_factory=list)
    width: int = 0
    height: int = 0

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    @property
    def confidence(self) -> float | None:
        scored = [word.confidence for word in self.words if word.confidence is not None]
        if not scored:
            return None
        return sum(scored) / len(scored)


@runtime_checkable
class OcrEngine(Protocol):
    """Recognises text, with positions, in a page image."""

    name: str

    def available(self) -> bool:
        """Whether this engine can actually run right now."""
        ...

    def recognise(self, image: Image) -> OcrPage: ...


def group_into_lines(
    words: list[PositionedWord], *, tolerance: float = LINE_GROUPING_TOLERANCE
) -> list[OcrLine]:
    """Rebuild visual rows from word boxes, top to bottom, left to right.

    Grouping is geometric rather than taken from Tesseract's ``block``/``par``/
    ``line`` numbering, because that numbering splits on layout: in a table it
    routinely puts the label column in one block and the figures column in
    another, so a row's label and its figure end up in different "lines". The
    vertical centre of the box is the thing that actually says which row a word
    is on.
    """
    if not words:
        return []

    band = median([word.height for word in words if word.height > 0] or [1]) * tolerance
    band = max(band, 1.0)

    ordered = sorted(words, key=lambda word: (word.top + word.height / 2, word.left))
    lines: list[list[PositionedWord]] = []
    current: list[PositionedWord] = []
    current_centre = 0.0

    for word in ordered:
        centre = word.top + word.height / 2
        if current and abs(centre - current_centre) > band:
            lines.append(current)
            current = []
        if not current:
            current_centre = centre
        else:
            # Track the running mean so a row that drifts downward across the
            # page does not split halfway along.
            current_centre = (current_centre * len(current) + centre) / (len(current) + 1)
        current.append(word)

    if current:
        lines.append(current)

    return [OcrLine(words=sorted(line, key=lambda word: word.left)) for line in lines]


class TesseractOcrEngine:
    """OCR via the Tesseract CLI, through pytesseract.

    The **Tesseract system binary** is a separate installation. The pip package
    is only a wrapper around a command line; installing ``pytesseract`` alone
    gives you nothing that can read an image.
    """

    name = "tesseract"

    def __init__(
        self,
        *,
        language: str = "eng",
        min_confidence: float = MIN_WORD_CONFIDENCE,
        binary: str | None = None,
    ) -> None:
        self.language = language
        self.min_confidence = min_confidence
        self.binary = binary

    def _pytesseract(self):
        import pytesseract

        if self.binary:
            pytesseract.pytesseract.tesseract_cmd = self.binary
        return pytesseract

    def available(self) -> bool:
        """Report whether the Tesseract binary can actually be invoked."""
        try:
            self._pytesseract().get_tesseract_version()
        except Exception as exc:  # noqa: BLE001 - any failure means unusable
            logger.warning("Tesseract is not usable: %s", exc)
            return False
        return True

    def recognise(self, image: Image) -> OcrPage:
        pytesseract = self._pytesseract()
        from pytesseract import Output

        try:
            data = pytesseract.image_to_data(
                image, lang=self.language, output_type=Output.DICT
            )
        except Exception as exc:  # noqa: BLE001 - wrapped, never surfaced raw
            logger.exception("Tesseract failed on a page")
            raise OcrUnavailable(
                "The OCR engine failed while reading a scanned page."
            ) from exc

        words: list[PositionedWord] = []
        for index, text in enumerate(data["text"]):
            stripped = text.strip()
            if not stripped:
                continue
            confidence = float(data["conf"][index])
            if confidence < self.min_confidence:
                continue
            words.append(
                PositionedWord(
                    text=stripped,
                    left=max(0.0, float(data["left"][index])),
                    top=max(0.0, float(data["top"][index])),
                    width=max(0.0, float(data["width"][index])),
                    height=max(0.0, float(data["height"][index])),
                    confidence=confidence,
                )
            )

        return OcrPage(
            words=words,
            lines=group_into_lines(words),
            width=image.width,
            height=image.height,
        )


def render_pdf_page(data: bytes, page_index: int, *, dpi: int = 300) -> Image:
    """Rasterise one PDF page for OCR.

    pypdfium2 rather than pdf2image: the wheel bundles the PDFium binary, so
    there is no Poppler system install to explain on top of Tesseract.
    """
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(data)
    try:
        page = document[page_index]
        bitmap = page.render(scale=dpi / 72)
        return bitmap.to_pil()
    finally:
        document.close()


def build_ocr_engine(language: str = "eng") -> OcrEngine:
    """Construct the configured OCR engine.

    Returns the engine whether or not it is usable; callers ask
    :meth:`OcrEngine.available` and raise :class:`OcrUnavailable` at the point
    where OCR is actually needed, so a document that never needs OCR is not
    blocked by a missing binary.
    """
    return TesseractOcrEngine(language=language)


__all__ = [
    "LINE_GROUPING_TOLERANCE",
    "MIN_WORD_CONFIDENCE",
    "OcrEngine",
    "OcrLine",
    "OcrPage",
    "OcrUnavailable",
    "TesseractOcrEngine",
    "build_ocr_engine",
    "group_into_lines",
    "render_pdf_page",
]
