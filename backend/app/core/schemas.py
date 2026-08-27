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
    # Module 2 has extracted the full line items and normalized their labels.
    EXTRACTED = "extracted"
    # Module 3 has computed the ratios. Module 4 will name its own state.
    ANALYZED = "analyzed"
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


class ExtractionStatus(str, Enum):
    """Whether Module 2 got a usable figure out of a line."""

    EXTRACTED = "extracted"
    # The label was found but its figure would not parse. The line is kept
    # anyway: dropping it would quietly shrink the Balance Sheet, and a line
    # nobody can read is exactly the one a reviewer needs to see.
    UNPARSED_VALUE = "unparsed_value"


class NormalizationStatus(str, Enum):
    """How far terminology mapping got on one line item.

    ``NEEDS_REVIEW`` is a real answer, not a failure. Forcing a canonical label
    onto a label nobody understood would put a confident wrong category into
    the ratios; saying so leaves the line intact and visible.
    """

    NORMALIZED = "normalized"
    NEEDS_REVIEW = "needs_review"
    UNMAPPED = "unmapped"
    UNAVAILABLE = "unavailable"


class NormalizationMethod(str, Enum):
    """What decided the mapping. Stored so every answer names its own source."""

    DICTIONARY = "dictionary"
    CACHE = "cache"
    LLM = "llm"
    UNAVAILABLE = "unavailable"


class Normalization(BaseModel):
    """The terminology decision for one line item, and who made it.

    Recorded beside the original label, never instead of it. ``model`` and
    ``taxonomy_version`` are what make a stored mapping reproducible: the same
    document re-run against the same model and vocabulary must give the same
    answer, and when it does not, this says which of the two changed.
    """

    canonical_label: str | None = None
    status: NormalizationStatus
    method: NormalizationMethod
    confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="The model's own stated confidence. NOT a calibrated "
        "probability - it may demote a mapping to needs_review and may never "
        "rescue one that failed validation.",
    )
    taxonomy_version: str
    model: str | None = Field(default=None, description="e.g. 'qwen3:8b'.")
    reason: str | None = Field(
        default=None, description="Why this was not normalized, when it was not."
    )


class LineItem(BaseModel):
    """One extracted line of the Balance Sheet.

    ``label`` is the document's own wording and is never overwritten -
    ``normalization.canonical_label`` sits beside it. "Trade Debtors" and
    "Trade Receivables" may map to one concept while remaining distinguishable
    as what was actually printed.
    """

    label: str = Field(description="The label as printed in the document.")
    value: Money | None = Field(
        default=None, description="None when the printed figure would not parse."
    )
    raw: str | None = Field(
        default=None, description="The figure exactly as printed, e.g. '(2,300)'."
    )
    subsection: str | None = Field(
        default=None, description="'current' or 'non_current' where the sheet says."
    )
    source: SourceRef | None = None
    status: ExtractionStatus = ExtractionStatus.EXTRACTED
    normalization: Normalization | None = None


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
    line_items_total: Money | None = Field(
        default=None, description="Sum of the extracted line items."
    )
    reconciliation_difference: Money | None = Field(
        default=None,
        description="total - line_items_total, signed. **Diagnostic only.** "
        "Subtotals and rounding make exact agreement unusual, so this is "
        "recorded for review and never used to reject a document. It is not "
        "the accounting equation, which is Module 1's and is checked there.",
    )


class ExtractedBalanceSheet(BaseModel):
    """One reporting period. Single-period scope - see the module docstring."""

    entity_name: str | None = None
    period_label: str | None = Field(default=None, description="e.g. 'FY2024', 'As at 31 March 2024'.")
    period_end_date: date | None = None
    currency: str | None = None
    assets: BalanceSheetSection
    liabilities: BalanceSheetSection
    equity: BalanceSheetSection
    taxonomy_version: str | None = Field(
        default=None, description="Which canonical vocabulary normalized this."
    )
    normalization_summary: dict[str, int] | None = Field(
        default=None, description="Line-item counts by NormalizationStatus."
    )


# --------------------------------------------------------------------------
# Module 3 results - the ratio shapes
#
# The result shape lives here, in ``core``, for the same reason
# ``ExtractedBalanceSheet`` does: it is the contract Module 4 will read. The
# *formulas* stay in ``modules/ratios``, which ``core`` may not import.
# --------------------------------------------------------------------------


