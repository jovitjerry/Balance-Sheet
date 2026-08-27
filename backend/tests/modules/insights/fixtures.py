"""Building an analyzed document to ask questions of.

Module 4 consumes a finished record - Modules 1-3 have already run - so unlike
the earlier modules it can be tested against documents assembled directly. The
real end-to-end path is exercised separately.
"""

from __future__ import annotations

from decimal import Decimal

from app.core.schemas import (
    BalanceSheetDocument,
    DocumentStatus,
    EquationCheck,
    IdentificationEvidence,
    IdentificationSignal,
    ParserKind,
    PreliminaryExtraction,
    SourceFile,
    SourcePage,
    SourceRef,
    StorageRef,
)
from app.modules.ratios.service import compute_ratios
from tests.modules.ratios.fixtures import balanced_sheet, item, section, sheet

DOCUMENT_ID = "652f1a2b3c4d5e6f70819200"
OTHER_DOCUMENT_ID = "652f1a2b3c4d5e6f70819201"

# The balance sheet page as it would have been printed, for chunking and
# retrieval tests. Deliberately close to the real fixture's wording.
BALANCE_SHEET_PAGE = """Meridian Industries Limited
Balance Sheet as at 31 March 2026

ASSETS
Current Assets
Cash and cash equivalents 125,000
Trade receivables 280,000
Inventory 350,000
Other current assets 95,000
Total Current Assets 850,000
Non-Current Assets
Property, plant and equipment 1,200,000
Intangible assets 150,000
Other non-current assets 100,000
TOTAL ASSETS 2,300,000
"""

NOTES_PAGE = """Notes to the Financial Statements

1. Property, plant and equipment
Property, plant and equipment is stated at cost less accumulated
depreciation and any accumulated impairment losses. Depreciation is
charged on a straight-line basis over the estimated useful lives of the
assets, which for plant and machinery is ten years.

2. Inventory
Inventory is valued at the lower of cost and net realisable value, with
cost determined on a first-in, first-out basis.

3. Trade receivables
Trade receivables are recognised initially at the transaction price and
carried less any provision for amounts considered doubtful.
"""


def _source(sha: str = "d" * 64) -> SourceFile:
    return SourceFile(
        filename="sheet.pdf",
        content_type="application/pdf",
        size_bytes=2048,
        sha256=sha,
        ref=StorageRef(
            backend="local",
            key="dd/dd/x.pdf",
            size_bytes=2048,
            content_type="application/pdf",
        ),
    )


def preliminary_of(pages: list[str]) -> PreliminaryExtraction:
    """Raw parser output carrying the given page texts and nothing invented."""
    return PreliminaryExtraction(
        parser=ParserKind.PDF_TEXT,
        pages=[
            SourcePage(index=index, text=text, page_width=612.0, page_height=792.0)
            for index, text in enumerate(pages)
        ],
    )


def analyzed_document(
    *,
    document_id: str = DOCUMENT_ID,
    pages: list[str] | None = None,
    labels: dict[str, list[tuple[str, str]]] | None = None,
    entity: str = "Meridian Industries Limited",
    sha: str = "d" * 64,
    balance_sheet_pages: tuple[int, ...] = (0,),
) -> BalanceSheetDocument:
    """A document exactly as Modules 1-3 leave it: analyzed, with ratios.

    ``labels`` replaces the default line items for a section, so a test can put
    wording peculiar to one filing on the document. ``pages`` supplies the page
    texts Module 4 chunks; page 0 is the balance sheet unless said otherwise.
    """
    extracted = balanced_sheet()
    if labels:
        updates = {}
        for name, entries in labels.items():
            original = getattr(extracted, name)
            updates[name] = section(
                str(original.total),
                [item(label, value, None) for label, value in entries],
                label=original.total_label or "Total",
            )
        extracted = extracted.model_copy(update=updates)

    extracted = extracted.model_copy(update={"entity_name": entity})

    # Keep the fixture internally coherent: the section totals were printed on
    # the page the sheet is on. page_roles reads both this and the
    # identification signals, so a fixture that disagreed with itself would
    # tag two pages as the Balance Sheet.
    sheet_page = balance_sheet_pages[0] if balance_sheet_pages else 0
    extracted = extracted.model_copy(
        update={
            name: getattr(extracted, name).model_copy(
                update={
                    "total_source": SourceRef(page_index=sheet_page, row=99, column=1)
                }
            )
            for name in ("assets", "liabilities", "equity")
        }
    )
    page_texts = pages if pages is not None else [BALANCE_SHEET_PAGE]

    return BalanceSheetDocument(
        _id=document_id,
        status=DocumentStatus.ANALYZED,
        source=_source(sha),
        preliminary=preliminary_of(page_texts),
        identification=IdentificationEvidence(
            is_balance_sheet=True,
            score=8,
            threshold=4,
            signals=[
                IdentificationSignal(
                    kind="title",
                    text="Balance Sheet as at 31 March 2026",
                    weight=4,
                    source=SourceRef(page_index=index, row=1),
                )
                for index in balance_sheet_pages
            ],
        ),
        extracted=extracted,
        ratios=compute_ratios(extracted),
        equation_check=EquationCheck(
            total_assets=Decimal("2300000"),
            total_liabilities=Decimal("1350000"),
            total_equity=Decimal("950000"),
            expected=Decimal("2300000"),
            difference=Decimal("0"),
            tolerance_applied=Decimal("1"),
            balanced=True,
        ),
    )


def document_with_notes(**kwargs: object) -> BalanceSheetDocument:
    """A two-page filing: the sheet, then the accounting policies.

    The page that carries the sheet is overridable, so a test can prove the
    role comes from Module 1's stored evidence rather than from page order.
    """
    kwargs.setdefault("pages", [BALANCE_SHEET_PAGE, NOTES_PAGE])
    kwargs.setdefault("balance_sheet_pages", (0,))
    return analyzed_document(**kwargs)  # type: ignore[arg-type]


__all__ = [
    "BALANCE_SHEET_PAGE",
    "DOCUMENT_ID",
    "NOTES_PAGE",
    "OTHER_DOCUMENT_ID",
    "analyzed_document",
    "document_with_notes",
    "preliminary_of",
    "sheet",
]
