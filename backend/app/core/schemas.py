from __future__ import annotations
from datetime import date, datetime, timezone
from enum import Enum
from typing import Annotated, Any
from pydantic import BaseModel, ConfigDict, Field
from app.core.money import Money

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

class DocumentStatus(str, Enum):
    UPLOADED = 'uploaded'
    PARSED = 'parsed'
    VALIDATED = 'validated'
    EXTRACTED = 'extracted'
    ANALYZED = 'analyzed'
    REJECTED = 'rejected'
    FAILED = 'failed'

class ParserKind(str, Enum):
    PDF_TEXT = 'pdf_text'
    PDF_OCR = 'pdf_ocr'
    PDF_MIXED = 'pdf_mixed'
    EXCEL = 'excel'

class RejectionReason(str, Enum):
    UNREADABLE = 'unreadable'
    NOT_A_BALANCE_SHEET = 'not_a_balance_sheet'
    MISSING_REQUIRED_FIELDS = 'missing_required_fields'
    EQUATION_UNBALANCED = 'equation_unbalanced'

class StorageRef(BaseModel):
    backend: str = Field(description="Storage backend that owns this object, e.g. 'local'.")
    key: str = Field(description='Backend-relative key. Derived from the content hash.')
    size_bytes: int = Field(ge=0)
    content_type: str

class SourceFile(BaseModel):
    filename: str = Field(description='Original client filename. Metadata ONLY - never used to build a path.')
    content_type: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    ref: StorageRef

class SourceRef(BaseModel):
    page_index: int = Field(ge=0, description='Page number, or sheet index for Excel.')
    sheet_name: str | None = Field(default=None, description='Worksheet name for Excel; None for PDF.')
    row: int | None = None
    column: int | None = None

class PositionedWord(BaseModel):
    text: str
    left: float = Field(ge=0)
    top: float = Field(ge=0)
    width: float = Field(ge=0)
    height: float = Field(ge=0)
    confidence: float | None = Field(default=None, description='OCR per-word confidence, 0-100. None for digital text, which is read rather than guessed at.')

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def center_x(self) -> float:
        return self.left + self.width / 2

class RawTable(BaseModel):
    rows: list[list[str | None]] = Field(default_factory=list)

class SourcePage(BaseModel):
    index: int = Field(ge=0)
    name: str | None = Field(default=None, description='Sheet name for Excel; None for PDF.')
    text: str = ''
    tables: list[RawTable] = Field(default_factory=list)
    ocr_used: bool = False
    ocr_confidence: float | None = None
    words: list[PositionedWord] = Field(default_factory=list, description='Word boxes for this page, from OCR or from the PDF text layer. Empty for Excel, whose cells already carry column structure.')
    page_width: float | None = None
    page_height: float | None = None

