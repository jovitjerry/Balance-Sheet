"""Reading the preliminary extraction back, wherever Module 1 put it.

Module 1 keeps raw parser output on the document, unless it is large enough to
threaten MongoDB's 16 MB document cap - OCR word boxes from a long scanned
filing can approach it - in which case the payload goes to file storage and the
document keeps a :class:`~app.core.schemas.StorageRef` instead.

**Which half a document took is not the caller's business.** Every module after
Module 1 wants the same thing: the pages. So the choice is resolved here, once,
and ``document.preliminary`` is never read directly anywhere else.

This lives in ``core`` because both Module 2 and Module 4 need it and it names
neither: ``StorageRef``, ``PreliminaryExtraction`` and ``FileStorage`` are all
``core`` types, which is exactly the test ``core`` applies to shared code.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.errors import StorageError
from app.core.schemas import BalanceSheetDocument, PreliminaryExtraction
from app.core.storage import FileStorage

logger = logging.getLogger(__name__)


async def load_preliminary(
    document: BalanceSheetDocument, *, storage: FileStorage | None = None
) -> PreliminaryExtraction | None:
    """The raw parser output for ``document``, or ``None`` if it has none.

    ``storage`` is needed only when the payload was offloaded. A document whose
    extraction is inline - the ordinary case - loads without one, so a caller
    that never meets a large scanned filing never has to wire a file store in.

    :raises StorageError: when the payload was offloaded and cannot be read -
        no file store was supplied, the object is gone, or it will not parse.
        Deliberately **not** ``None``: "I could not read it" and "there is
        nothing to read" are different facts, and returning the second for the
        first is what sends a caller off to report a perfectly good Balance
        Sheet as unreadable.
    """
    if document.preliminary is not None:
        # Already in hand. Never fetch what we are holding - and prefer it when
        # both are somehow present, since it is the object Module 1 built.
        return document.preliminary

    ref = document.preliminary_ref
    if ref is None:
        return None

    if storage is None:
        raise StorageError(
            "The preliminary extraction for this document was offloaded to "
            "storage, but no file store was supplied to read it back."
        )

    raw = await storage.open(ref)  # StorageError if the object is missing
    return _parse(raw, document_id=document.id)


def _parse(raw: bytes, *, document_id: str | None) -> PreliminaryExtraction:
    """Rebuild the model from its stored JSON.

    ``PreliminaryExtraction`` holds no monetary value - raw table cells stay
    strings and word geometry is floats - so plain JSON round-trips it exactly.
    It deliberately does **not** go through ``decode_from_mongo``: this payload
    never went through ``encode_for_mongo`` on the way out, and pushing it
    through the Decimal128 boundary would be inventing a conversion.
    """
    try:
        data: Any = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        # The stored bytes are corrupt or truncated. Logged with the id so it
        # can be found; the message stays free of paths and keys.
        logger.error(
            "Stored preliminary extraction for %s is not valid JSON: %s",
            document_id,
            exc,
        )
        raise StorageError(
            "The stored preliminary extraction could not be read."
        ) from exc

    try:
        return PreliminaryExtraction.model_validate(data)
    except Exception as exc:  # noqa: BLE001 - pydantic raises ValidationError
        logger.error(
            "Stored preliminary extraction for %s does not match the schema: %s",
            document_id,
            exc,
        )
        raise StorageError(
            "The stored preliminary extraction could not be read."
        ) from exc


__all__ = ["load_preliminary"]
