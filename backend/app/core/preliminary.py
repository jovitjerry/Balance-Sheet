from __future__ import annotations
import json
import logging
from typing import Any
from app.core.errors import StorageError
from app.core.schemas import BalanceSheetDocument, PreliminaryExtraction
from app.core.storage import FileStorage
logger = logging.getLogger(__name__)

async def load_preliminary(document: BalanceSheetDocument, *, storage: FileStorage | None=None) -> PreliminaryExtraction | None:
    if document.preliminary is not None:
        return document.preliminary
    ref = document.preliminary_ref
    if ref is None:
        return None
    if storage is None:
        raise StorageError('The preliminary extraction for this document was offloaded to storage, but no file store was supplied to read it back.')
    raw = await storage.open(ref)
    return _parse(raw, document_id=document.id)

def _parse(raw: bytes, *, document_id: str | None) -> PreliminaryExtraction:
    try:
        data: Any = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.error('Stored preliminary extraction for %s is not valid JSON: %s', document_id, exc)
        raise StorageError('The stored preliminary extraction could not be read.') from exc
    try:
        return PreliminaryExtraction.model_validate(data)
    except Exception as exc:
        logger.error('Stored preliminary extraction for %s does not match the schema: %s', document_id, exc)
        raise StorageError('The stored preliminary extraction could not be read.') from exc
__all__ = ['load_preliminary']
