"""Cutting stored page text into retrievable passages.

The input is :attr:`~app.core.schemas.SourcePage.text`, which Module 1 already
extracted. **Nothing here opens a file, runs OCR, or parses anything** - a
structural test enforces it. Tables and word boxes are deliberately not
re-flattened into prose either: that would manufacture text the document never
printed, and a citation quoting manufactured text is worse than no citation.

Two rules do most of the work.

**A chunk never spans a page.** A passage citing two pages can cite neither, and
the page number is the whole value of the citation to a reader holding the
document.

**A chunk is a verbatim slice, recorded by offset.** ``char_start``/``char_end``
index into the stored page, so a citation can be checked against the source
rather than taken on trust - and a chunk can be rebuilt without re-embedding.

Sizes are constants, not settings. They are part of a reproducible retrieval
contract: a deployment that could change the chunking could change an answer
without changing a version number, the same argument that keeps
``RATIO_DECIMAL_PLACES`` out of configuration in Module 3.
"""

from __future__ import annotations

from app.core.schemas import (
    BalanceSheetDocument,
    DocumentChunk,
    PageRole,
    PreliminaryExtraction,
)

# Bumped whenever the chunking rules change. Stored on every chunk, so a
# re-index can be triggered by comparison rather than by guesswork - and a
# chunking change stays distinguishable from an embedding-model change.
CHUNK_SPEC_VERSION = "1.0.0"

# A page in these documents runs to roughly a thousand characters, so 600 gives
# genuine granularity while keeping a citation small enough to locate by eye.
# The embedding model is not the constraint - nomic-embed-text takes 8192
# tokens - citation precision is.
CHUNK_TARGET = 600
MAX_CHUNK = 1000
# Enough that a sentence broken across a boundary is retrievable from either
# side. Larger would mostly duplicate storage for the same recall.
CHUNK_OVERLAP = 100

# Preferred split points, strongest first. A blank line usually separates whole
# policies; a line break separates rows of a statement. Splitting mid-word is
# never acceptable - it produces a fragment that embeds as noise.
_BOUNDARIES = ("\n\n", "\n", ". ", " ")


def chunks_for(document: BalanceSheetDocument) -> list[DocumentChunk]:
    """Every retrievable passage of ``document``, in reading order.

    Embeddings are **not** computed here. Chunking is deterministic and needs
    nothing installed; embedding needs a model and a network call. Keeping them
    apart is what lets the whole of this be unit-tested with Ollama stopped.
    """
    preliminary = document.preliminary
    if preliminary is None or document.id is None:
        return []

    roles = page_roles(document)
    chunks: list[DocumentChunk] = []

    for page in preliminary.pages:
        for position, (start, end) in enumerate(_spans(page.text)):
            chunks.append(
                DocumentChunk(
                    document_id=document.id,
                    page_index=page.index,
                    sheet_name=page.name,
                    page_role=roles.get(page.index, PageRole.SUPPLEMENTARY),
                    chunk_index=position,
                    char_start=start,
                    char_end=end,
                    text=page.text[start:end],
                    embedding=[],
                    embedding_model="",
                    embedding_dim=1,
                    chunk_spec_version=CHUNK_SPEC_VERSION,
                )
            )
    return chunks


def page_roles(document: BalanceSheetDocument) -> dict[int, PageRole]:
    """Which pages are the Balance Sheet and which are supplementary.

    Read from evidence Module 1 already stored - the identification signals and
    the source references of the three section totals - rather than re-derived
    by looking at the text again. Two implementations of "is this the Balance
    Sheet?" could disagree, and this one would be the silent loser.

    A page carrying no evidence is supplementary: notes, policies, the
    auditor's report. Those are **retrievable, never analysed** - no figure is
    ever taken from one, which is what keeps the Balance-Sheet-only scope while
    still letting a policy question be answered.
    """
    roles: dict[int, PageRole] = {}
    preliminary: PreliminaryExtraction | None = document.preliminary
    if preliminary is None:
        return roles

    sheet_pages: set[int] = set()
    if document.identification is not None:
        sheet_pages.update(
            signal.source.page_index for signal in document.identification.signals
        )
    if document.extracted is not None:
        for field_name in ("assets", "liabilities", "equity"):
            source = getattr(document.extracted, field_name).total_source
            if source is not None:
                sheet_pages.add(source.page_index)

    for page in preliminary.pages:
        roles[page.index] = (
            PageRole.BALANCE_SHEET
            if page.index in sheet_pages
            else PageRole.SUPPLEMENTARY
        )
    return roles


def _spans(text: str) -> list[tuple[int, int]]:
    """Character ranges to cut this page into, as ``(start, end)`` pairs.

    Offsets rather than strings so the caller can slice the page itself: a
    chunk that merely *resembles* its source is not traceable to it.
    """
    if not text.strip():
        return []
    if len(text) <= MAX_CHUNK:
        # The ordinary case for a Balance Sheet page. One chunk, whole.
        return [_trimmed(text, 0, len(text))]

    spans: list[tuple[int, int]] = []
    start = 0
    while start < len(text):
        end = _split_at(text, start)
        span = _trimmed(text, start, end)
        if span[1] > span[0]:
            spans.append(span)
        if end >= len(text):
            break
        # Step back by the overlap, but always make progress - a target
        # shorter than the overlap would otherwise loop forever.
        start = max(end - CHUNK_OVERLAP, start + 1)
    return spans


def _split_at(text: str, start: int) -> int:
    """Where to end a chunk beginning at ``start``.

    Aims for the target, accepts anything up to the hard maximum, and prefers
    the strongest boundary available in that window - a blank line over a line
    break over a sentence end over a space. Never splits inside a word.
    """
    if start + MAX_CHUNK >= len(text):
        return len(text)

    window_start = start + CHUNK_TARGET
    window = text[start : start + MAX_CHUNK]

    for boundary in _BOUNDARIES:
        found = window.rfind(boundary, CHUNK_TARGET)
        if found != -1:
            return start + found + len(boundary)

    # No boundary anywhere in the window - a single unbroken run of characters.
    # Cut at the maximum rather than growing without limit.
    return min(start + MAX_CHUNK, len(text))


def _trimmed(text: str, start: int, end: int) -> tuple[int, int]:
    """Shrink a span past leading and trailing whitespace.

    So a chunk never begins with a blank line, and the recorded offsets still
    slice out exactly the text that was stored.
    """
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


__all__ = [
    "CHUNK_OVERLAP",
    "CHUNK_SPEC_VERSION",
    "CHUNK_TARGET",
    "MAX_CHUNK",
    "chunks_for",
    "page_roles",
]
