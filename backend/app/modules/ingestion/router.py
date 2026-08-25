"""Module 1 HTTP routes."""

from __future__ import annotations

from typing import Annotated, Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, File, UploadFile, status
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings
from app.core.db import BALANCE_SHEETS
from app.core.deps import get_db, get_settings_dep, get_storage
from app.core.errors import BalanceSheetError, InvalidUploadError
from app.core.schemas import BalanceSheetDocument
from app.core.storage import FileStorage
from app.modules.ingestion.service import ingest

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentNotFound(BalanceSheetError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "document_not_found"


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BalanceSheetDocument)
async def upload_document(
    file: Annotated[UploadFile, File(description="Balance Sheet as PDF or Excel.")],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    storage: Annotated[FileStorage, Depends(get_storage)],
    db: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_db)],
) -> BalanceSheetDocument:
    """Upload a Balance Sheet.

    Validates the file, stores the original outside MongoDB, and records the
    document at status ``uploaded``. Parsing, OCR and extraction are not
    implemented yet, so the document does not advance past that.
    """
    data = await file.read()
    return await ingest(
        data,
        filename=file.filename or "",
        content_type=file.content_type or "application/octet-stream",
        storage=storage,
        db=db,
        settings=settings,
    )


@router.get("/{document_id}", response_model=BalanceSheetDocument)
async def get_document(
    document_id: str,
    db: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_db)],
) -> BalanceSheetDocument:
    """Fetch a stored document by id."""
    try:
        oid = ObjectId(document_id)
    except (InvalidId, TypeError) as exc:
        raise InvalidUploadError(f"Not a valid document id: {document_id!r}") from exc

    found = await db[BALANCE_SHEETS].find_one({"_id": oid})
    if found is None:
        raise DocumentNotFound(f"No document with id {document_id}.")
    return BalanceSheetDocument.from_mongo(found)


__all__ = ["router"]
