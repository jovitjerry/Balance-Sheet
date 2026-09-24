from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from app.core.errors import BalanceSheetError
from app.core.lines import WordRow, group_into_lines
from app.core.schemas import PositionedWord
if TYPE_CHECKING:
    from PIL.Image import Image
logger = logging.getLogger(__name__)
MIN_WORD_CONFIDENCE = 30.0

class OcrUnavailable(BalanceSheetError):
    status_code = 503
    code = 'ocr_unavailable'

@dataclass
class OcrPage:
    words: list[PositionedWord] = field(default_factory=list)
    lines: list[WordRow] = field(default_factory=list)
    width: int = 0
    height: int = 0

    @property
    def text(self) -> str:
        return '\n'.join((line.text for line in self.lines))

    @property
    def confidence(self) -> float | None:
        scored = [word.confidence for word in self.words if word.confidence is not None]
        if not scored:
            return None
        return sum(scored) / len(scored)

@runtime_checkable
class OcrEngine(Protocol):
    name: str

    def available(self) -> bool:
        ...

    def recognise(self, image: Image) -> OcrPage:
        ...

class TesseractOcrEngine:
    name = 'tesseract'

    def __init__(self, *, language: str='eng', min_confidence: float=MIN_WORD_CONFIDENCE, binary: str | None=None) -> None:
        self.language = language
        self.min_confidence = min_confidence
        self.binary = binary

    def _pytesseract(self):
        import pytesseract
        if self.binary:
            pytesseract.pytesseract.tesseract_cmd = self.binary
        return pytesseract

    def available(self) -> bool:
        try:
            self._pytesseract().get_tesseract_version()
        except Exception as exc:
            logger.warning('Tesseract is not usable: %s', exc)
            return False
        return True

    def recognise(self, image: Image) -> OcrPage:
        pytesseract = self._pytesseract()
        from pytesseract import Output
        try:
            data = pytesseract.image_to_data(image, lang=self.language, output_type=Output.DICT)
        except Exception as exc:
            logger.exception('Tesseract failed on a page')
            raise OcrUnavailable('The OCR engine failed while reading a scanned page.') from exc
        words: list[PositionedWord] = []
        for index, text in enumerate(data['text']):
            stripped = text.strip()
            if not stripped:
                continue
            confidence = float(data['conf'][index])
            if confidence < self.min_confidence:
                continue
            words.append(PositionedWord(text=stripped, left=max(0.0, float(data['left'][index])), top=max(0.0, float(data['top'][index])), width=max(0.0, float(data['width'][index])), height=max(0.0, float(data['height'][index])), confidence=confidence))
        return OcrPage(words=words, lines=group_into_lines(words), width=image.width, height=image.height)

def render_pdf_page(data: bytes, page_index: int, *, dpi: int=300) -> Image:
    import pypdfium2 as pdfium
    document = pdfium.PdfDocument(data)
    try:
        page = document[page_index]
        bitmap = page.render(scale=dpi / 72)
        return bitmap.to_pil()
    finally:
        document.close()

def build_ocr_engine(language: str='eng') -> OcrEngine:
    return TesseractOcrEngine(language=language)
__all__ = ['MIN_WORD_CONFIDENCE', 'OcrEngine', 'OcrPage', 'OcrUnavailable', 'TesseractOcrEngine', 'build_ocr_engine', 'render_pdf_page']
