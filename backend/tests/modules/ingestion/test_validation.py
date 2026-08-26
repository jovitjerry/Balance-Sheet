"""Module 1 upload validation: streaming size cap, and content that must
actually be what the extension claims.

All pure - no cluster, no filesystem.
"""

from __future__ import annotations

import zipfile

import pytest

from app.core.config import Settings
from app.core.errors import InvalidUploadError
from app.modules.ingestion.validation import (
    UploadKind,
    read_capped,
    validate_content,
    validate_filename,
    validate_upload,
)
from tests.modules.ingestion.fixtures import (
    make_plain_zip,
    make_text_pdf,
    simple_balance_sheet_pdf,
    simple_balance_sheet_xlsx,
)


class _Stream:
    """A minimal stand-in for ``UploadFile``, counting what was handed out."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self.position = 0

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            chunk = self._data[self.position :]
        else:
            chunk = self._data[self.position : self.position + size]
        self.position += len(chunk)
        return chunk


class TestReadCapped:
    async def test_it_reads_a_small_upload_whole(self) -> None:
        payload = b"a balance sheet" * 100
        assert await read_capped(_Stream(payload), max_bytes=1_000_000) == payload

    async def test_it_refuses_an_empty_upload(self) -> None:
        with pytest.raises(InvalidUploadError, match="empty"):
            await read_capped(_Stream(b""), max_bytes=1_000)

    async def test_it_refuses_an_oversized_upload(self) -> None:
        with pytest.raises(InvalidUploadError, match="exceeds"):
            await read_capped(_Stream(b"x" * 5_000), max_bytes=1_000)

    async def test_it_stops_reading_instead_of_buffering_the_whole_file(self) -> None:
        """The cap has to bite *during* the read, not after it.

        This is the whole point of streaming: a 5 GB upload must not become 5 GB
        of process memory before anyone checks the size. The assertion is that
        the stream was abandoned early, not merely that an error was raised.
        """
        huge = _Stream(b"x" * 5_000_000)
        with pytest.raises(InvalidUploadError):
            await read_capped(huge, max_bytes=1_000, chunk_size=256)

        assert huge.position < 5_000_000
        # At most the cap plus the chunk that tripped it was ever pulled in.
        assert huge.position <= 1_000 + 256

    async def test_a_file_exactly_at_the_cap_is_accepted(self) -> None:
        payload = b"y" * 1_000
        assert await read_capped(_Stream(payload), max_bytes=1_000) == payload


class TestValidateFilename:
    def test_pdf_and_xlsx_are_accepted(self, settings: Settings) -> None:
        assert validate_filename("sheet.pdf", settings) == ".pdf"
        assert validate_filename("sheet.xlsx", settings) == ".xlsx"

    def test_the_extension_check_is_case_insensitive(self, settings: Settings) -> None:
        assert validate_filename("SHEET.PDF", settings) == ".pdf"

    def test_legacy_xls_is_out_of_scope(self, settings: Settings) -> None:
        """.xls is the pre-2007 binary format. Only OOXML .xlsx is supported."""
        with pytest.raises(InvalidUploadError, match="Unsupported file type"):
            validate_filename("sheet.xls", settings)

    @pytest.mark.parametrize("name", ["sheet.exe", "sheet.txt", "sheet", "sheet.pdf.exe"])
    def test_unsupported_extensions_are_refused(
        self, name: str, settings: Settings
    ) -> None:
        with pytest.raises(InvalidUploadError, match="Unsupported file type"):
            validate_filename(name, settings)

    def test_an_empty_filename_is_refused(self, settings: Settings) -> None:
        with pytest.raises(InvalidUploadError, match="filename is required"):
            validate_filename("   ", settings)

    def test_a_traversal_filename_is_judged_on_its_suffix_only(
        self, settings: Settings
    ) -> None:
        """The filename is read for its suffix and nothing else.

        Storage keys come from the content hash, so a traversal attempt in the
        filename has nowhere to land - but the validator must not be the thing
        that reintroduces it.
        """
        assert validate_filename("../../../../etc/passwd.pdf", settings) == ".pdf"


class TestValidateContent:
    def test_a_real_pdf_named_pdf_is_accepted(self) -> None:
        assert validate_content(simple_balance_sheet_pdf(), ".pdf") is UploadKind.PDF

    def test_a_real_xlsx_named_xlsx_is_accepted(self) -> None:
        assert validate_content(simple_balance_sheet_xlsx(), ".xlsx") is UploadKind.XLSX

    def test_a_zip_wearing_a_pdf_extension_is_refused(self) -> None:
        """Extension checks alone are not validation.

        Handing a ZIP to a PDF parser because the name ended in .pdf is parser
        confusion; the bytes decide, not the label.
        """
        with pytest.raises(InvalidUploadError, match="does not look like a PDF"):
            validate_content(simple_balance_sheet_xlsx(), ".pdf")

    def test_a_pdf_wearing_an_xlsx_extension_is_refused(self) -> None:
        with pytest.raises(InvalidUploadError, match="does not look like"):
            validate_content(simple_balance_sheet_pdf(), ".xlsx")

    def test_an_executable_renamed_to_pdf_is_refused(self) -> None:
        with pytest.raises(InvalidUploadError, match="does not look like a PDF"):
            validate_content(b"MZ\x90\x00" + b"\x00" * 500, ".pdf")

    def test_a_pdf_header_after_leading_junk_is_still_a_pdf(self) -> None:
        """Real-world PDFs sometimes carry preamble bytes before ``%PDF-``."""
        assert validate_content(b"\r\n" + simple_balance_sheet_pdf(), ".pdf") is UploadKind.PDF

    def test_a_truncated_pdf_without_a_header_is_refused(self) -> None:
        with pytest.raises(InvalidUploadError, match="does not look like a PDF"):
            validate_content(b"1 0 obj << >> endobj", ".pdf")

    def test_a_plain_zip_is_not_a_workbook(self) -> None:
        """A .xlsx must be structurally an OOXML *workbook*, not just a ZIP."""
        with pytest.raises(InvalidUploadError, match="not a valid .xlsx workbook"):
            validate_content(make_plain_zip(), ".xlsx")

    def test_a_zip_missing_the_workbook_part_is_refused(self) -> None:
        archive = make_plain_zip({"[Content_Types].xml": b"<Types/>", "docProps/app.xml": b"<a/>"})
        with pytest.raises(InvalidUploadError, match="not a valid .xlsx workbook"):
            validate_content(archive, ".xlsx")

    def test_a_truncated_zip_is_refused_without_leaking_internals(self) -> None:
        """Losing the end-of-central-directory makes the archive unopenable."""
        truncated = simple_balance_sheet_xlsx()[:-200]
        with pytest.raises(InvalidUploadError, match="corrupt or incomplete") as caught:
            validate_content(truncated, ".xlsx")
        assert "Traceback" not in caught.value.message
        assert "zipfile" not in caught.value.message.lower()

    def test_damaged_member_data_is_left_for_the_parser_to_report(self) -> None:
        """Upload validation judges the *container*, and stops there.

        Corrupting a member's stored bytes leaves the central directory intact,
        so the archive still opens and still declares a workbook. Detecting that
        the XML inside is rubbish would mean inflating it here - which is exactly
        the work the bomb guard exists to avoid doing before the size is known.
        That verdict belongs to parsing, where it is recorded against the
        document as 'unreadable' rather than thrown away as a bad upload.
        """
        damaged = bytearray(simple_balance_sheet_xlsx())
        damaged[40:200] = b"\x00" * 160
        assert validate_content(bytes(damaged), ".xlsx") is UploadKind.XLSX

    def test_a_zip_bomb_is_refused(self) -> None:
        """A few kB that claim to expand to gigabytes never reaches openpyxl."""
        import io

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", b"<Types/>")
            archive.writestr("xl/workbook.xml", b"\x00" * (200 * 1024 * 1024))
        with pytest.raises(InvalidUploadError, match="expands"):
            validate_content(buffer.getvalue(), ".xlsx")

    def test_an_empty_pdf_page_set_is_still_structurally_a_pdf(self) -> None:
        """Content validation judges the container, not whether it says anything.

        'Readable but says nothing useful' is a *parsing* verdict, reached later
        and recorded against the document - not an upload rejection.
        """
        assert validate_content(make_text_pdf([[]]), ".pdf") is UploadKind.PDF


class TestValidateUpload:
    """The composed filename + size check, used before anything is stored."""

    def test_it_returns_the_extension(self, settings: Settings) -> None:
        assert validate_upload("sheet.pdf", 1024, settings) == ".pdf"

    def test_it_refuses_an_empty_file(self, settings: Settings) -> None:
        with pytest.raises(InvalidUploadError, match="empty"):
            validate_upload("sheet.pdf", 0, settings)

    def test_it_refuses_an_oversized_file(self, settings: Settings) -> None:
        with pytest.raises(InvalidUploadError, match="exceed"):
            validate_upload("sheet.pdf", settings.max_upload_bytes + 1, settings)
