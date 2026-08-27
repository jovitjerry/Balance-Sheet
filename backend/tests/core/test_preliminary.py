"""Reading back the preliminary extraction, wherever Module 1 put it.

Module 1 stores the raw parser output inline in the MongoDB document, unless it
is large enough to threaten the 16 MB document cap - in which case it is written
to file storage and the document keeps only a ``StorageRef``.

Both halves of that decision were implemented. Reading the second one back was
not: ``preliminary_ref`` was written and never loaded, so a document that took
the offload path came back from Mongo with ``preliminary = None`` and every
later module treated it as unreadable. These tests pin the read side.
"""

from __future__ import annotations

import json

import pytest

from app.core.errors import StorageError
from app.core.preliminary import load_preliminary
from app.core.schemas import (
    BalanceSheetDocument,
    ParserKind,
    PositionedWord,
    PreliminaryExtraction,
    RawTable,
    SourceFile,
    SourcePage,
    StorageRef,
)
from app.core.storage import LocalFileStorage, key_for

SHA = "c" * 64


def _document(**kwargs: object) -> BalanceSheetDocument:
    return BalanceSheetDocument(
        source=SourceFile(
            filename="sheet.pdf",
            content_type="application/pdf",
            size_bytes=1,
            sha256=SHA,
            ref=StorageRef(
                backend="local",
                key="cc/cc/x.pdf",
                size_bytes=1,
                content_type="application/pdf",
            ),
        ),
        **kwargs,  # type: ignore[arg-type]
    )


def _preliminary() -> PreliminaryExtraction:
    """Raw output carrying every field kind the JSON round trip has to survive."""
    return PreliminaryExtraction(
        parser=ParserKind.PDF_OCR,
        pages=[
            SourcePage(
                index=0,
                name=None,
                text="ASSETS\nCash and cash equivalents 125,000",
                tables=[RawTable(rows=[["Cash", "(2,300)"], ["Stock", None]])],
                ocr_used=True,
                ocr_confidence=88.5,
                words=[
                    PositionedWord(
                        text="ASSETS", left=72.0, top=740.0, width=40.5,
                        height=11.25, confidence=96.5,
                    )
                ],
                page_width=612.0,
                page_height=792.0,
            )
        ],
        warnings=["page 1 was scanned"],
    )


class TestInlinePreliminary:
    async def test_it_returns_what_is_on_the_document(self) -> None:
        preliminary = _preliminary()
        document = _document(preliminary=preliminary)

        assert await load_preliminary(document) is preliminary

    async def test_it_does_not_need_storage_when_the_payload_is_inline(self) -> None:
        """The common path must not require a file store to be wired in."""
        document = _document(preliminary=_preliminary())
        assert await load_preliminary(document, storage=None) is not None


class TestOffloadedPreliminary:
    async def test_it_loads_the_payload_from_file_storage(
        self, storage: LocalFileStorage
    ) -> None:
        """The case that was silently broken: nothing inline, everything in the store."""
        preliminary = _preliminary()
        ref = await storage.save(
            json.dumps(
                preliminary.model_dump(mode="python", exclude_none=True), default=str
            ).encode("utf-8"),
            key=key_for(SHA, ".preliminary.json"),
            content_type="application/json",
        )
        document = _document(preliminary_ref=ref)

        loaded = await load_preliminary(document, storage=storage)

        assert loaded is not None
        assert loaded.parser is ParserKind.PDF_OCR
        assert loaded.pages[0].text.startswith("ASSETS")

    async def test_the_round_trip_preserves_every_field(
        self, storage: LocalFileStorage
    ) -> None:
        """Word geometry and raw table cells are what Modules 2 and 4 read.

        Raw cells must come back as the strings they were printed as -
        ``"(2,300)"`` still parenthesised, ``None`` still absent - because the
        printed convention is evidence, and coercing it is what the raw payload
        exists to prevent.
        """
        original = _preliminary()
        ref = await storage.save(
            json.dumps(
                original.model_dump(mode="python", exclude_none=True), default=str
            ).encode("utf-8"),
            key=key_for(SHA, ".preliminary.json"),
            content_type="application/json",
        )

        loaded = await load_preliminary(_document(preliminary_ref=ref), storage=storage)

        assert loaded is not None
        page = loaded.pages[0]
        assert page.tables[0].rows == [["Cash", "(2,300)"], ["Stock", None]]
        assert page.words[0].text == "ASSETS"
        assert page.words[0].left == 72.0
        assert page.words[0].confidence == 96.5
        assert page.ocr_used is True
        assert page.page_width == 612.0
        assert loaded.warnings == ["page 1 was scanned"]

    async def test_inline_wins_when_both_are_somehow_present(
        self, storage: LocalFileStorage
    ) -> None:
        """Never fetch what is already in hand."""
        ref = await storage.save(
            b'{"parser": "excel", "pages": [], "warnings": []}',
            key=key_for(SHA, ".preliminary.json"),
            content_type="application/json",
        )
        document = _document(preliminary=_preliminary(), preliminary_ref=ref)

        loaded = await load_preliminary(document, storage=storage)

        assert loaded is not None
        assert loaded.parser is ParserKind.PDF_OCR  # the inline one


class TestFailureIsLoudRatherThanEmpty:
    async def test_a_ref_with_no_store_raises_instead_of_reporting_nothing(
        self,
    ) -> None:
        """Returning None here is exactly the bug this module exists to fix.

        "I was not given a file store" and "this document has no preliminary
        extraction" are different facts, and the second one sends a caller off
        to report a perfectly good Balance Sheet as unreadable.
        """
        document = _document(
            preliminary_ref=StorageRef(
                backend="local",
                key="cc/cc/x.preliminary.json",
                size_bytes=10,
                content_type="application/json",
            )
        )
        with pytest.raises(StorageError, match="file store"):
            await load_preliminary(document, storage=None)

    async def test_a_missing_object_raises(self, storage: LocalFileStorage) -> None:
        document = _document(
            preliminary_ref=StorageRef(
                backend="local",
                key="cc/cc/absent.preliminary.json",
                size_bytes=10,
                content_type="application/json",
            )
        )
        with pytest.raises(StorageError):
            await load_preliminary(document, storage=storage)

    async def test_a_corrupt_payload_raises_rather_than_half_loading(
        self, storage: LocalFileStorage
    ) -> None:
        ref = await storage.save(
            b"{not json at all",
            key=key_for(SHA, ".preliminary.json"),
            content_type="application/json",
        )
        with pytest.raises(StorageError, match="could not be read"):
            await load_preliminary(_document(preliminary_ref=ref), storage=storage)

    async def test_a_document_with_neither_reports_nothing(self) -> None:
        """The genuine "no preliminary" case still returns None."""
        assert await load_preliminary(_document()) is None
