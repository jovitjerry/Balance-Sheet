"""Module 1 upload and validation.

Validation tests are pure. The ingest tests use ``test_db`` and skip when no
MongoDB cluster is reachable.
"""

from __future__ import annotations

from typing import Any

import pytest
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings
from app.core.db import BALANCE_SHEETS
from app.core.errors import InvalidUploadError
from app.core.schemas import DocumentStatus
from app.core.storage import LocalFileStorage, sha256_of
from app.modules.ingestion.service import ingest, validate_upload

PDF = b"%PDF-1.7 pretend balance sheet"


class TestValidateUpload:
    def test_a_pdf_is_accepted(self, settings: Settings) -> None:
        assert validate_upload("sheet.pdf", len(PDF), settings) == ".pdf"

    @pytest.mark.parametrize("name", ["sheet.xlsx", "sheet.xls", "SHEET.PDF"])
    def test_permitted_extensions(self, name: str, settings: Settings) -> None:
        validate_upload(name, 10, settings)

    @pytest.mark.parametrize("name", ["sheet.exe", "sheet.txt", "sheet"])
    def test_unsupported_extensions_are_refused(
        self, name: str, settings: Settings
    ) -> None:
        with pytest.raises(InvalidUploadError, match="Unsupported file type"):
            validate_upload(name, 10, settings)

    def test_empty_filename_is_refused(self, settings: Settings) -> None:
        with pytest.raises(InvalidUploadError, match="filename is required"):
            validate_upload("   ", 10, settings)

    def test_empty_file_is_refused(self, settings: Settings) -> None:
        with pytest.raises(InvalidUploadError, match="empty"):
            validate_upload("sheet.pdf", 0, settings)

    def test_oversized_file_is_refused(self, settings: Settings) -> None:
        with pytest.raises(InvalidUploadError, match="exceeding"):
            validate_upload("sheet.pdf", settings.max_upload_bytes + 1, settings)


class TestIngest:
    async def test_it_stores_the_file_outside_mongo_and_records_a_ref(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        document = await ingest(
            PDF,
            filename="sheet.pdf",
            content_type="application/pdf",
            storage=storage,
            db=test_db,
            settings=settings,
        )

        assert document.id is not None
        assert document.status is DocumentStatus.UPLOADED
        assert document.source.sha256 == sha256_of(PDF)

        # The bytes are on disk...
        assert await storage.open(document.source.ref) == PDF
        # ...and the stored record holds only a reference to them.
        stored = await test_db[BALANCE_SHEETS].find_one({"_id": {"$exists": True}})
        assert stored is not None
        assert stored["source"]["ref"]["key"] == document.source.ref.key
        assert not any(isinstance(value, bytes) for value in stored["source"].values())

    async def test_reuploading_identical_bytes_does_not_duplicate(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        kwargs = dict(
            filename="sheet.pdf",
            content_type="application/pdf",
            storage=storage,
            db=test_db,
            settings=settings,
        )
        first = await ingest(PDF, **kwargs)  # type: ignore[arg-type]
        second = await ingest(PDF, **kwargs)  # type: ignore[arg-type]

        assert first.id == second.id
        assert await test_db[BALANCE_SHEETS].count_documents({}) == 1

    async def test_an_invalid_file_is_refused_before_anything_is_stored(
        self,
        test_db: AsyncDatabase[dict[str, Any]],
        storage: LocalFileStorage,
        settings: Settings,
    ) -> None:
        with pytest.raises(InvalidUploadError):
            await ingest(
                b"nope",
                filename="malware.exe",
                content_type="application/octet-stream",
                storage=storage,
                db=test_db,
                settings=settings,
            )

        assert list(storage.root.rglob("*")) == []
        assert await test_db[BALANCE_SHEETS].count_documents({}) == 0
