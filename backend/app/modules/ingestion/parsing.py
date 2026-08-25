"""PDF / Excel parsing and OCR for Module 1.

NOT IMPLEMENTED. This is a documented contract only.

When built, this produces a :class:`~app.core.schemas.PreliminaryExtraction`:
raw per-page text and tables, with table cells kept as **strings** exactly as
printed, plus OCR metadata. Module 2 re-derives structured data from that
output, so nothing here may normalise or interpret values.

Dependencies are deliberately not yet in ``requirements.txt``. They arrive with
the implementation - and note that OCR needs the **Tesseract system binary**,
not just a pip package.
"""

from __future__ import annotations

from app.core.errors import StageNotImplemented
from app.core.schemas import PreliminaryExtraction, SourceFile


async def parse(data: bytes, source: SourceFile) -> PreliminaryExtraction:
    """Parse an uploaded file into raw text and tables.

    Selects text extraction, OCR, or the Excel reader based on the file and on
    whether a PDF yields usable text.

    :raises StageNotImplemented: always, until Module 1 parsing is built.
    """
    raise StageNotImplemented(
        "PDF/Excel parsing and OCR are not implemented yet (Module 1, pending)."
    )


__all__ = ["parse"]