class PreliminaryExtraction(BaseModel):
    parser: ParserKind
    pages: list[SourcePage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

class ExtractionStatus(str, Enum):
    EXTRACTED = 'extracted'
    UNPARSED_VALUE = 'unparsed_value'

class NormalizationStatus(str, Enum):
    NORMALIZED = 'normalized'
    NEEDS_REVIEW = 'needs_review'
    UNMAPPED = 'unmapped'
    UNAVAILABLE = 'unavailable'

class NormalizationMethod(str, Enum):
    DICTIONARY = 'dictionary'
    CACHE = 'cache'
    LLM = 'llm'
    UNAVAILABLE = 'unavailable'

class Normalization(BaseModel):
    canonical_label: str | None = None
    status: NormalizationStatus
    method: NormalizationMethod
    confidence: float | None = Field(default=None, ge=0, le=1, description="The model's own stated confidence. NOT a calibrated probability - it may demote a mapping to needs_review and may never rescue one that failed validation.")
    taxonomy_version: str
    model: str | None = Field(default=None, description="e.g. 'qwen3:8b'.")
    reason: str | None = Field(default=None, description='Why this was not normalized, when it was not.')

class LineItem(BaseModel):
    label: str = Field(description='The label as printed in the document.')
    value: Money | None = Field(default=None, description='None when the printed figure would not parse.')
    raw: str | None = Field(default=None, description="The figure exactly as printed, e.g. '(2,300)'.")
    subsection: str | None = Field(default=None, description="'current' or 'non_current' where the sheet says.")
    source: SourceRef | None = None
    status: ExtractionStatus = ExtractionStatus.EXTRACTED
    normalization: Normalization | None = None

class BalanceSheetSection(BaseModel):
    total: Money
    total_label: str | None = Field(default=None, description="The total line's label exactly as printed.")
    total_raw: str | None = Field(default=None, description="The total cell as printed, e.g. '(2,300)'. Kept alongside the parsed Decimal so the printed convention stays recoverable.")
    total_source: SourceRef | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    line_items_total: Money | None = Field(default=None, description='Sum of the extracted line items.')
    reconciliation_difference: Money | None = Field(default=None, description="total - line_items_total, signed. **Diagnostic only.** Subtotals and rounding make exact agreement unusual, so this is recorded for review and never used to reject a document. It is not the accounting equation, which is Module 1's and is checked there.")

class ExtractedBalanceSheet(BaseModel):
    entity_name: str | None = None
    period_label: str | None = Field(default=None, description="e.g. 'FY2024', 'As at 31 March 2024'.")
    period_end_date: date | None = None
    currency: str | None = None
    assets: BalanceSheetSection
    liabilities: BalanceSheetSection
    equity: BalanceSheetSection
    taxonomy_version: str | None = Field(default=None, description='Which canonical vocabulary normalized this.')
    normalization_summary: dict[str, int] | None = Field(default=None, description='Line-item counts by NormalizationStatus.')

class RatioStatus(str, Enum):
    OK = 'ok'
    PARTIAL = 'partial'
    UNAVAILABLE = 'unavailable'

class RatioUnit(str, Enum):
    RATIO = 'ratio'
    CURRENCY = 'currency'

class RatioBasis(str, Enum):
    SECTION_TOTAL = 'section_total'
    DERIVED_SUM = 'derived_sum'
    COMPOSITE = 'composite'

class RatioInput(BaseModel):
    canonical_label: str | None = None
    label: str = Field(description='The label as printed in the document.')
    value: Money
    source: SourceRef | None = None

class RatioResult(BaseModel):
    name: str
    formula: str = Field(description="e.g. 'Current Assets / Current Liabilities'.")
    definition: str = Field(description='Prose definition, for the report and Module 4.')
    unit: RatioUnit
    status: RatioStatus
    value: Money | None = None
    numerator: Money | None = None
    denominator: Money | None = None
    numerator_basis: RatioBasis | None = None
    denominator_basis: RatioBasis | None = None
    numerator_inputs: list[RatioInput] = Field(default_factory=list)
    denominator_inputs: list[RatioInput] = Field(default_factory=list)
    excluded: list[RatioInput] = Field(default_factory=list, description='Lines that would have contributed had they been classified.')
    excluded_value: Money | None = Field(default=None, description='Sum of the excluded figures. The reported value and the value with this added bound the true one.')
    reason: str | None = Field(default=None, description='Machine-readable, from a closed set. Why there is no value.')
    warnings: list[str] = Field(default_factory=list)

class RatioDiagnostics(BaseModel):
    duplicate_canonical_labels: dict[str, int] = Field(default_factory=dict, description='Canonical labels claimed by more than one line, and by how many. Summed, never de-duplicated: two printed lines are two figures.')
    reconciliation_difference: dict[str, Money] = Field(default_factory=dict, description="Per section, Module 2's total-minus-line-items difference. How far the derived level and the printed level disagree.")
    normalization_summary: dict[str, int] = Field(default_factory=dict, description='Line-item counts by NormalizationStatus.')
    unclassified: list[RatioInput] = Field(default_factory=list, description='Every line carrying a figure that no ratio could use.')

class RatioSet(BaseModel):
    ratios: list[RatioResult] = Field(default_factory=list)
    spec_version: str = Field(description='Which set of formulas produced this.')
    taxonomy_version: str | None = Field(default=None, description='Copied from the sheet that was analysed.')
    currency: str | None = None
    scale_label: str | None = Field(default=None, description="e.g. 'in thousands'. Recorded, NOT applied - as in Modules 1 and 2. Ratios are dimensionless; working capital carries this scale.")
    diagnostics: RatioDiagnostics = Field(default_factory=RatioDiagnostics)
    warnings: list[str] = Field(default_factory=list)
    computed_at: datetime = Field(default_factory=utcnow)

    def get(self, name: str) -> RatioResult | None:
        for result in self.ratios:
            if result.name == name:
                return result
        return None

class PageRole(str, Enum):
    BALANCE_SHEET = 'balance_sheet'
    SUPPLEMENTARY = 'supplementary'

class DocumentChunk(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str | None = Field(default=None, alias='_id')
    document_id: str = Field(description='Mandatory retrieval filter. Never optional.')
    page_index: int = Field(ge=0)
    sheet_name: str | None = None
    page_role: PageRole
    chunk_index: int = Field(ge=0, description='Position within the page.')
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    text: str
    embedding: list[float] = Field(default_factory=list)
    embedding_model: str
    embedding_dim: int = Field(gt=0)
    chunk_spec_version: str
    created_at: datetime = Field(default_factory=utcnow)

class ChunkIndexState(BaseModel):
    indexed_at: datetime = Field(default_factory=utcnow)
    embedding_model: str
    embedding_dim: int = Field(gt=0)
    chunk_spec_version: str
    chunk_count: int = Field(ge=0)

    def is_stale(self, *, embedding_model: str, chunk_spec_version: str) -> bool:
        return self.embedding_model != embedding_model or self.chunk_spec_version != chunk_spec_version

class RetrievalRoute(str, Enum):
    STRUCTURED = 'structured'
    TEXT = 'text'
    BOTH = 'both'
    OUT_OF_SCOPE = 'out_of_scope'

class EvidenceKind(str, Enum):
    SECTION_TOTAL = 'section_total'
    LINE_ITEM = 'line_item'
    RATIO = 'ratio'
    EQUATION = 'equation'
    COVERAGE = 'coverage'
    TEXT = 'text'

class Evidence(BaseModel):
    id: str = Field(description='Citation tag, unique within one answer.')
    kind: EvidenceKind
    label: str = Field(description="What this is, in the document's own words where it has any.")
    value: str | None = Field(default=None, description='The figure, as a string. Money is never serialised as a JSON number - an IEEE double would defeat the point of Decimal.')
    detail: str | None = Field(default=None, description='Formula, unavailability reason, or stated limitation.')
    quote: str | None = Field(default=None, description='The passage, for TEXT evidence.')
    page_index: int | None = None
    source: SourceRef | None = None
    chunk_id: str | None = None

class AnswerStatus(str, Enum):
    ANSWERED = 'answered'
    REFUSED = 'refused'
    DEGRADED = 'degraded'

class Verification(BaseModel):
    passed: bool
    figures_verified: list[str] = Field(default_factory=list)
    figures_unverified: list[str] = Field(default_factory=list)
    retried: bool = Field(default=False, description='Whether generation was retried after a failed check.')

class Answer(BaseModel):
    document_id: str
    question: str
    answer: str | None = Field(default=None, description='None only when status is DEGRADED.')
    status: AnswerStatus
    route: RetrievalRoute
    supporting_facts: list[Evidence] = Field(default_factory=list, description='The authoritative facts placed in context, cited or not.')
    citations: list[Evidence] = Field(default_factory=list, description='What the model actually cited, resolved. A tag that resolves to nothing is dropped rather than shipped pointing nowhere.')
    verification: Verification
    reason: str | None = Field(default=None, description='Machine-readable, from a closed set. Why it refused.')
    model: str | None = Field(default=None, description='None when no model was called.')
    spec_version: str
    created_at: datetime = Field(default_factory=utcnow)

class IdentificationSignal(BaseModel):
    kind: str = Field(description="'title', 'section_header', 'total_line' or 'equation_terms'.")
    text: str = Field(description='The matching text, as printed.')
    weight: int = Field(description='Points this signal contributed to the score.')
    source: SourceRef

class IdentificationEvidence(BaseModel):
    is_balance_sheet: bool
    score: int
    threshold: int
    signals: list[IdentificationSignal] = Field(default_factory=list)

class PeriodCandidate(BaseModel):
    label: str = Field(description='The column heading as printed.')
    end_date: date | None = None
    year: int | None = None
    source: SourceRef

class PeriodSelection(BaseModel):
    selected: PeriodCandidate
    candidates: list[PeriodCandidate] = Field(default_factory=list)
    reason: str = Field(description='Why this candidate was chosen.')

class UnitHint(BaseModel):
    currency: str | None = Field(default=None, description='ISO code or symbol as found.')
    scale_label: str | None = Field(default=None, description="e.g. 'in thousands'.")
    scale_factor: Money | None = Field(default=None, description='What scale_label means numerically. NOT applied.')
    source: SourceRef | None = None

class ValidationSummary(BaseModel):
    required_fields_present: bool
    missing_fields: list[str] = Field(default_factory=list)
    equation_balanced: bool | None = Field(default=None, description='None when the equation could not be evaluated.')
    passed: bool

class Rejection(BaseModel):
    reason: RejectionReason
    message: str = Field(description='Safe for display. No paths, no stack traces.')
    at: datetime = Field(default_factory=utcnow)

class EquationCheck(BaseModel):
    total_assets: Money
    total_liabilities: Money
    total_equity: Money
    expected: Money = Field(description='total_liabilities + total_equity')
    difference: Money = Field(description='total_assets - expected, signed')
    tolerance_applied: Money
    balanced: bool

class BalanceSheetDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str | None = Field(default=None, alias='_id')
    status: DocumentStatus = DocumentStatus.UPLOADED
    source: SourceFile
    preliminary: PreliminaryExtraction | None = None
    preliminary_ref: StorageRef | None = None
    identification: IdentificationEvidence | None = None
    period: PeriodSelection | None = None
    units: UnitHint | None = None
    extracted: ExtractedBalanceSheet | None = None
    ratios: RatioSet | None = None
    chunk_index: ChunkIndexState | None = None
    equation_check: EquationCheck | None = None
    validation: ValidationSummary | None = None
    rejection: Rejection | None = None
    errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    def to_mongo(self) -> dict[str, Any]:
        from app.core.money import encode_for_mongo
        data = self.model_dump(by_alias=True, exclude_none=True, mode='python')
        if data.get('_id') is None:
            data.pop('_id', None)
        return encode_for_mongo(data)

    @classmethod
    def from_mongo(cls, data: dict[str, Any]) -> BalanceSheetDocument:
        from app.core.money import decode_from_mongo
        decoded = dict(decode_from_mongo(data))
        if '_id' in decoded:
            decoded['_id'] = str(decoded['_id'])
        return cls.model_validate(decoded)
Sha256 = Annotated[str, Field(min_length=64, max_length=64)]
__all__ = ['Answer', 'AnswerStatus', 'BalanceSheetDocument', 'BalanceSheetSection', 'ChunkIndexState', 'DocumentChunk', 'DocumentStatus', 'EquationCheck', 'Evidence', 'EvidenceKind', 'PageRole', 'RetrievalRoute', 'Verification', 'ExtractedBalanceSheet', 'IdentificationEvidence', 'IdentificationSignal', 'ExtractionStatus', 'LineItem', 'Normalization', 'NormalizationMethod', 'NormalizationStatus', 'ParserKind', 'PositionedWord', 'PeriodCandidate', 'PeriodSelection', 'PreliminaryExtraction', 'RatioBasis', 'RatioDiagnostics', 'RatioInput', 'RatioResult', 'RatioSet', 'RatioStatus', 'RatioUnit', 'RawTable', 'Rejection', 'RejectionReason', 'SourceFile', 'SourcePage', 'SourceRef', 'StorageRef', 'UnitHint', 'ValidationSummary', 'utcnow']
