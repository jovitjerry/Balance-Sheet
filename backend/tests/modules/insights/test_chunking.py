"""Turning stored page text into retrievable passages.

The input is text Module 1 already extracted. Nothing here re-opens a file,
re-runs OCR, or re-flattens tables into prose - a chunk containing text the
document never printed would be a fabricated citation waiting to happen.
"""

from __future__ import annotations

from app.core.schemas import PageRole
from app.modules.insights.chunking import (
    CHUNK_OVERLAP,
    CHUNK_TARGET,
    MAX_CHUNK,
    chunks_for,
)
from tests.modules.insights.fixtures import (
    BALANCE_SHEET_PAGE,
    NOTES_PAGE,
    analyzed_document,
    document_with_notes,
)


class TestChunksComeFromStoredText:
    def test_a_short_page_becomes_one_chunk(self) -> None:
        """A one-page Balance Sheet is ~1,000 characters. Do not pad it."""
        chunks = chunks_for(analyzed_document())
        assert 1 <= len(chunks) <= 3

    def test_every_chunk_is_a_verbatim_slice_of_the_page(self) -> None:
        """char_start/char_end must actually locate the text on the page.

        This is what makes a citation checkable rather than merely asserted: a
        reader can go to the stored page and find the quoted words at the
        offsets recorded.
        """
        document = document_with_notes()
        pages = [page.text for page in document.preliminary.pages]

        for chunk in chunks_for(document):
            source = pages[chunk.page_index]
            assert source[chunk.char_start : chunk.char_end] == chunk.text

    def test_nothing_is_invented(self) -> None:
        every = "".join(page.text for page in document_with_notes().preliminary.pages)
        for chunk in chunks_for(document_with_notes()):
            assert chunk.text in every

    def test_a_document_with_no_preliminary_yields_nothing(self) -> None:
        document = analyzed_document().model_copy(update={"preliminary": None})
        assert chunks_for(document) == []

    def test_an_empty_page_is_skipped_rather_than_stored_blank(self) -> None:
        document = analyzed_document(pages=["", "   \n  \n "])
        assert chunks_for(document) == []


class TestSizes:
    def test_no_chunk_exceeds_the_hard_maximum(self) -> None:
        long_page = "\n\n".join(f"Paragraph {n}. " + "word " * 120 for n in range(8))
        for chunk in chunks_for(analyzed_document(pages=[long_page])):
            assert len(chunk.text) <= MAX_CHUNK

    def test_a_long_page_splits_into_several(self) -> None:
        long_page = "\n\n".join(f"Paragraph {n}. " + "word " * 120 for n in range(8))
        assert len(chunks_for(analyzed_document(pages=[long_page]))) > 3

    def test_consecutive_chunks_overlap(self) -> None:
        """So a sentence split across a boundary is retrievable from either side."""
        long_page = " ".join(f"sentence number {n} here." for n in range(400))
        chunks = chunks_for(analyzed_document(pages=[long_page]))

        assert len(chunks) >= 2
        for earlier, later in zip(chunks, chunks[1:]):
            if earlier.page_index != later.page_index:
                continue
            assert later.char_start < earlier.char_end, "no overlap between chunks"

    def test_no_chunk_is_empty_or_whitespace(self) -> None:
        for chunk in chunks_for(document_with_notes()):
            assert chunk.text.strip()

    def test_words_are_not_split_in_half(self) -> None:
        long_page = " ".join(f"antidisestablishmentarianism{n}" for n in range(200))
        for chunk in chunks_for(analyzed_document(pages=[long_page])):
            assert not chunk.text.startswith("ism")


class TestChunksNeverSpanPages:
    def test_each_chunk_belongs_to_exactly_one_page(self) -> None:
        """A chunk citing two pages can cite neither."""
        document = document_with_notes()
        pages = [page.text for page in document.preliminary.pages]

        for chunk in chunks_for(document):
            assert 0 <= chunk.page_index < len(pages)
            assert chunk.text in pages[chunk.page_index]

    def test_chunk_index_restarts_on_each_page(self) -> None:
        chunks = chunks_for(document_with_notes())
        first_of_each = {}
        for chunk in chunks:
            first_of_each.setdefault(chunk.page_index, chunk.chunk_index)
        assert set(first_of_each.values()) == {0}


class TestPageRole:
    def test_the_balance_sheet_page_is_tagged_as_such(self) -> None:
        chunks = chunks_for(document_with_notes())
        page_zero = [chunk for chunk in chunks if chunk.page_index == 0]
        assert page_zero
        assert all(chunk.page_role is PageRole.BALANCE_SHEET for chunk in page_zero)

    def test_a_notes_page_is_supplementary(self) -> None:
        """Retrievable, never analysed. No figure is ever taken from one."""
        chunks = chunks_for(document_with_notes())
        notes = [chunk for chunk in chunks if chunk.page_index == 1]
        assert notes
        assert all(chunk.page_role is PageRole.SUPPLEMENTARY for chunk in notes)

    def test_the_role_comes_from_module_1s_stored_evidence(self) -> None:
        """Derived from identification signals, never re-derived by re-reading."""
        document = document_with_notes(balance_sheet_pages=(1,))
        roles = {chunk.page_index: chunk.page_role for chunk in chunks_for(document)}
        assert roles[1] is PageRole.BALANCE_SHEET
        assert roles[0] is PageRole.SUPPLEMENTARY


class TestMetadata:
    def test_every_chunk_is_scoped_to_its_document(self) -> None:
        """document_id is the mandatory retrieval filter. It is never absent."""
        from tests.modules.insights.fixtures import DOCUMENT_ID

        for chunk in chunks_for(document_with_notes()):
            assert chunk.document_id == DOCUMENT_ID

    def test_chunks_record_what_built_them(self) -> None:
        """So a chunking change can be told from a model change when re-indexing."""
        for chunk in chunks_for(document_with_notes()):
            assert chunk.chunk_spec_version
            assert chunk.embedding == []  # embedding is a later, separate step


class TestDeterminism:
    def test_chunking_the_same_document_twice_gives_the_same_chunks(self) -> None:
        first = chunks_for(document_with_notes())
        second = chunks_for(document_with_notes())

        assert [(chunk.page_index, chunk.char_start, chunk.text) for chunk in first] == [
            (chunk.page_index, chunk.char_start, chunk.text) for chunk in second
        ]


class TestTheRealPages:
    def test_the_policy_paragraph_survives_intact_in_some_chunk(self) -> None:
        """A policy split across two chunks is a policy neither one answers."""
        chunks = chunks_for(document_with_notes())
        notes = [chunk.text for chunk in chunks if chunk.page_index == 1]

        assert any("first-in, first-out" in text for text in notes)
        assert any("straight-line basis" in text for text in notes)

    def test_the_constants_are_sane(self) -> None:
        assert CHUNK_OVERLAP < CHUNK_TARGET < MAX_CHUNK
