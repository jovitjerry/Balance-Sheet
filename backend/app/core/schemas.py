"""The shared data model.

``BalanceSheetDocument`` is the single record every module reads and writes. It
is defined in ``core`` rather than in a module package precisely because it is
the contract between modules.

Scope reminder: **single reporting period only**. There is deliberately no list
of periods and no year-over-year structure here.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.money import Money


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DocumentStatus(str, Enum):
    """How far a document has progressed.

    Only the states this foundation can actually reach are declared. Modules
    2-4 add their own when they are built.
    """

    UPLOADED = "uploaded"
    PARSED = "parsed"
    VALIDATED = "validated"
    REJECTED = "rejected"
    FAILED = "failed"


class ParserKind(str, Enum):
    PDF_TEXT = "pdf_text"
    PDF_OCR = "pdf_ocr"
    EXCEL = "excel"


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------


class StorageRef(BaseModel):
    """A pointer to a file held outside MongoDB.

    Original uploads are never stored inline in a document.
    """

    backend: str = Field(description="Storage backend that owns this object, e.g. 'local'.")
    key: str = Field(description="Backend-relative key. Derived from the content hash.")
    size_bytes: int = Field(ge=0)
    content_type: str


class SourceFile(BaseModel):
    """Metadata about the uploaded file. The bytes live behind ``ref``."""

    filename: str = Field(description="Original client filename. Metadata ONLY - never used to build a path.")
    content_type: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    ref: StorageRef


# --------------------------------------------------------------------------
# Preliminary extraction - raw parser output, preserved for Module 2
# --------------------------------------------------------------------------


class SourceRef(BaseModel):
    """Where a figure came from, for traceability back to the document."""

    page_index: int = Field(ge=0, description="Page number, or sheet index for Excel.")
    row: int | None = None
    column: int | None = None


class RawTable(BaseModel):
    """A table exactly as the parser found it.

    Cells stay **strings**. Preserving ``"(2,300)"`` and ``"1,234.5"`` as
    printed keeps the parenthetical-negative and thousands-separator
    conventions recoverable; coercing to numbers here would destroy evidence
    Module 2 needs.
    """

    rows: list[list[str | None]] = Field(default_factory=list)


class SourcePage(BaseModel):
    index: int = Field(ge=0)
    name: str | None = Field(default=None, description="Sheet name for Excel; None for PDF.")
    text: str = ""
    tables: list[RawTable] = Field(default_factory=list)
    ocr_used: bool = False
    ocr_confidence: float | None = None


class PreliminaryExtraction(BaseModel):
    """Raw parser output plus source metadata.

    Kept alongside - never replaced by - the structured
    :class:`ExtractedBalanceSheet`, so Module 2 can re-derive from source and
    any extracted figure remains traceable.
    """

    parser: ParserKind
    pages: list[SourcePage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Structured extraction
# --------------------------------------------------------------------------


class LineItem(BaseModel):
    label: str = Field(description="The label as printed in the document.")
    value: Money
    source: SourceRef | None = None


class BalanceSheetSection(BaseModel):
    total: Money
    line_items: list[LineItem] = Field(default_factory=list)


class ExtractedBalanceSheet(BaseModel):
    """One reporting period. Single-period scope - see the module docstring."""

    entity_name: str | None = None
    period_label: str | None = Field(default=None, description="e.g. 'FY2024', 'As at 31 March 2024'.")
    period_end_date: date | None = None
    currency: str | None = None
    assets: BalanceSheetSection
    liabilities: BalanceSheetSection
    equity: BalanceSheetSection


class EquationCheck(BaseModel):
    """Result of validating Total Assets = Total Liabilities + Equity.

    ``difference`` is signed and always recorded, so a near-miss is auditable
    rather than a silent pass. ``tolerance_applied`` is the effective absolute
    threshold that was used.
    """

    total_assets: Money
    total_liabilities: Money
    total_equity: Money
    expected: Money = Field(description="total_liabilities + total_equity")
    difference: Money = Field(description="total_assets - expected, signed")
    tolerance_applied: Money
    balanced: bool


# --------------------------------------------------------------------------
# The document
# --------------------------------------------------------------------------


class BalanceSheetDocument(BaseModel):
    """The record stored in the ``balance_sheets`` collection."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = Field(default=None, alias="_id")
    status: DocumentStatus = DocumentStatus.UPLOADED
    source: SourceFile

    # Raw parser output, or a pointer to it when it exceeds the inline cap.
    preliminary: PreliminaryExtraction | None = None
    preliminary_ref: StorageRef | None = None

    extracted: ExtractedBalanceSheet | None = None
    equation_check: EquationCheck | None = None

    errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def to_mongo(self) -> dict[str, Any]:
        """Dump for insertion, with ``Decimal`` encoded as ``Decimal128``."""
        from app.core.money import encode_for_mongo

        data = self.model_dump(by_alias=True, exclude_none=True, mode="python")
        if data.get("_id") is None:
            data.pop("_id", None)
        return encode_for_mongo(data)

    @classmethod
    def from_mongo(cls, data: dict[str, Any]) -> BalanceSheetDocument:
        """Build from a stored document, decoding ``Decimal128``."""
        from app.core.money import decode_from_mongo

        decoded = dict(decode_from_mongo(data))
        if "_id" in decoded:
            decoded["_id"] = str(decoded["_id"])
        return cls.model_validate(decoded)


Sha256 = Annotated[str, Field(min_length=64, max_length=64)]


__all__ = [
    "BalanceSheetDocument",
    "BalanceSheetSection",
    "DocumentStatus",
    "EquationCheck",
    "ExtractedBalanceSheet",
    "LineItem",
    "ParserKind",
    "PreliminaryExtraction",
    "RawTable",
    "SourceFile",
    "SourcePage",
    "SourceRef",
    "StorageRef",
    "utcnow",
]
