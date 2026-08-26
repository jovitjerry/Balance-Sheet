"""Module 1 - Upload & Validation.

The whole workflow, in order:

    upload -> file validation -> content validation -> parse (OCR when needed)
    -> preliminary extraction -> current-period selection -> Balance Sheet
    identification -> locate the three totals -> accounting-equation check
    -> persist -> respond

Two things govern how this is written.

**State is persisted as it is reached, not at the end.** The document row is
created the moment the file is stored, and each stage updates it in place. A
crash during OCR therefore leaves a record saying the document was uploaded and
parsing was under way - not nothing at all.

**A refusal is a result, and results are kept.** A submission that turns out
not to be a Balance Sheet, or that does not balance, stays in the collection
with the evidence that produced the verdict. Deleting it would erase the audit
trail that makes the refusal reviewable.

What reaches the caller differs by *kind* of refusal - see :func:`process_upload`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings
from app.core.db import BALANCE_SHEETS
from app.core.errors import NotABalanceSheetError, UnreadableDocumentError
from app.core.money import encode_for_mongo
from app.core.schemas import (
    BalanceSheetDocument,
    BalanceSheetSection,
    DocumentStatus,
    ExtractedBalanceSheet,
    PreliminaryExtraction,
    Rejection,
    RejectionReason,
    SourceFile,
    ValidationSummary,
    utcnow,
)
from app.core.storage import FileStorage, key_for, sha256_of
from app.modules.ingestion.equation import check_equation
from app.modules.ingestion.identification import (
    LocatedTotals,
    detect_units,
    is_balance_sheet,
    locate_totals,
    select_period,
)
from app.modules.ingestion.ocr import OcrEngine, OcrUnavailable
from app.modules.ingestion.parsing import parse
from app.modules.ingestion.validation import (
    AsyncByteReader,
    read_capped,
    validate_content,
    validate_filename,
    validate_upload,
)

logger = logging.getLogger(__name__)

PRELIMINARY_SUFFIX = ".preliminary.json"


# --------------------------------------------------------------------------
# The full workflow
# --------------------------------------------------------------------------


async def process_upload(
    source: AsyncByteReader,
    *,
    filename: str,
    content_type: str,
    storage: FileStorage,
    db: AsyncDatabase[dict[str, Any]],
    settings: Settings,
    ocr: OcrEngine | None = None,
) -> BalanceSheetDocument:
    """Run a Balance Sheet submission through Module 1 end to end.

    Refusals divide in two, which is what decides the HTTP status the router
    returns:

    * **Not a Balance Sheet at all** - unreadable, or a Cash Flow Statement.
      There is nothing here to review, so this raises, and the router answers
      4xx. The record is still written and marked ``REJECTED``.
    * **A Balance Sheet that fails validation** - a missing total, or one that
      does not balance. That verdict *is* the useful answer, so it returns
      normally with the evidence attached and the router answers 201. The
      caller can see exactly which check failed and by how much.

    Re-uploading identical bytes returns the existing document rather than
    reprocessing it - storage keys are content-addressed, so this comes free.
    """
    extension = validate_filename(filename, settings)
    data = await read_capped(source, max_bytes=settings.max_upload_bytes)
    kind = validate_content(data, extension)

    document = await ingest(
        data,
        filename=filename,
        content_type=content_type,
        storage=storage,
        db=db,
        settings=settings,
    )
    if document.status is not DocumentStatus.UPLOADED:
        # Already processed on an earlier upload of the same bytes.
        return document

    preliminary = await _parse_stage(
        data, document, kind=kind, storage=storage, db=db, settings=settings, ocr=ocr
    )
    return await _validate_stage(preliminary, document, db=db, settings=settings)


# --------------------------------------------------------------------------
# Stage 1 - store the file and open the record
# --------------------------------------------------------------------------


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

    Returns a document at status ``UPLOADED``, written before any parsing is
    attempted so that a failure later still leaves a trace of the submission.

    Re-uploading identical bytes returns the existing document rather than
    creating a duplicate - storage keys are content-addressed, so this comes
    for free.
    """
    validate_upload(filename, len(data), settings)
    extension = validate_filename(filename, settings)
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