class RatioStatus(str, Enum):
    """Whether a ratio was computed, and how completely.

    ``PARTIAL`` is the honest middle: the figure is real, but a line that
    should have contributed was left out because nobody could classify it.
    Reporting that as ``OK`` would hand a reader an understated ratio with no
    hint that it is understated.
    """

    OK = "ok"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class RatioUnit(str, Enum):
    """What kind of number a result is.

    Working capital is money and inherits the sheet's printed scale; the other
    six are dimensionless, so scale cancels out of them entirely.
    """

    RATIO = "ratio"
    CURRENCY = "currency"


class RatioBasis(str, Enum):
    """Which level of the document a figure was taken from.

    Recorded per side of every ratio because Module 3 mixes levels
    deliberately: grand totals are Module 1's printed, equation-checked
    figures, while current/non-current subtotals have to be summed from line
    items because Module 2 discarded the printed subtotals. A reader should not
    have to know that to interpret the number.
    """

    SECTION_TOTAL = "section_total"
    DERIVED_SUM = "derived_sum"
    COMPOSITE = "composite"


class RatioInput(BaseModel):
    """One line item that contributed to - or was excluded from - a ratio.

    ``label`` is the document's own wording, so a numerator traces back to ink
    on the page rather than stopping at a canonical concept.
    ``canonical_label`` is ``None`` on an excluded input, which is precisely
    why it was excluded.
    """

    canonical_label: str | None = None
    label: str = Field(description="The label as printed in the document.")
    value: Money
    source: SourceRef | None = None


class RatioResult(BaseModel):
    """One ratio, its value, and everything needed to argue with it.

    ``numerator`` and ``denominator`` are stored **unrounded** so any consumer
    can re-derive ``value`` at any precision. ``value`` itself is quantized
    once, at the end - see ``modules/ratios/service.py``.
    """

    name: str
    formula: str = Field(description="e.g. 'Current Assets / Current Liabilities'.")
    definition: str = Field(description="Prose definition, for the report and Module 4.")
    unit: RatioUnit
    status: RatioStatus
    # Money is reused here for its one real guarantee - Decimal, never float,
    # and Decimal128 on the way back out of Mongo. `unit` is what says whether
    # this particular number is currency; a bare ratio is dimensionless.
    value: Money | None = None
    # The two operands, left and right. For the six quotients they are the
    # numerator and the denominator; for working capital, which is a
    # difference, they are the minuend and the subtrahend. Both are populated
    # either way - naming the second one "denominator" costs a little accuracy
    # in one case and buys full traceability of the subtracted side.
    numerator: Money | None = None
    denominator: Money | None = None
    numerator_basis: RatioBasis | None = None
    denominator_basis: RatioBasis | None = None
    numerator_inputs: list[RatioInput] = Field(default_factory=list)
    denominator_inputs: list[RatioInput] = Field(default_factory=list)
    excluded: list[RatioInput] = Field(
        default_factory=list,
        description="Lines that would have contributed had they been classified.",
    )
    excluded_value: Money | None = Field(
        default=None,
        description="Sum of the excluded figures. The reported value and the "
        "value with this added bound the true one.",
    )
    reason: str | None = Field(
        default=None, description="Machine-readable, from a closed set. Why there is no value."
    )
    warnings: list[str] = Field(default_factory=list)


class RatioDiagnostics(BaseModel):
    """What a reviewer needs in order to distrust a ratio intelligently.

    None of this changes a computed figure. It exists because the failure this
    module cannot detect - a line confidently mapped to the wrong category -
    leaves no trace in the ratios themselves, only in these.
    """

    duplicate_canonical_labels: dict[str, int] = Field(
        default_factory=dict,
        description="Canonical labels claimed by more than one line, and by how "
        "many. Summed, never de-duplicated: two printed lines are two figures.",
    )
    reconciliation_difference: dict[str, Money] = Field(
        default_factory=dict,
        description="Per section, Module 2's total-minus-line-items difference. "
        "How far the derived level and the printed level disagree.",
    )
    normalization_summary: dict[str, int] = Field(
        default_factory=dict, description="Line-item counts by NormalizationStatus."
    )
    unclassified: list[RatioInput] = Field(
        default_factory=list,
        description="Every line carrying a figure that no ratio could use.",
    )


