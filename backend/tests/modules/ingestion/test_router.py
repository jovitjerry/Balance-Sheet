"""The Module 1 HTTP surface.

What a caller sees: the status codes that encode the hybrid rejection
semantics, and error bodies that carry a verdict and nothing internal.

These use ``api_client``, which depends on ``test_db``, so they are marked
``integration`` and skip without a cluster.
"""

from __future__ import annotations

import re

import pytest
from httpx import AsyncClient

from tests.modules.ingestion.fixtures import (
    Text,
    comparative_balance_sheet_pdf,
    make_text_pdf,
    simple_balance_sheet_pdf,
    simple_balance_sheet_xlsx,
)

UPLOAD = "/api/v1/documents"

# Anything that would betray how the server is built, rather than what it found.
LEAK_PATTERNS = (
    re.compile(r"Traceback", re.IGNORECASE),
    re.compile(r"[A-Za-z]:\\\\|[A-Za-z]:/"),          # Windows filesystem paths
    re.compile(r"/(?:home|usr|var|etc)/"),            # POSIX filesystem paths
    re.compile(r"mongodb(?:\+srv)?://", re.IGNORECASE),
    re.compile(r"\.venv|site-packages"),
    re.compile(r"pdfminer|pdfplumber|openpyxl|pytesseract|zipfile", re.IGNORECASE),
    re.compile(r"line \d+, in "),
)


def assert_no_internals(body: str) -> None:
    for pattern in LEAK_PATTERNS:
        assert not pattern.search(body), f"response leaked internals: {pattern.pattern}"


def upload_files(data: bytes, name: str = "sheet.pdf", mime: str = "application/pdf"):
    return {"file": (name, data, mime)}


def text_pdf(rows: list[tuple[str, str | None]]) -> bytes:
    runs: list[Text] = []
    y = 740.0
    for label, value in rows:
        runs.append(Text(72, y, label))
        if value is not None:
            runs.append(Text(420, y, value))
        y -= 18.0
    return make_text_pdf([runs])


