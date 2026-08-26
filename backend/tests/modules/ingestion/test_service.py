"""The Module 1 workflow end to end, against a real MongoDB.

These use ``test_db`` and so are marked ``integration`` automatically; they
skip when no cluster is reachable, or fail under ``--require-mongo``.

The OCR path is not exercised here - it needs the Tesseract binary and is
covered in ``test_ocr.py``. Every fixture below has a text layer.
"""

from __future__ import annotations

import io
from decimal import Decimal
from typing import Any

import pytest
from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings
from app.core.db import BALANCE_SHEETS
from app.core.errors import InvalidUploadError, NotABalanceSheetError, UnreadableDocumentError
from app.core.schemas import (
    BalanceSheetDocument,
    DocumentStatus,
    RejectionReason,
)
from app.core.storage import LocalFileStorage
from app.modules.ingestion.service import process_upload
from tests.modules.ingestion.fixtures import (
    Text,
    abc_manufacturing_balance_sheet_pdf,
    comparative_balance_sheet_pdf,
    make_text_pdf,
    side_by_side_balance_sheet_pdf,
    simple_balance_sheet_pdf,
    simple_balance_sheet_xlsx,
)


class Upload:
    """A stand-in for ``UploadFile`` - just the streaming read the service uses."""

    def __init__(self, data: bytes) -> None:
        self._stream = io.BytesIO(data)

    async def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)


def text_pdf(rows: list[tuple[str, str | None]]) -> bytes:
    runs: list[Text] = []
    y = 740.0
    for label, value in rows:
        runs.append(Text(72, y, label))
        if value is not None:
            runs.append(Text(420, y, value))
        y -= 18.0
    return make_text_pdf([runs])


async def run(
    data: bytes,
    db: AsyncDatabase[dict[str, Any]],
    storage: LocalFileStorage,
    settings: Settings,
    *,
    filename: str = "sheet.pdf",
    content_type: str = "application/pdf",
) -> BalanceSheetDocument:
    return await process_upload(
        Upload(data),
        filename=filename,
        content_type=content_type,
        storage=storage,
        db=db,
        settings=settings,
    )


BALANCED_PDF_ROWS: list[tuple[str, str | None]] = [
    ("Acme Manufacturing Limited", None),
    ("Balance Sheet as at 31 March 2024", None),
    ("Total Assets", "150,000"),
    ("Total Liabilities", "90,000"),
    ("Total Shareholders' Equity", "60,000"),
]


