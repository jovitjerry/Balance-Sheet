"""Module 1 HTTP routes.

Responses carry the verdict and the evidence behind it, and nothing else. No
stack trace, no filesystem path, no connection string, no parser internals -
every error a caller can see is a message this module wrote deliberately.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, File, UploadFile, status
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings
from app.core.db import BALANCE_SHEETS
from app.core.deps import get_db, get_llm, get_ocr, get_settings_dep, get_storage
from app.core.errors import BalanceSheetError, InvalidUploadError
from app.core.llm.base import LlmProvider
from app.core.pipeline import DocumentStatus, PipelineStage, StageContext, run_pipeline
from app.core.schemas import BalanceSheetDocument, utcnow
from app.core.storage import FileStorage
from app.modules.ingestion.ocr import OcrEngine
from app.modules.ingestion.service import process_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentNotFound(BalanceSheetError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "document_not_found"


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BalanceSheetDocument)
async def upload_document(
    file: Annotated[UploadFile, File(description="Balance Sheet as PDF or .xlsx.")],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    storage: Annotated[FileStorage, Depends(get_storage)],
    db: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_db)],
    ocr: Annotated[OcrEngine, Depends(get_ocr)],
    llm: Annotated[LlmProvider, Depends(get_llm)],
) -> BalanceSheetDocument:
    """Upload a Balance Sheet and run the pipeline over it.

    Validates the file and its actual content, stores the original outside
    MongoDB, parses it (using OCR for scanned pages), identifies it as a
    Balance Sheet, selects the most recent reporting period, locates the three
    section totals and checks the accounting equation.

    **201** - the document is a Balance Sheet and was processed. Its ``status``
    says whether it passed: ``validated`` if the equation holds, ``rejected``
    with a ``rejection`` and a ``validation`` summary if a total is missing or
    the sheet does not balance. Either way the figures and their sources are on
    the document.

    **400** - the upload itself was refused: wrong type, empty, too large, or
    contents that do not match the extension.

    **422** - the file could not be read, or is not a Balance Sheet.

    A document that passes Module 1 continues into Module 2, which extracts
    every line item and maps its terminology onto the canonical vocabulary;
    ``status`` is then ``extracted``. Labels the local model could not resolve -
    or that it could not be asked about, because Ollama is not running - are
    marked ``needs_review`` on the item rather than guessed at.

    **503** - the document needs OCR and this server cannot run it, or
    ``LLM_REQUIRED`` is set and the local model is unreachable.
    """
    # The body is streamed and size-capped inside process_upload, so an
    # oversized file is abandoned mid-read rather than buffered and measured.
    document = await process_upload(
        file,
        filename=file.filename or "",
        content_type=file.content_type or "application/octet-stream",
        storage=storage,
        db=db,
        settings=settings,
        ocr=ocr,
    )

    if document.status is not DocumentStatus.VALIDATED:
        # Rejected or unbalanced. The verdict and its evidence are the result;
        # extracting line items from a sheet Module 1 refused would be work
        # done on a document nobody should be reading figures out of.
        return document

    # Chained through core.pipeline rather than by importing Module 2 here:
    # Module 1 must not depend on a later module, and the pipeline is the one
    # place whose job is to know the order they run in.
    result = await run_pipeline(
        document,
        start_after=PipelineStage.INGEST,
        context=StageContext(llm=llm, settings=settings),
    )
    await _store_extraction(db, result.document)
    return result.document


async def _store_extraction(
    db: AsyncDatabase[dict[str, Any]], document: BalanceSheetDocument
) -> None:
    """Persist what Module 2 added, in place.

    Written as its own step for the same reason Module 1 persists at every
    transition: a crash after a long normalization run should leave the work on
    the document, not only in the response that never arrived.
    """
    if document.id is None or document.extracted is None:  # pragma: no cover
        return

    from app.core.money import encode_for_mongo

    await db[BALANCE_SHEETS].update_one(
        {"_id": ObjectId(document.id)},
        {
            "$set": encode_for_mongo(
                {
                    "extracted": document.extracted.model_dump(mode="python"),
                    "status": document.status.value,
                    "updated_at": utcnow(),
                }
            )
        },
    )


@router.get("/{document_id}", response_model=BalanceSheetDocument)
async def get_document(
    document_id: str,
    db: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_db)],
) -> BalanceSheetDocument:
    """Fetch a stored document by id.

    Rejected submissions are retrievable too - they are kept for audit, not
    discarded.
    """
    try:
        oid = ObjectId(document_id)
    except (InvalidId, TypeError) as exc:
        raise InvalidUploadError("Not a valid document id.") from exc

    found = await db[BALANCE_SHEETS].find_one({"_id": oid})
    if found is None:
        raise DocumentNotFound(f"No document with id {document_id}.")
    return BalanceSheetDocument.from_mongo(found)


__all__ = ["router"]
