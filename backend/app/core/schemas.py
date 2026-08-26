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
    # A filing whose pages are not uniform: some carry a digital text layer,
    # others are scanned images. Detection is per page, so the document-level
    # kind has to be able to say "both" rather than pick a side.
    PDF_MIXED = "pdf_mixed"
    EXCEL = "excel"


class RejectionReason(str, Enum):
    """Why a submission did not reach ``VALIDATED``.

    Rejected submissions are kept, never deleted - an auditor needs to see what
    was refused and why as much as what was accepted.
    """

    UNREADABLE = "unreadable"
    NOT_A_BALANCE_SHEET = "not_a_balance_sheet"
    MISSING_REQUIRED_FIELDS = "missing_required_fields"
    EQUATION_UNBALANCED = "equation_unbalanced"


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
    sheet_name: str | None = Field(
        default=None, description="Worksheet name for Excel; None for PDF."
    )
    row: int | None = None
    column: int | None = None


class PositionedWord(BaseModel):
    """One word and the box it occupied on the page.

    Positions are kept rather than discarded because a Balance Sheet is a
    two-dimensional document: which *column* a number sits in is what decides
    which reporting period it belongs to, and that information exists only in
    the geometry. Reducing a page to a flat string destroys it.

    Recorded for scanned pages (from OCR) *and* digital ones (from the PDF text
    layer), so column handling is one code path rather than two. Coordinates are
    page pixels after rasterisation, or PDF points for a digital page;
    ``page_width`` and ``page_height`` on :class:`SourcePage` give them meaning
    either way.
    """

    text: str
    left: float = Field(ge=0)
    top: float = Field(ge=0)
    width: float = Field(ge=0)
    height: float = Field(ge=0)
    confidence: float | None = Field(
        default=None,
        description="OCR per-word confidence, 0-100. None for digital text, "
        "which is read rather than guessed at.",
    )

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def center_x(self) -> float:
        return self.left + self.width / 2


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
    words: list[PositionedWord] = Field(
        default_factory=list,
        description="Word boxes for this page, from OCR or from the PDF text "
        "layer. Empty for Excel, whose cells already carry column structure.",
    )
    page_width: float | None = None
    page_height: float | None = None


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
    """A section total, plus its line items once Module 2 has filled them in.

    Module 1 populates ``total`` (and the three traceability fields beside it)
    and leaves ``line_items`` empty. Complete line-item extraction is Module 2's
    responsibility and is deliberately absent here.
    """

    total: Money
    total_label: str | None = Field(
        default=None, description="The total line's label exactly as printed."
    )
    total_raw: str | None = Field(
        default=None,
        description="The total cell as printed, e.g. '(2,300)'. Kept alongside the "
        "parsed Decimal so the printed convention stays recoverable.",
    )
    total_source: SourceRef | None = None
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


# --------------------------------------------------------------------------
# Module 1 evidence - why the system decided what it decided
# --------------------------------------------------------------------------


class IdentificationSignal(BaseModel):
    """One piece of evidence that the document is (or is not) a Balance Sheet."""

    kind: str = Field(description="'title', 'section_header', 'total_line' or 'equation_terms'.")
    text: str = Field(description="The matching text, as printed.")
    weight: int = Field(description="Points this signal contributed to the score.")
    source: SourceRef


class IdentificationEvidence(BaseModel):
    """The identification decision with the reasoning that produced it.

    Stored rather than discarded so a rejection can be argued with. A bare
    'not a Balance Sheet' with no evidence is not auditable.
    """

    is_balance_sheet: bool
    score: int
    threshold: int
    signals: list[IdentificationSignal] = Field(default_factory=list)


class PeriodCandidate(BaseModel):
    """A reporting period column found in the document.

    Comparative filings print two or more. All of them are recorded here for
    traceability, but only one is ever analysed - see :class:`PeriodSelection`.
    """

    label: str = Field(description="The column heading as printed.")
    end_date: date | None = None
    year: int | None = None
    source: SourceRef


class PeriodSelection(BaseModel):
    """Which reporting period was analysed, and why.

    **Single-period scope.** When a Balance Sheet is comparative, the most
    recent period is selected and the rest are recorded but not analysed. This
    is deliberately not a year-over-year comparison: no figure from a
    non-selected column is ever read.
    """

    selected: PeriodCandidate
    candidates: list[PeriodCandidate] = Field(default_factory=list)
    reason: str = Field(description="Why this candidate was chosen.")


class UnitHint(BaseModel):
    """Currency and magnitude as *printed on the document*.

    Recorded only. Module 1 applies no scaling: a sheet printed 'in thousands'
    is stored with the figures exactly as printed and ``scale_factor`` noted
    beside them. Scaling is a normalisation decision and belongs to Module 2.
    """

    currency: str | None = Field(default=None, description="ISO code or symbol as found.")
    scale_label: str | None = Field(default=None, description="e.g. 'in thousands'.")
    scale_factor: Money | None = Field(
        default=None, description="What scale_label means numerically. NOT applied."
    )
    source: SourceRef | None = None


class ValidationSummary(BaseModel):
    """The Module 1 verdict: is this a usable Balance Sheet?"""

    required_fields_present: bool
    missing_fields: list[str] = Field(default_factory=list)
    equation_balanced: bool | None = Field(
        default=None, description="None when the equation could not be evaluated."
    )
    passed: bool


class Rejection(BaseModel):
    """A recorded refusal, kept for auditability.

    Rejected submissions stay in the collection. Deleting them would erase the
    evidence trail that makes a refusal reviewable.
    """

    reason: RejectionReason
    message: str = Field(description="Safe for display. No paths, no stack traces.")
    at: datetime = Field(default_factory=utcnow)


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

    # Module 1 evidence.
    identification: IdentificationEvidence | None = None
    period: PeriodSelection | None = None
    units: UnitHint | None = None

    extracted: ExtractedBalanceSheet | None = None
    equation_check: EquationCheck | None = None
    validation: ValidationSummary | None = None
    rejection: Rejection | None = None

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
    "IdentificationEvidence",
    "IdentificationSignal",
    "LineItem",
    "ParserKind",
    "PositionedWord",
    "PeriodCandidate",
    "PeriodSelection",
    "PreliminaryExtraction",
    "RawTable",
    "Rejection",
    "RejectionReason",
    "SourceFile",
    "SourcePage",
    "SourceRef",
    "StorageRef",
    "UnitHint",
    "ValidationSummary",
    "utcnow",
]