class RatioSet(BaseModel):
    """Every ratio computed for one reporting period.

    ``spec_version`` is deliberately separate from ``taxonomy_version``: a
    formula change and a vocabulary change are different events, and a stored
    result has to say which of the two moved.
    """

    ratios: list[RatioResult] = Field(default_factory=list)
    spec_version: str = Field(description="Which set of formulas produced this.")
    taxonomy_version: str | None = Field(
        default=None, description="Copied from the sheet that was analysed."
    )
    currency: str | None = None
    scale_label: str | None = Field(
        default=None,
        description="e.g. 'in thousands'. Recorded, NOT applied - as in Modules 1 and 2. "
        "Ratios are dimensionless; working capital carries this scale.",
    )
    diagnostics: RatioDiagnostics = Field(default_factory=RatioDiagnostics)
    warnings: list[str] = Field(default_factory=list)
    computed_at: datetime = Field(default_factory=utcnow)

    def get(self, name: str) -> RatioResult | None:
        """The result named ``name``, or ``None`` if this set has no such ratio."""
        for result in self.ratios:
            if result.name == name:
                return result
        return None


# --------------------------------------------------------------------------
# Module 4 - retrieval, grounding and answers
#
# The response shapes live here, in ``core``, for the same reason
# ``ExtractedBalanceSheet`` and ``RatioSet`` do: they are the contract a caller
# reads. The retrieval *logic* - chunking rules, routing, prompts - stays in
# ``modules/insights``, which ``core`` may not import.
# --------------------------------------------------------------------------


class PageRole(str, Enum):
    """What part a page plays in the uploaded file.

    Derived from the identification evidence Module 1 already stored, never
    re-derived. The distinction is what lets a policy question be answered from
    the notes while the analysis stays Balance-Sheet-only: supplementary pages
    are **retrievable, never analysed**, and no figure is ever taken from one.
    """

    BALANCE_SHEET = "balance_sheet"
    SUPPLEMENTARY = "supplementary"


