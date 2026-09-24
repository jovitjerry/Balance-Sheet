from __future__ import annotations
from dataclasses import dataclass, field
from statistics import median
from app.core.amounts import looks_like_amount
from app.core.schemas import PeriodSelection, PositionedWord, PreliminaryExtraction, SourcePage, SourceRef
LINE_GROUPING_TOLERANCE = 0.6

@dataclass
class WordRow:
    words: list[PositionedWord] = field(default_factory=list)

    @property
    def text(self) -> str:
        return ' '.join((word.text for word in self.words))

    @property
    def top(self) -> float:
        return min((word.top for word in self.words))

    @property
    def bottom(self) -> float:
        return max((word.top + word.height for word in self.words))

    def words_right_of(self, x: float) -> list[PositionedWord]:
        return [word for word in self.words if word.left >= x]

def group_into_lines(words: list[PositionedWord], *, tolerance: float=LINE_GROUPING_TOLERANCE) -> list[WordRow]:
    if not words:
        return []
    band = median([word.height for word in words if word.height > 0] or [1]) * tolerance
    band = max(band, 1.0)
    ordered = sorted(words, key=lambda word: (word.top + word.height / 2, word.left))
    lines: list[list[PositionedWord]] = []
    current: list[PositionedWord] = []
    current_centre = 0.0
    for word in ordered:
        centre = word.top + word.height / 2
        if current and abs(centre - current_centre) > band:
            lines.append(current)
            current = []
        if not current:
            current_centre = centre
        else:
            current_centre = (current_centre * len(current) + centre) / (len(current) + 1)
        current.append(word)
    if current:
        lines.append(current)
    return [WordRow(words=sorted(line, key=lambda word: word.left)) for line in lines]

@dataclass(frozen=True)
class Cell:
    text: str
    column: int
    x: float | None = None

@dataclass(frozen=True)
class LabelSegment:
    label: Cell
    figures: list[Cell]

@dataclass
class DocumentLine:
    page_index: int
    cells: list[Cell] = field(default_factory=list)
    row: int | None = None
    sheet_name: str | None = None

    @property
    def label(self) -> str:
        return self.cells[0].text if self.cells else ''

    @property
    def value_cells(self) -> list[Cell]:
        return self.cells[1:]

    @property
    def segments(self) -> list[LabelSegment]:
        runs: list[tuple[Cell, list[Cell]]] = []
        for cell in self.cells:
            if runs and looks_like_amount(cell.text):
                runs[-1][1].append(cell)
            else:
                runs.append((cell, []))
        return [LabelSegment(label=label, figures=figures) for label, figures in runs if not looks_like_amount(label.text)]

    @property
    def text(self) -> str:
        return ' '.join((cell.text for cell in self.cells)).strip()

    def source(self, column: int | None=None) -> SourceRef:
        return SourceRef(page_index=self.page_index, sheet_name=self.sheet_name, row=self.row, column=column)

def build_lines(preliminary: PreliminaryExtraction) -> list[DocumentLine]:
    lines: list[DocumentLine] = []
    for page in preliminary.pages:
        lines.extend(build_page_lines(page))
    return lines

def build_page_lines(page: SourcePage) -> list[DocumentLine]:
    if page.words:
        return _lines_from_words(page)
    if page.tables:
        return _lines_from_tables(page)
    return _lines_from_text(page)

def _lines_from_words(page: SourcePage) -> list[DocumentLine]:
    lines: list[DocumentLine] = []
    for row, grouped in enumerate(group_into_lines(page.words)):
        words = grouped.words
        if not words:
            continue
        gap_threshold = _column_gap_threshold(words)
        groups: list[list] = [[words[0]]]
        for previous, word in zip(words, words[1:]):
            if word.left - previous.right > gap_threshold:
                groups.append([word])
            else:
                groups[-1].append(word)
        lines.append(DocumentLine(page_index=page.index, cells=[Cell(text=' '.join((word.text for word in group)), column=index, x=min((word.left for word in group))) for index, group in enumerate(groups)], row=row, sheet_name=page.name))
    return lines

def _column_gap_threshold(words: list) -> float:
    heights = [word.height for word in words if word.height > 0]
    typical = sum(heights) / len(heights) if heights else 10.0
    return typical * 1.5

def _lines_from_tables(page: SourcePage) -> list[DocumentLine]:
    lines: list[DocumentLine] = []
    row_index = 0
    for table in page.tables:
        for cells in table.rows:
            present = [(index, (text or '').strip()) for index, text in enumerate(cells)]
            filled = [(index, text) for index, text in present if text]
            if not filled:
                row_index += 1
                continue
            lines.append(DocumentLine(page_index=page.index, cells=[Cell(text=text, column=index) for index, text in filled], row=row_index, sheet_name=page.name))
            row_index += 1
    return lines

def _lines_from_text(page: SourcePage) -> list[DocumentLine]:
    return [DocumentLine(page_index=page.index, cells=[Cell(text=line.strip(), column=0)], row=row, sheet_name=page.name) for row, line in enumerate(page.text.splitlines()) if line.strip()]

def column_x_for(lines: list[DocumentLine], period: PeriodSelection | None) -> float | None:
    if period is None:
        return None
    target = period.selected.source
    for line in lines:
        if line.page_index != target.page_index or line.row != target.row:
            continue
        for cell in line.cells:
            if cell.column == target.column:
                return cell.x
    return None

def figure_for(segment: LabelSegment, column: int | None, column_x: float | None) -> Cell | None:
    figures = [cell for cell in segment.figures if looks_like_amount(cell.text)]
    if not figures:
        return None
    if column_x is not None:
        positioned = [cell for cell in figures if cell.x is not None]
        if positioned:
            return min(positioned, key=lambda cell: abs(cell.x - column_x))
    if column is not None:
        exact = [cell for cell in figures if cell.column == column]
        if exact:
            return exact[0]
    return figures[0]
__all__ = ['LINE_GROUPING_TOLERANCE', 'Cell', 'DocumentLine', 'LabelSegment', 'WordRow', 'build_lines', 'build_page_lines', 'column_x_for', 'figure_for', 'group_into_lines']