class TestUploadSucceeds:
    async def test_a_balancing_sheet_returns_201_and_the_figures(
        self, api_client: AsyncClient
    ) -> None:
        response = await api_client.post(
            UPLOAD, files=upload_files(simple_balance_sheet_pdf())
        )

        assert response.status_code == 201
        body = response.json()
        # A sheet that passes Module 1 continues into Module 2, so the status
        # it comes to rest at is `extracted`. The Module 1 verdict is still
        # right here on the document - the equation check below is it.
        assert body["status"] == "extracted"
        assert body["equation_check"]["balanced"] is True
        assert body["extracted"]["assets"]["total"] == "150000"

    async def test_the_pipeline_continues_into_line_item_extraction(
        self, api_client: AsyncClient
    ) -> None:
        """Module 1 leaves `line_items` empty; Module 2 is what fills it in."""
        response = await api_client.post(
            UPLOAD, files=upload_files(simple_balance_sheet_pdf())
        )

        assets = response.json()["extracted"]["assets"]
        assert assets["line_items"], "the upload did not continue into Module 2"
        assert {item["label"] for item in assets["line_items"]} == {
            "Cash and cash equivalents",
            "Inventories",
            "Property, plant and equipment",
        }

    async def test_a_workbook_is_accepted(self, api_client: AsyncClient) -> None:
        response = await api_client.post(
            UPLOAD,
            files=upload_files(
                simple_balance_sheet_xlsx(),
                "sheet.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        )
        assert response.status_code == 201
        assert response.json()["status"] == "extracted"

    async def test_a_comparative_sheet_reports_the_period_it_chose(
        self, api_client: AsyncClient
    ) -> None:
        response = await api_client.post(
            UPLOAD, files=upload_files(comparative_balance_sheet_pdf())
        )

        body = response.json()
        assert response.status_code == 201
        assert body["period"]["selected"]["year"] == 2024
        assert len(body["period"]["candidates"]) == 2
        assert "Most recent" in body["period"]["reason"]

    async def test_money_is_serialised_exactly_not_as_a_float(
        self, api_client: AsyncClient
    ) -> None:
        """JSON numbers are IEEE doubles; money goes over the wire as a string."""
        response = await api_client.post(
            UPLOAD, files=upload_files(simple_balance_sheet_pdf())
        )
        assert isinstance(response.json()["extracted"]["assets"]["total"], str)


class TestHybridRejectionStatusCodes:
    async def test_a_failing_balance_sheet_is_201_with_its_verdict(
        self, api_client: AsyncClient
    ) -> None:
        """It is a Balance Sheet. The finding is the answer, not an error."""
        pdf = text_pdf(
            [
                ("Balance Sheet as at 31 March 2024", None),
                ("Total Assets", "150,000"),
                ("Total Liabilities", "90,000"),
                ("Total Equity", "40,000"),
            ]
        )
        response = await api_client.post(UPLOAD, files=upload_files(pdf))

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "rejected"
        assert body["rejection"]["reason"] == "equation_unbalanced"
        assert body["validation"]["passed"] is False
        assert body["equation_check"]["difference"] == "20000"

    async def test_a_missing_total_is_201_naming_the_gap(
        self, api_client: AsyncClient
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
        response = await api_client.post(UPLOAD, files=upload_files(pdf))

        assert response.status_code == 201
        body = response.json()
        assert body["validation"]["missing_fields"] == ["equity"]
        assert body.get("equation_check") is None

    async def test_a_non_balance_sheet_is_422(self, api_client: AsyncClient) -> None:
        """Nothing here to review, so it is an error rather than a verdict."""
        pdf = text_pdf(
            [
                ("Statement of Profit and Loss for the year ended 31 March 2024", None),
                ("Revenue from operations", "500,000"),
                ("Profit before taxation for the year", "80,000"),
            ]
        )
        response = await api_client.post(UPLOAD, files=upload_files(pdf))

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "not_a_balance_sheet"

    async def test_an_unreadable_file_is_422(self, api_client: AsyncClient) -> None:
        response = await api_client.post(
            UPLOAD, files=upload_files(b"%PDF-1.4\n" + b"\x00" * 400)
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "unreadable_document"


class TestUploadRefusals:
    async def test_an_unsupported_extension_is_400(self, api_client: AsyncClient) -> None:
        response = await api_client.post(
            UPLOAD, files=upload_files(b"MZ\x90\x00", "malware.exe", "application/octet-stream")
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_upload"

    async def test_legacy_xls_is_refused(self, api_client: AsyncClient) -> None:
        response = await api_client.post(
            UPLOAD, files=upload_files(b"\xd0\xcf\x11\xe0", "sheet.xls", "application/vnd.ms-excel")
        )
        assert response.status_code == 400

    async def test_contents_that_contradict_the_extension_are_400(
        self, api_client: AsyncClient
    ) -> None:
        response = await api_client.post(
            UPLOAD, files=upload_files(simple_balance_sheet_xlsx(), "sheet.pdf")
        )
        assert response.status_code == 400
        assert "does not look like a PDF" in response.json()["error"]["message"]

    async def test_an_empty_file_is_400(self, api_client: AsyncClient) -> None:
        response = await api_client.post(UPLOAD, files=upload_files(b""))
        assert response.status_code == 400


class TestResponsesLeakNothing:
    @pytest.mark.parametrize(
        ("payload", "name"),
        [
            (b"%PDF-1.4\n" + b"\x00" * 400, "sheet.pdf"),
            (b"MZ\x90\x00" + b"\x00" * 100, "malware.exe"),
            (b"PK\x03\x04" + b"\x00" * 100, "sheet.xlsx"),
            (b"", "sheet.pdf"),
        ],
    )
    async def test_no_error_response_exposes_internals(
        self, api_client: AsyncClient, payload: bytes, name: str
    ) -> None:
        """Paths, stack traces, library names and the connection string stay in."""
        response = await api_client.post(UPLOAD, files=upload_files(payload, name))

        assert response.status_code >= 400
        assert_no_internals(response.text)
        assert set(response.json()["error"]) == {"code", "message"}

    async def test_a_traversal_filename_is_not_echoed_into_a_path(
        self, api_client: AsyncClient
    ) -> None:
        response = await api_client.post(
            UPLOAD,
            files=upload_files(simple_balance_sheet_pdf(), "../../../../etc/passwd.pdf"),
        )

        assert response.status_code == 201
        body = response.json()
        # The name is kept as metadata; the storage key comes from the hash.
        assert body["source"]["filename"] == "../../../../etc/passwd.pdf"
        assert ".." not in body["source"]["ref"]["key"]
        assert body["source"]["ref"]["key"].startswith(body["source"]["sha256"][:2])


class TestFetchDocument:
    async def test_a_stored_document_can_be_fetched(
        self, api_client: AsyncClient
    ) -> None:
        created = await api_client.post(
            UPLOAD, files=upload_files(simple_balance_sheet_pdf())
        )
        document_id = created.json()["_id"]

        response = await api_client.get(f"{UPLOAD}/{document_id}")
        assert response.status_code == 200
        assert response.json()["_id"] == document_id

    async def test_a_rejected_submission_is_still_retrievable(
        self, api_client: AsyncClient
    ) -> None:
        """Rejections are kept for audit, so they must be readable."""
        pdf = text_pdf(
            [
                ("Balance Sheet as at 31 March 2024", None),
                ("Total Assets", "150,000"),
                ("Total Liabilities", "90,000"),
                ("Total Equity", "40,000"),
            ]
        )
        created = await api_client.post(UPLOAD, files=upload_files(pdf))
        document_id = created.json()["_id"]

        response = await api_client.get(f"{UPLOAD}/{document_id}")
        assert response.status_code == 200
        assert response.json()["rejection"]["reason"] == "equation_unbalanced"

    async def test_an_unknown_id_is_404(self, api_client: AsyncClient) -> None:
        response = await api_client.get(f"{UPLOAD}/000000000000000000000000")
        assert response.status_code == 404

    async def test_a_malformed_id_is_400_without_echoing_it(
        self, api_client: AsyncClient
    ) -> None:
        response = await api_client.get(f"{UPLOAD}/not-an-object-id")
        assert response.status_code == 400
        assert_no_internals(response.text)
