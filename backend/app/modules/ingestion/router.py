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
router = APIRouter(prefix='/documents', tags=['documents'])

class DocumentNotFound(BalanceSheetError):
    status_code = status.HTTP_404_NOT_FOUND
    code = 'document_not_found'

@router.post('', status_code=status.HTTP_201_CREATED, response_model=BalanceSheetDocument)
async def upload_document(file: Annotated[UploadFile, File(description='Balance Sheet as PDF or .xlsx.')], settings: Annotated[Settings, Depends(get_settings_dep)], storage: Annotated[FileStorage, Depends(get_storage)], db: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_db)], ocr: Annotated[OcrEngine, Depends(get_ocr)], llm: Annotated[LlmProvider, Depends(get_llm)]) -> BalanceSheetDocument:
    document = await process_upload(file, filename=file.filename or '', content_type=file.content_type or 'application/octet-stream', storage=storage, db=db, settings=settings, ocr=ocr)
    if document.status is not DocumentStatus.VALIDATED:
        return document
    result = await run_pipeline(document, start_after=PipelineStage.INGEST, context=StageContext(llm=llm, settings=settings, storage=storage))
    await _store_pipeline_result(db, result.document)
    return result.document

async def _store_pipeline_result(db: AsyncDatabase[dict[str, Any]], document: BalanceSheetDocument) -> None:
    if document.id is None or document.extracted is None:
        return
    from app.core.money import encode_for_mongo
    changes: dict[str, Any] = {'extracted': document.extracted.model_dump(mode='python'), 'status': document.status.value, 'updated_at': utcnow()}
    if document.ratios is not None:
        changes['ratios'] = document.ratios.model_dump(mode='python')
    await db[BALANCE_SHEETS].update_one({'_id': ObjectId(document.id)}, {'$set': encode_for_mongo(changes)})

@router.get('/{document_id}', response_model=BalanceSheetDocument)
async def get_document(document_id: str, db: Annotated[AsyncDatabase[dict[str, Any]], Depends(get_db)]) -> BalanceSheetDocument:
    try:
        oid = ObjectId(document_id)
    except (InvalidId, TypeError) as exc:
        raise InvalidUploadError('Not a valid document id.') from exc
    found = await db[BALANCE_SHEETS].find_one({'_id': oid})
    if found is None:
        raise DocumentNotFound(f'No document with id {document_id}.')
    return BalanceSheetDocument.from_mongo(found)
__all__ = ['router']