class TestHappyPath:
    async def test_a_balancing_sheet_is_validated(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        document = await run(simple_balance_sheet_pdf(), test_db, storage, settings)

        assert document.status is DocumentStatus.VALIDATED
        assert document.validation.passed is True
        assert document.equation_check.balanced is True
        assert document.equation_check.difference == Decimal(0)

    async def test_the_three_totals_are_extracted(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        document = await run(simple_balance_sheet_pdf(), test_db, storage, settings)

        assert document.extracted.assets.total == Decimal("150000")
        assert document.extracted.liabilities.total == Decimal("90000")
        assert document.extracted.equity.total == Decimal("60000")

    async def test_line_items_are_left_for_module_2(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        """Module 1 extracts totals only. Filling these would be a false claim."""
        document = await run(simple_balance_sheet_pdf(), test_db, storage, settings)

        assert document.extracted.assets.line_items == []
        assert document.extracted.liabilities.line_items == []
        assert document.extracted.equity.line_items == []

    async def test_a_workbook_is_processed_the_same_way(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        document = await run(
            simple_balance_sheet_xlsx(),
            test_db,
            storage,
            settings,
            filename="sheet.xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        assert document.status is DocumentStatus.VALIDATED
        assert document.extracted.assets.total == Decimal("150000")

    async def test_traceability_survives_to_the_stored_document(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        """Every figure must be traceable back to where it was printed."""
        document = await run(simple_balance_sheet_pdf(), test_db, storage, settings)
        reloaded = BalanceSheetDocument.from_mongo(
            await test_db[BALANCE_SHEETS].find_one({"_id": ObjectId(document.id)})
        )

        assets = reloaded.extracted.assets
        assert assets.total_raw == "150,000"
        assert assets.total_label.startswith("Total Assets")
        assert assets.total_source.page_index == 0
        assert reloaded.preliminary is not None
        assert reloaded.preliminary.pages[0].text

    async def test_money_round_trips_as_decimal_not_float(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        document = await run(simple_balance_sheet_pdf(), test_db, storage, settings)
        stored = await test_db[BALANCE_SHEETS].find_one({"_id": ObjectId(document.id)})

        raw_total = stored["extracted"]["assets"]["total"]
        assert not isinstance(raw_total, float)
        assert raw_total.to_decimal() == Decimal("150000")


class TestSingleperiodScope:
    async def test_a_comparative_sheet_uses_only_the_most_recent_period(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        document = await run(comparative_balance_sheet_pdf(), test_db, storage, settings)

        assert document.status is DocumentStatus.VALIDATED
        assert document.extracted.assets.total == Decimal("150000")
        assert document.period.selected.year == 2024

    async def test_the_other_period_is_recorded_but_not_analysed(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        """Recorded for traceability. Never compared - that is out of scope."""
        document = await run(comparative_balance_sheet_pdf(), test_db, storage, settings)

        assert {c.year for c in document.period.candidates} == {2023, 2024}
        assert document.extracted.period_end_date.year == 2024
        # There is one set of figures on the document, not two.
        assert not hasattr(document.extracted, "periods")


class TestUnitsAreRecordedNotApplied:
    async def test_currency_is_recorded(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        document = await run(simple_balance_sheet_pdf(), test_db, storage, settings)
        assert document.units.currency == "INR"
        assert document.extracted.currency == "INR"

    async def test_a_scale_is_noted_without_multiplying_anything(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        pdf = text_pdf(
            [
                ("Balance Sheet as at 31 March 2024", None),
                ("(All amounts in thousands of INR)", None),
                ("Total Assets", "150"),
                ("Total Liabilities", "90"),
                ("Total Equity", "60"),
            ]
        )
        document = await run(pdf, test_db, storage, settings)

        assert document.units.scale_factor == Decimal("1000")
        assert document.extracted.assets.total == Decimal("150"), (
            "the scale was applied - normalisation belongs to Module 2"
        )


class TestHybridRejectionSemantics:
    """Not-a-Balance-Sheet raises; a failing Balance Sheet returns its verdict."""

    async def test_a_non_balance_sheet_raises_and_is_still_recorded(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        pdf = text_pdf(
            [
                ("Statement of Profit and Loss for the year ended 31 March 2024", None),
                ("Revenue from operations", "500,000"),
                ("Profit before taxation for the year", "80,000"),
            ]
        )
        with pytest.raises(NotABalanceSheetError):
            await run(pdf, test_db, storage, settings)

        stored = await test_db[BALANCE_SHEETS].find_one({})
        assert stored is not None, "a rejected submission must be kept for audit"
        assert stored["status"] == DocumentStatus.REJECTED.value
        assert stored["rejection"]["reason"] == RejectionReason.NOT_A_BALANCE_SHEET.value

    async def test_an_unbalanced_sheet_returns_its_verdict_rather_than_raising(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        """It *is* a Balance Sheet, so the finding is the useful answer."""
        pdf = text_pdf(
            [
                ("Balance Sheet as at 31 March 2024", None),
                ("Total Assets", "150,000"),
                ("Total Liabilities", "90,000"),
                ("Total Equity", "40,000"),
            ]
        )
        document = await run(pdf, test_db, storage, settings)

        assert document.status is DocumentStatus.REJECTED
        assert document.rejection.reason is RejectionReason.EQUATION_UNBALANCED
        assert document.validation.passed is False
        assert document.equation_check.balanced is False
        assert document.equation_check.difference == Decimal("20000")

    async def test_a_missing_total_names_what_is_missing(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        pdf = text_pdf(
            [
                ("Balance Sheet as at 31 March 2024", None),
                ("ASSETS", None),
                ("Total Assets", "150,000"),
                ("LIABILITIES", None),
                ("Total Liabilities", "90,000"),
                ("SHAREHOLDERS' EQUITY", None),
            ]
        )
        document = await run(pdf, test_db, storage, settings)

        assert document.status is DocumentStatus.REJECTED
        assert document.rejection.reason is RejectionReason.MISSING_REQUIRED_FIELDS
        assert document.validation.missing_fields == ["equity"]
        assert document.equation_check is None, (
            "no equation may be reported when a figure was never found"
        )

    async def test_an_unreadable_document_is_recorded_then_raised(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        with pytest.raises(UnreadableDocumentError):
            await run(b"%PDF-1.4\n" + b"\x00" * 400, test_db, storage, settings)

        stored = await test_db[BALANCE_SHEETS].find_one({})
        assert stored["status"] == DocumentStatus.REJECTED.value
        assert stored["rejection"]["reason"] == RejectionReason.UNREADABLE.value

    async def test_the_identification_evidence_is_kept_on_a_rejection(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        """A refusal has to be arguable, so the reasoning is stored with it."""
        pdf = text_pdf(
            [
                ("Notice of the Annual General Meeting of members", None),
                ("The meeting will be held on 12 August 2024 at the registered office", None),
            ]
        )
        with pytest.raises(NotABalanceSheetError):
            await run(pdf, test_db, storage, settings)

        stored = await test_db[BALANCE_SHEETS].find_one({})
        assert stored["identification"]["is_balance_sheet"] is False
        assert "score" in stored["identification"]


class TestProgressivePersistence:
    async def test_the_record_exists_before_parsing_is_attempted(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        """A failure mid-pipeline must not leave the submission untraceable."""
        with pytest.raises(UnreadableDocumentError):
            await run(b"%PDF-1.4\n" + b"\x00" * 400, test_db, storage, settings)

        assert await test_db[BALANCE_SHEETS].count_documents({}) == 1

    async def test_the_original_file_is_stored_outside_mongo(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        data = simple_balance_sheet_pdf()
        document = await run(data, test_db, storage, settings)

        assert await storage.open(document.source.ref) == data
        stored = await test_db[BALANCE_SHEETS].find_one({"_id": ObjectId(document.id)})
        assert not any(isinstance(v, bytes) for v in stored["source"].values())

    async def test_the_storage_key_comes_from_the_hash_not_the_filename(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        """Client filenames are attacker-controlled and never touch a path."""
        document = await run(
            simple_balance_sheet_pdf(),
            test_db,
            storage,
            settings,
            filename="../../../../etc/passwd.pdf",
        )
        assert document.source.ref.key.startswith(document.source.sha256[:2])
        assert ".." not in document.source.ref.key

    async def test_the_preliminary_extraction_is_preserved(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        """Module 2 re-derives from this, so it survives alongside the totals."""
        document = await run(simple_balance_sheet_xlsx(), test_db, storage, settings,
                             filename="sheet.xlsx", content_type="application/vnd.ms-excel")

        assert document.preliminary is not None
        rows = document.preliminary.pages[0].tables[0].rows
        assert any("(All figures in INR)" in (cell or "") for row in rows for cell in row)

    async def test_an_oversized_preliminary_spills_to_storage(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        """MongoDB caps a document at 16 MB; the raw output is kept regardless."""
        tiny = settings.model_copy(update={"max_prelim_inline_bytes": 200})
        document = await run(simple_balance_sheet_pdf(), test_db, storage, tiny)

        assert document.preliminary_ref is not None
        assert await storage.open(document.preliminary_ref)
        stored = await test_db[BALANCE_SHEETS].find_one({"_id": ObjectId(document.id)})
        assert "preliminary" not in stored


class TestDeduplication:
    async def test_reuploading_identical_bytes_returns_the_same_document(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        data = simple_balance_sheet_pdf()
        first = await run(data, test_db, storage, settings)
        second = await run(data, test_db, storage, settings)

        assert first.id == second.id
        assert second.status is DocumentStatus.VALIDATED
        assert await test_db[BALANCE_SHEETS].count_documents({}) == 1


class TestUploadRefusals:
    async def test_an_unsupported_extension_never_reaches_storage(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        with pytest.raises(InvalidUploadError):
            await run(b"whatever", test_db, storage, settings, filename="malware.exe")

        assert list(storage.root.rglob("*")) == []
        assert await test_db[BALANCE_SHEETS].count_documents({}) == 0

    async def test_contents_that_contradict_the_extension_are_refused(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        with pytest.raises(InvalidUploadError, match="does not look like a PDF"):
            await run(simple_balance_sheet_xlsx(), test_db, storage, settings)

        assert await test_db[BALANCE_SHEETS].count_documents({}) == 0

    async def test_an_oversized_upload_is_refused_before_storage(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        small = settings.model_copy(update={"max_upload_bytes": 100})
        with pytest.raises(InvalidUploadError, match="exceeds"):
            await run(simple_balance_sheet_pdf(), test_db, storage, small)

        assert list(storage.root.rglob("*")) == []
        assert await test_db[BALANCE_SHEETS].count_documents({}) == 0


class TestCombinedFooterSheet:
    """The document shape that first exposed the combined-footer defect.

    It closes with ``TOTAL LIABILITIES + EQUITY  2,300,000``, restating assets.
    Read as the liabilities total it inflates liabilities by the whole of
    equity, and a sheet that balances is rejected. End to end here, because the
    defect only became visible once the whole workflow ran.
    """

    async def test_the_sheet_is_validated_not_rejected(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        document = await run(
            abc_manufacturing_balance_sheet_pdf(), test_db, storage, settings
        )

        assert document.status is DocumentStatus.VALIDATED
        assert document.equation_check.balanced is True
        assert document.equation_check.difference == Decimal(0)

    async def test_liabilities_exclude_the_balancing_footer(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        document = await run(
            abc_manufacturing_balance_sheet_pdf(), test_db, storage, settings
        )

        assert document.extracted.liabilities.total == Decimal("1350000")
        assert document.extracted.equity.total == Decimal("950000")
        assert document.extracted.assets.total == Decimal("2300000")


class TestSideBySideSheet:
    """A Balance Sheet printed horizontally, end to end.

    Assets run down the left of the page and Liabilities and Equity down the
    right, so ``Total Liabilities`` shares its visual row with an unrelated
    assets line. Reading only the leading cell of each row reports this sheet
    as missing its liabilities while it balances perfectly.
    """

    async def test_it_is_validated_not_rejected(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        document = await run(
            side_by_side_balance_sheet_pdf(), test_db, storage, settings
        )

        assert document.status is DocumentStatus.VALIDATED
        assert document.validation.passed is True
        assert document.equation_check.balanced is True

    async def test_the_right_hand_column_totals_are_extracted(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        document = await run(
            side_by_side_balance_sheet_pdf(), test_db, storage, settings
        )

        assert document.extracted.assets.total == Decimal("2300000")
        assert document.extracted.liabilities.total == Decimal("1350000")
        assert document.extracted.equity.total == Decimal("950000")