# --------------------------------------------------------------------------
# Stage 2 - parse
# --------------------------------------------------------------------------


async def _parse_stage(
    data: bytes,
    document: BalanceSheetDocument,
    *,
    kind: Any,
    storage: FileStorage,
    db: AsyncDatabase[dict[str, Any]],
    settings: Settings,
    ocr: OcrEngine | None,
) -> PreliminaryExtraction:
    try:
        preliminary = await parse(data, document.source, kind=kind, settings=settings, ocr=ocr)
    except UnreadableDocumentError as exc:
        await _reject(
            document, db, reason=RejectionReason.UNREADABLE, message=exc.message
        )
        raise
    except OcrUnavailable:
        # Not a rejection: the document may be perfectly valid and the server
        # is what is missing a capability. Recording it as REJECTED would blame
        # the submission for an operational problem.
        await _mark_failed(document, db, "OCR was required but unavailable.")
        raise

    document.preliminary = preliminary
    document.status = DocumentStatus.PARSED

    updates: dict[str, Any] = {"status": DocumentStatus.PARSED.value}
    dumped = preliminary.model_dump(mode="python", exclude_none=True)
    if _payload_size(dumped) > settings.max_prelim_inline_bytes:
        # MongoDB caps a document at 16 MB, and OCR word boxes from a long
        # scanned filing can approach it. Spilling to file storage keeps the
        # raw output rather than truncating it.
        ref = await storage.save(
            json.dumps(dumped, default=str).encode("utf-8"),
            key=key_for(document.source.sha256, PRELIMINARY_SUFFIX),
            content_type="application/json",
        )
        document.preliminary_ref = ref
        updates["preliminary_ref"] = ref.model_dump(mode="python")
        logger.info("Preliminary extraction offloaded to storage for %s", document.id)
    else:
        updates["preliminary"] = dumped

    await _set(db, document.id, updates)
    return preliminary


def _payload_size(dumped: dict[str, Any]) -> int:
    return len(json.dumps(dumped, default=str).encode("utf-8"))


# --------------------------------------------------------------------------
# Stage 3 - identify, select the period, locate totals, check the equation
# --------------------------------------------------------------------------


async def _validate_stage(
    preliminary: PreliminaryExtraction,
    document: BalanceSheetDocument,
    *,
    db: AsyncDatabase[dict[str, Any]],
    settings: Settings,
) -> BalanceSheetDocument:
    evidence = is_balance_sheet(preliminary)
    document.identification = evidence
    await _set(db, document.id, {"identification": evidence.model_dump(mode="python")})

    if not evidence.is_balance_sheet:
        message = (
            "The document was read successfully but is not a Balance Sheet. "
            "This system reviews Balance Sheets only."
        )
        await _reject(
            document, db, reason=RejectionReason.NOT_A_BALANCE_SHEET, message=message
        )
        raise NotABalanceSheetError(message)

    period = select_period(preliminary)
    units = detect_units(preliminary)
    document.period = period
    document.units = units
    await _set(
        db,
        document.id,
        {
            key: value.model_dump(mode="python")
            for key, value in (("period", period), ("units", units))
            if value is not None
        },
    )

    totals = locate_totals(preliminary, period=period)
    if not totals.complete:
        return await _reject_incomplete(document, db, totals, period, units)

    equation = check_equation(
        totals.assets.value,
        totals.liabilities.value,
        totals.equity.value,
        tolerance_abs=settings.equation_tolerance_abs,
        tolerance_rel=settings.equation_tolerance_rel,
    )
    extracted = _extracted_from(totals, period, units)
    summary = ValidationSummary(
        required_fields_present=True,
        missing_fields=[],
        equation_balanced=equation.balanced,
        passed=equation.balanced,
    )

    document.extracted = extracted
    document.equation_check = equation
    document.validation = summary
    updates: dict[str, Any] = {
        "extracted": extracted.model_dump(mode="python", exclude_none=True),
        "equation_check": equation.model_dump(mode="python"),
        "validation": summary.model_dump(mode="python"),
    }

    if equation.balanced:
        document.status = DocumentStatus.VALIDATED
        updates["status"] = DocumentStatus.VALIDATED.value
        await _set(db, document.id, updates)
        return document

    rejection = Rejection(
        reason=RejectionReason.EQUATION_UNBALANCED,
        message=(
            "The accounting equation does not hold: Total Assets do not equal "
            "Total Liabilities plus Total Equity. The difference is recorded "
            "against the document."
        ),
    )
    document.status = DocumentStatus.REJECTED
    document.rejection = rejection
    updates["status"] = DocumentStatus.REJECTED.value
    updates["rejection"] = rejection.model_dump(mode="python")
    await _set(db, document.id, updates)
    return document


