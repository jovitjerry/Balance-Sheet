"""Module 1 - Upload & Validation.

Implemented here: file validation, content hashing, storage of the original
file, and creation of the MongoDB record.

Not implemented: parsing, OCR, Balance Sheet identification, and field
extraction. Those live in ``parsing.py`` and ``identification.py`` and raise
``StageNotImplemented``.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings
from app.core.db import BALANCE_SHEETS
from app.core.errors import InvalidUploadError
from app.core.schemas import BalanceSheetDocument, DocumentStatus, SourceFile
from app.core.storage import FileStorage, key_for, sha256_of


def validate_upload(
    filename: str,
    size_bytes: int,
    settings: Settings,
) -> str:
    """Validate an upload before anything is stored, returning its extension.

    Checks the extension against the allow-list and the size against the cap.
    The filename is inspected only to read its suffix; it is never used to
    build a path.
    """
    if not filename or not filename.strip():
        raise InvalidUploadError("A filename is required.")

    extension = PurePosixPath(filename).suffix.lower()
    if extension not in settings.allowed_extensions:
        allowed = ", ".join(settings.allowed_extensions)
        raise InvalidUploadError(
            f"Unsupported file type {extension or '(none)'!r}. Allowed: {allowed}."
        )

    if size_bytes <= 0:
        raise InvalidUploadError("The uploaded file is empty.")
    if size_bytes > settings.max_upload_bytes:
        raise InvalidUploadError(
            f"File is {size_bytes} bytes, exceeding the "
            f"{settings.max_upload_bytes}-byte limit."
        )

    return extension


async def ingest(
    data: bytes,
    *,
    filename: str,
    content_type: str,
    storage: FileStorage,
    db: AsyncDatabase[dict[str, Any]],
    settings: Settings,
) -> BalanceSheetDocument:
    """Validate, store, and record an uploaded Balance Sheet.

    Returns a document at status ``UPLOADED``. Advancing it further requires
    parsing, which is not implemented yet.

    Re-uploading identical bytes returns the existing document rather than
    creating a duplicate - storage keys are content-addressed, so this comes
    for free.
    """
    extension = validate_upload(filename, len(data), settings)
    digest = sha256_of(data)

    existing = await db[BALANCE_SHEETS].find_one({"source.sha256": digest})
    if existing is not None:
        return BalanceSheetDocument.from_mongo(existing)

    ref = await storage.save(
        data, key=key_for(digest, extension), content_type=content_type
    )
    document = BalanceSheetDocument(
        status=DocumentStatus.UPLOADED,
        source=SourceFile(
            filename=filename,
            content_type=content_type,
            size_bytes=len(data),
            sha256=digest,
            ref=ref,
        ),
    )

    result = await db[BALANCE_SHEETS].insert_one(document.to_mongo())
    document.id = str(result.inserted_id)
    return document


__all__ = ["ingest", "validate_upload"]
