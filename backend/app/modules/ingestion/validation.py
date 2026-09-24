from __future__ import annotations
import io
import zipfile
from enum import Enum
from pathlib import PurePosixPath
from typing import Protocol
from app.core.config import Settings
from app.core.errors import InvalidUploadError
DEFAULT_CHUNK_SIZE = 1024 * 1024
PDF_HEADER = b'%PDF-'
PDF_HEADER_SEARCH_WINDOW = 1024
ZIP_MAGIC = (b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08')
OOXML_CONTENT_TYPES = '[Content_Types].xml'
XLSX_WORKBOOK_PART = 'xl/workbook.xml'
MAX_ZIP_EXPANSION_RATIO = 200
MIN_ZIP_BOMB_BYTES = 64 * 1024 * 1024

class UploadKind(str, Enum):
    PDF = 'pdf'
    XLSX = 'xlsx'
EXTENSION_KINDS: dict[str, UploadKind] = {'.pdf': UploadKind.PDF, '.xlsx': UploadKind.XLSX}

class AsyncByteReader(Protocol):

    async def read(self, size: int=-1) -> bytes:
        ...

async def read_capped(source: AsyncByteReader, *, max_bytes: int, chunk_size: int=DEFAULT_CHUNK_SIZE) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await source.read(chunk_size)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise InvalidUploadError(f'File exceeds the {max_bytes}-byte upload limit.')
        chunks.append(chunk)
    if total == 0:
        raise InvalidUploadError('The uploaded file is empty.')
    return b''.join(chunks)

def validate_filename(filename: str, settings: Settings) -> str:
    if not filename or not filename.strip():
        raise InvalidUploadError('A filename is required.')
    extension = PurePosixPath(filename).suffix.lower()
    if extension not in settings.allowed_extensions:
        allowed = ', '.join(settings.allowed_extensions)
        raise InvalidUploadError(f"Unsupported file type {extension or '(none)'!r}. Allowed: {allowed}.")
    return extension

def validate_size(size_bytes: int, settings: Settings) -> None:
    if size_bytes <= 0:
        raise InvalidUploadError('The uploaded file is empty.')
    if size_bytes > settings.max_upload_bytes:
        raise InvalidUploadError(f'File is {size_bytes} bytes, exceeding the {settings.max_upload_bytes}-byte limit.')

def validate_upload(filename: str, size_bytes: int, settings: Settings) -> str:
    extension = validate_filename(filename, settings)
    validate_size(size_bytes, settings)
    return extension

def looks_like_pdf(data: bytes) -> bool:
    return PDF_HEADER in data[:PDF_HEADER_SEARCH_WINDOW]

def looks_like_zip(data: bytes) -> bool:
    return data[:4] in ZIP_MAGIC

def validate_content(data: bytes, extension: str) -> UploadKind:
    kind = EXTENSION_KINDS.get(extension)
    if kind is None:
        raise InvalidUploadError(f'Unsupported file type {extension!r}.')
    if kind is UploadKind.PDF:
        if not looks_like_pdf(data):
            raise InvalidUploadError('The file does not look like a PDF. Its contents do not match its .pdf extension.')
        return UploadKind.PDF
    if not looks_like_zip(data):
        raise InvalidUploadError('The file does not look like an Excel workbook. A .xlsx file is a ZIP package, and this one is not.')
    _validate_xlsx_package(data)
    return UploadKind.XLSX

def _validate_xlsx_package(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            declared = sum((info.file_size for info in archive.infolist()))
    except (zipfile.BadZipFile, OSError, ValueError) as exc:
        raise InvalidUploadError('The Excel workbook could not be read. The file appears to be corrupt or incomplete.') from exc
    if declared > MIN_ZIP_BOMB_BYTES and declared > len(data) * MAX_ZIP_EXPANSION_RATIO:
        raise InvalidUploadError('The Excel workbook expands to an implausible size and was refused.')
    if OOXML_CONTENT_TYPES not in names or XLSX_WORKBOOK_PART not in names:
        raise InvalidUploadError('The file is not a valid .xlsx workbook. It is a ZIP archive, but it does not contain an Excel workbook.')
__all__ = ['DEFAULT_CHUNK_SIZE', 'EXTENSION_KINDS', 'AsyncByteReader', 'UploadKind', 'looks_like_pdf', 'looks_like_zip', 'read_capped', 'validate_content', 'validate_filename', 'validate_size', 'validate_upload']