async def _reject_incomplete(
    document: BalanceSheetDocument,
    db: AsyncDatabase[dict[str, Any]],
    totals: LocatedTotals,
    period: Any,
    units: Any,
) -> BalanceSheetDocument:
    """A Balance Sheet whose totals could not all be found.

    Returned rather than raised: it is a Balance Sheet, and naming which total
    is missing is a more useful answer than a bare refusal. No equation check
    is attempted - inventing a zero for the missing figure would produce a
    verdict the document does not support.
    """
    summary = ValidationSummary(
        required_fields_present=False,
        missing_fields=totals.missing,
        equation_balanced=None,
        passed=False,
    )
    missing = ", ".join(f"Total {name.capitalize()}" for name in totals.missing)
    rejection = Rejection(
        reason=RejectionReason.MISSING_REQUIRED_FIELDS,
        message=f"The Balance Sheet is missing a required total: {missing}.",
    )

    document.validation = summary
    document.rejection = rejection
    document.status = DocumentStatus.REJECTED
    await _set(
        db,
        document.id,
        {
            "status": DocumentStatus.REJECTED.value,
            "validation": summary.model_dump(mode="python"),
            "rejection": rejection.model_dump(mode="python"),
        },
    )
    return document


def _extracted_from(totals: LocatedTotals, period: Any, units: Any) -> ExtractedBalanceSheet:
    """Build the structured record Module 1 is responsible for.

    Section totals only. ``line_items`` stays empty on every section: complete
    line-item extraction is Module 2's job, and filling anything in here would
    be pretending to a completeness this stage does not have.
    """

    def section(total: Any) -> BalanceSheetSection:
        return BalanceSheetSection(
            total=total.value,
            total_label=total.label,
            total_raw=total.raw,
            total_source=total.source,
            line_items=[],
        )

    return ExtractedBalanceSheet(
        period_label=period.selected.label if period else None,
        period_end_date=period.selected.end_date if period else None,
        currency=units.currency if units else None,
        assets=section(totals.assets),
        liabilities=section(totals.liabilities),
        equity=section(totals.equity),
    )


# --------------------------------------------------------------------------
# Persistence helpers
# --------------------------------------------------------------------------


async def _set(
    db: AsyncDatabase[dict[str, Any]], document_id: str | None, values: dict[str, Any]
) -> None:
    """Write one stage's result, encoding at the storage boundary."""
    if not document_id or not values:
        return
    payload = dict(values)
    payload["updated_at"] = utcnow()
    await db[BALANCE_SHEETS].update_one(
        {"_id": ObjectId(document_id)}, {"$set": encode_for_mongo(payload)}
    )


async def _reject(
    document: BalanceSheetDocument,
    db: AsyncDatabase[dict[str, Any]],
    *,
    reason: RejectionReason,
    message: str,
) -> None:
    """Record a refusal against the document. The record is kept, not deleted."""
    rejection = Rejection(reason=reason, message=message)
    document.status = DocumentStatus.REJECTED
    document.rejection = rejection
    await _set(
        db,
        document.id,
        {
            "status": DocumentStatus.REJECTED.value,
            "rejection": rejection.model_dump(mode="python"),
        },
    )


async def _mark_failed(
    document: BalanceSheetDocument, db: AsyncDatabase[dict[str, Any]], message: str
) -> None:
    """Record a processing failure that is ours, not the submission's."""
    document.status = DocumentStatus.FAILED
    document.errors = [*document.errors, message]
    await _set(
        db,
        document.id,
        {"status": DocumentStatus.FAILED.value, "errors": document.errors},
    )


__all__ = ["ingest", "process_upload", "validate_upload"]
