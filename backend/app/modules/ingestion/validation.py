"""Upload validation - the first gate in Module 1.

Two things happen here, and both are refusals *before* any parser sees the
bytes:

1. **Size, enforced while reading.** The cap is applied chunk by chunk, so an
   oversized upload is abandoned mid-stream rather than buffered in full and
   measured afterwards. Buffering first would make ``MAX_UPLOAD_BYTES`` a
   memory-exhaustion vector rather than a protection against one.

2. **Content, not just the extension.** A ``.pdf`` must actually begin with a
   PDF header and a ``.xlsx`` must actually be an OOXML workbook. Trusting the
   extension means handing a ZIP to a PDF parser because somebody renamed a
   file, which is parser confusion by another name.

Nothing here interprets the *document*. Whether a readable file is a Balance
Sheet is decided later, in :mod:`app.modules.ingestion.identification`.
"""

from __future__ import annotations

import io
import zipfile
from enum import Enum
from pathlib import PurePosixPath
from typing import Protocol

from app.core.config import Settings
from app.core.errors import InvalidUploadError

DEFAULT_CHUNK_SIZE = 1024 * 1024

# The PDF specification allows a header not to sit at byte zero, and real
# exporters do prepend bytes. Acrobat scans the first 1 KB; so do we.
PDF_HEADER = b"%PDF-"
PDF_HEADER_SEARCH_WINDOW = 1024

ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")

# Every OOXML package declares its parts here...
OOXML_CONTENT_TYPES = "[Content_Types].xml"
# ...and a *workbook* specifically has this part. A .docx passes the first
# check and fails this one, which is the distinction that matters.
XLSX_WORKBOOK_PART = "xl/workbook.xml"

# A ZIP declares its uncompressed sizes in the central directory, so a bomb can
# be spotted from the metadata alone - before a single byte is inflated. The
# floor keeps ordinary small workbooks (which compress extremely well, being
# XML) from tripping a pure ratio test.
MAX_ZIP_EXPANSION_RATIO = 200
MIN_ZIP_BOMB_BYTES = 64 * 1024 * 1024


class UploadKind(str, Enum):
    """What the bytes actually are, once verified."""

    PDF = "pdf"
    XLSX = "xlsx"


EXTENSION_KINDS: dict[str, UploadKind] = {
    ".pdf": UploadKind.PDF,
    ".xlsx": UploadKind.XLSX,
}


class AsyncByteReader(Protocol):
    """The slice of ``starlette.datastructures.UploadFile`` this module needs."""

    async def read(self, size: int = -1) -> bytes: ...


# --------------------------------------------------------------------------
# Size
# --------------------------------------------------------------------------


async def read_capped(
    source: AsyncByteReader,
    *,
    max_bytes: int,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> bytes:
    """Read an upload into memory, refusing it the moment it passes the cap.

    Peak memory is bounded at ``max_bytes + chunk_size``: the read stops at the
    chunk that crosses the limit and the rest of the stream is never pulled in.

    An empty upload is refused here too - there is nothing downstream that can
    do anything useful with zero bytes.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await source.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise InvalidUploadError(
                f"File exceeds the {max_bytes}-byte upload limit."
            )
        chunks.append(chunk)

    if total == 0:
        raise InvalidUploadError("The uploaded file is empty.")
    return b"".join(chunks)


# --------------------------------------------------------------------------
# Name
# --------------------------------------------------------------------------


def validate_filename(filename: str, settings: Settings) -> str:
    """Check the extension against the allow-list and return it, lower-cased.

    The filename is read for its suffix and for nothing else. It is never used
    to build a path - storage keys come from the content hash - so a traversal
    attempt in the name has nowhere to land.
    """
    if not filename or not filename.strip():
        raise InvalidUploadError("A filename is required.")

    extension = PurePosixPath(filename).suffix.lower()
    if extension not in settings.allowed_extensions:
        allowed = ", ".join(settings.allowed_extensions)
        raise InvalidUploadError(
            f"Unsupported file type {extension or '(none)'!r}. Allowed: {allowed}."
        )
    return extension


def validate_size(size_bytes: int, settings: Settings) -> None:
    if size_bytes <= 0:
        raise InvalidUploadError("The uploaded file is empty.")
    if size_bytes > settings.max_upload_bytes:
        raise InvalidUploadError(
            f"File is {size_bytes} bytes, exceeding the "
            f"{settings.max_upload_bytes}-byte limit."
        )


def validate_upload(filename: str, size_bytes: int, settings: Settings) -> str:
    """Validate name and size together, returning the extension.

    Kept as one call for the path where the whole body is already in hand.
    Streaming callers use :func:`read_capped` and :func:`validate_filename`
    separately, so the cap is applied before the bytes exist.
    """
    extension = validate_filename(filename, settings)
    validate_size(size_bytes, settings)
    return extension


# --------------------------------------------------------------------------
# Content
# --------------------------------------------------------------------------


def looks_like_pdf(data: bytes) -> bool:
    return PDF_HEADER in data[:PDF_HEADER_SEARCH_WINDOW]


def looks_like_zip(data: bytes) -> bool:
    return data[:4] in ZIP_MAGIC


def validate_content(data: bytes, extension: str) -> UploadKind:
    """Confirm the bytes are what ``extension`` claims, and say what they are.

    :raises InvalidUploadError: if the content contradicts the extension, or
        the container is structurally unusable.
    """
    kind = EXTENSION_KINDS.get(extension)
    if kind is None:  # pragma: no cover - validate_filename runs first
        raise InvalidUploadError(f"Unsupported file type {extension!r}.")

    if kind is UploadKind.PDF:
        if not looks_like_pdf(data):
            raise InvalidUploadError(
                "The file does not look like a PDF. Its contents do not match "
                "its .pdf extension."
            )
        return UploadKind.PDF

    if not looks_like_zip(data):
        raise InvalidUploadError(
            "The file does not look like an Excel workbook. A .xlsx file is a "
            "ZIP package, and this one is not."
        )
    _validate_xlsx_package(data)
    return UploadKind.XLSX


def _validate_xlsx_package(data: bytes) -> None:
    """Structurally verify an OOXML workbook without inflating it.

    Only the central directory is read. That is enough to tell a workbook from
    a ``.docx``, to reject a corrupt archive, and to spot a decompression bomb
    from its declared sizes - all before openpyxl is given the file.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            declared = sum(info.file_size for info in archive.infolist())
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        # Deliberately not chaining the message: zipfile's text can contain
        # offsets and internals that have no business in an API response.
        raise InvalidUploadError(
            "The Excel workbook could not be read. The file appears to be "
            "corrupt or incomplete."
        ) from exc

    if declared > MIN_ZIP_BOMB_BYTES and declared > len(data) * MAX_ZIP_EXPANSION_RATIO:
        raise InvalidUploadError(
            "The Excel workbook expands to an implausible size and was refused."
        )

    if OOXML_CONTENT_TYPES not in names or XLSX_WORKBOOK_PART not in names:
        raise InvalidUploadError(
            "The file is not a valid .xlsx workbook. It is a ZIP archive, but "
            "it does not contain an Excel workbook."
        )


__all__ = [
    "DEFAULT_CHUNK_SIZE",
    "EXTENSION_KINDS",
    "AsyncByteReader",
    "UploadKind",
    "looks_like_pdf",
    "looks_like_zip",
    "read_capped",
    "validate_content",
    "validate_filename",
    "validate_size",
    "validate_upload",
]
