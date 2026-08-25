"""Domain exceptions and their HTTP representation."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class BalanceSheetError(Exception):
    """Base class for this application's domain errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidUploadError(BalanceSheetError):
    """The uploaded file was rejected before any parsing was attempted."""

    status_code = status.HTTP_400_BAD_REQUEST
    code = "invalid_upload"


class UnreadableDocumentError(BalanceSheetError):
    """The file was accepted but could not be parsed into text or tables."""

    status_code = 422  # Unprocessable Content; the named constant was renamed
    code = "unreadable_document"


class NotABalanceSheetError(BalanceSheetError):
    """The document parsed, but is not recognisable as a Balance Sheet."""

    status_code = 422  # Unprocessable Content; the named constant was renamed
    code = "not_a_balance_sheet"


class StorageError(BalanceSheetError):
    """The file store could not satisfy the request."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    code = "storage_error"


class StageNotImplemented(BalanceSheetError):
    """A pipeline stage exists but its module has not been built yet.

    Deliberately distinct from a failure: "not built yet" must never be
    reported as either success or an error in the data.
    """

    status_code = status.HTTP_501_NOT_IMPLEMENTED
    code = "stage_not_implemented"


def register_exception_handlers(app: FastAPI) -> None:
    """Render :class:`BalanceSheetError` subclasses as structured JSON."""

    @app.exception_handler(BalanceSheetError)
    async def _handle(_: Request, exc: BalanceSheetError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )


__all__ = [
    "BalanceSheetError",
    "InvalidUploadError",
    "NotABalanceSheetError",
    "StageNotImplemented",
    "StorageError",
    "UnreadableDocumentError",
    "register_exception_handlers",
]
