from __future__ import annotations
from app.core.schemas import BalanceSheetDocument, DocumentChunk, PageRole, PreliminaryExtraction
CHUNK_SPEC_VERSION = '1.0.0'
CHUNK_TARGET = 600
MAX_CHUNK = 1000
CHUNK_OVERLAP = 100
_BOUNDARIES = ('\n\n', '\n', '. ', ' ')

def chunks_for(document: BalanceSheetDocument) -> list[DocumentChunk]:
    preliminary = document.preliminary
    if preliminary is None or document.id is None:
        return []
    roles = page_roles(document)
    chunks: list[DocumentChunk] = []
    for page in preliminary.pages:
        for position, (start, end) in enumerate(_spans(page.text)):
            chunks.append(DocumentChunk(document_id=document.id, page_index=page.index, sheet_name=page.name, page_role=roles.get(page.index, PageRole.SUPPLEMENTARY), chunk_index=position, char_start=start, char_end=end, text=page.text[start:end], embedding=[], embedding_model='', embedding_dim=1, chunk_spec_version=CHUNK_SPEC_VERSION))
    return chunks

def page_roles(document: BalanceSheetDocument) -> dict[int, PageRole]:
    roles: dict[int, PageRole] = {}
    preliminary: PreliminaryExtraction | None = document.preliminary
    if preliminary is None:
        return roles
    sheet_pages: set[int] = set()
    if document.identification is not None:
        sheet_pages.update((signal.source.page_index for signal in document.identification.signals))
    if document.extracted is not None:
        for field_name in ('assets', 'liabilities', 'equity'):
            source = getattr(document.extracted, field_name).total_source
            if source is not None:
                sheet_pages.add(source.page_index)
    for page in preliminary.pages:
        roles[page.index] = PageRole.BALANCE_SHEET if page.index in sheet_pages else PageRole.SUPPLEMENTARY
    return roles

def _spans(text: str) -> list[tuple[int, int]]:
    if not text.strip():
        return []
    if len(text) <= MAX_CHUNK:
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
        start = max(end - CHUNK_OVERLAP, start + 1)
    return spans

def _split_at(text: str, start: int) -> int:
    if start + MAX_CHUNK >= len(text):
        return len(text)
    window_start = start + CHUNK_TARGET
    window = text[start:start + MAX_CHUNK]
    for boundary in _BOUNDARIES:
        found = window.rfind(boundary, CHUNK_TARGET)
        if found != -1:
            return start + found + len(boundary)
    return min(start + MAX_CHUNK, len(text))

def _trimmed(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end)
__all__ = ['CHUNK_OVERLAP', 'CHUNK_SPEC_VERSION', 'CHUNK_TARGET', 'MAX_CHUNK', 'chunks_for', 'page_roles']