class DocumentChunk(BaseModel):
    """One passage of the document's own text, embedded for retrieval.

    Built only from text Module 1 already extracted - this never re-opens a
    file. ``char_start``/``char_end`` index into ``SourcePage.text``, so a
    citation can be checked against the stored page rather than taken on trust.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = Field(default=None, alias="_id")
    document_id: str = Field(description="Mandatory retrieval filter. Never optional.")
    page_index: int = Field(ge=0)
    sheet_name: str | None = None
    page_role: PageRole
    chunk_index: int = Field(ge=0, description="Position within the page.")
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    text: str
    embedding: list[float] = Field(default_factory=list)
    embedding_model: str
    embedding_dim: int = Field(gt=0)
    chunk_spec_version: str
    created_at: datetime = Field(default_factory=utcnow)


class ChunkIndexState(BaseModel):
    """What the stored chunks for a document were built from.

    Kept so re-indexing is decided by comparison rather than by a timestamp
    nobody can interpret: a chunking change, a different embedding model or a
    changed dimension all invalidate the vectors, and each is visible here.
    """

    indexed_at: datetime = Field(default_factory=utcnow)
    embedding_model: str
    embedding_dim: int = Field(gt=0)
    chunk_spec_version: str
    chunk_count: int = Field(ge=0)

    def is_stale(self, *, embedding_model: str, chunk_spec_version: str) -> bool:
        """Whether these chunks must be rebuilt before they can be trusted.

        Dimension is not compared: it is a property of the model, so a change
        in one implies a change in the other, and comparing both would only
        invent a state where they disagree.
        """
        return (
            self.embedding_model != embedding_model
            or self.chunk_spec_version != chunk_spec_version
        )


class RetrievalRoute(str, Enum):
    """Which retrieval paths a question was sent down.

    Decided by rules, not by a model - so the same question always routes the
    same way, and an answer is reproducible.
    """

    STRUCTURED = "structured"
    TEXT = "text"
    BOTH = "both"
    # Knowably unanswerable from a Balance Sheet - net profit, revenue, cash
    # flow. Refused deterministically, without calling a model at all.
    OUT_OF_SCOPE = "out_of_scope"


class EvidenceKind(str, Enum):
    SECTION_TOTAL = "section_total"
    LINE_ITEM = "line_item"
    RATIO = "ratio"
    EQUATION = "equation"
    COVERAGE = "coverage"
    # A passage quoted from the document's own text.
    TEXT = "text"


class Evidence(BaseModel):
    """One grounded piece of support, and where it came from.

    Every kind carries the same shape so an answer's citations and its
    supporting facts are one vocabulary rather than two near-identical ones.
    ``id`` is the tag the model cites - ``F1``, ``R1``, ``C1``.
    """

    id: str = Field(description="Citation tag, unique within one answer.")
    kind: EvidenceKind
    label: str = Field(description="What this is, in the document's own words where it has any.")
    value: str | None = Field(
        default=None,
        description="The figure, as a string. Money is never serialised as a "
        "JSON number - an IEEE double would defeat the point of Decimal.",
    )
    detail: str | None = Field(
        default=None, description="Formula, unavailability reason, or stated limitation."
    )
    quote: str | None = Field(default=None, description="The passage, for TEXT evidence.")
    page_index: int | None = None
    source: SourceRef | None = None
    chunk_id: str | None = None


class AnswerStatus(str, Enum):
    """How an answer turned out.

    A refusal is a **successful** outcome, not an error: saying "a Balance
    Sheet does not report profit" is the correct answer to that question.
    """

    ANSWERED = "answered"
    REFUSED = "refused"
    # No model was reachable, so the facts are returned without prose. The
    # figures are already computed and stored; withholding them because a
    # language model is offline would help nobody.
    DEGRADED = "degraded"


class Verification(BaseModel):
    """Whether every figure in the answer traces back to supplied context.

    The direct answer to a measured failure: on this project's own Q&A
    benchmark a candidate model summed current assets as 550,000 against a true
    850,000 and concluded the company could not pay its bills. A figure that is
    not in the context is not in the answer.
    """

    passed: bool
    figures_verified: list[str] = Field(default_factory=list)
    figures_unverified: list[str] = Field(default_factory=list)
    retried: bool = Field(
        default=False, description="Whether generation was retried after a failed check."
    )


class Answer(BaseModel):
    """A grounded reply to one question about one document."""

    document_id: str
    question: str
    answer: str | None = Field(
        default=None, description="None only when status is DEGRADED."
    )
    status: AnswerStatus
    route: RetrievalRoute
    supporting_facts: list[Evidence] = Field(
        default_factory=list,
        description="The authoritative facts placed in context, cited or not.",
    )
    citations: list[Evidence] = Field(
        default_factory=list,
        description="What the model actually cited, resolved. A tag that "
        "resolves to nothing is dropped rather than shipped pointing nowhere.",
    )
    verification: Verification
    reason: str | None = Field(
        default=None, description="Machine-readable, from a closed set. Why it refused."
    )
    model: str | None = Field(default=None, description="None when no model was called.")
    spec_version: str
    created_at: datetime = Field(default_factory=utcnow)


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
    ratios: RatioSet | None = None
    # Module 4 indexes lazily, on the first question asked about a document -
    # so most uploads never carry this, and an upload never waits for it.
    chunk_index: ChunkIndexState | None = None
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
    "Answer",
    "AnswerStatus",
    "BalanceSheetDocument",
    "BalanceSheetSection",
    "ChunkIndexState",
    "DocumentChunk",
    "DocumentStatus",
    "EquationCheck",
    "Evidence",
    "EvidenceKind",
    "PageRole",
    "RetrievalRoute",
    "Verification",
    "ExtractedBalanceSheet",
    "IdentificationEvidence",
    "IdentificationSignal",
    "ExtractionStatus",
    "LineItem",
    "Normalization",
    "NormalizationMethod",
    "NormalizationStatus",
    "ParserKind",
    "PositionedWord",
    "PeriodCandidate",
    "PeriodSelection",
    "PreliminaryExtraction",
    "RatioBasis",
    "RatioDiagnostics",
    "RatioInput",
    "RatioResult",
    "RatioSet",
    "RatioStatus",
    "RatioUnit",
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
