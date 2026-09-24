from __future__ import annotations
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

class BalanceSheetError(Exception):
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = 'internal_error'

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

class InvalidUploadError(BalanceSheetError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = 'invalid_upload'

class UnreadableDocumentError(BalanceSheetError):
    status_code = 422
    code = 'unreadable_document'

class NotABalanceSheetError(BalanceSheetError):
    status_code = 422
    code = 'not_a_balance_sheet'

class StorageError(BalanceSheetError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = 'storage_error'

class StageNotImplemented(BalanceSheetError):
    status_code = status.HTTP_501_NOT_IMPLEMENTED
    code = 'stage_not_implemented'

def register_exception_handlers(app: FastAPI) -> None:

    @app.exception_handler(BalanceSheetError)
    async def _handle(_: Request, exc: BalanceSheetError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={'error': {'code': exc.code, 'message': exc.message}})
__all__ = ['BalanceSheetError', 'InvalidUploadError', 'NotABalanceSheetError', 'StageNotImplemented', 'StorageError', 'UnreadableDocumentError', 'register_exception_handlers']
