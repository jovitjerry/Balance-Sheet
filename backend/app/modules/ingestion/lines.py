"""One view of a document, whatever produced it.

A Balance Sheet arrives as PDF text, as a PDF table, as an OCR'd scan, or as
worksheet rows. Identification should not care which. This turns all four into
the same thing: an ordered list of :class:`DocumentLine`, each a label and the
cells to its right, each carrying where it came from.

The cells keep their **printed** text. Nothing here parses a value or
interprets a label. It does ask whether a cell has the *shape* of a figure,
because that is what tells one label's column from the next one's - but the
shape is all it looks at, and no meaning is read out of any label.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.schemas import PreliminaryExtraction, SourcePage, SourceRef
from app.modules.ingestion.amounts import looks_like_amount
from app.modules.ingestion.ocr import group_into_lines


@dataclass(frozen=True)
class Cell:
    """One printed cell, with whatever positional information exists.

    ``x`` is present for PDF and OCR pages, where columns are geometric.
    ``column`` is present for worksheet rows, where they are ordinal. Period
    selection uses whichever it has.
    """

    text: str
    column: int
    x: float | None = None


@dataclass(frozen=True)
class LabelSegment:
    """One label and the figures printed to its right, within a single row.

    A row usually holds exactly one of these. A Balance Sheet printed in the
    horizontal layout holds two - see :attr:`DocumentLine.segments`.
    """

    label: Cell
    figures: list[Cell]


@dataclass
class DocumentLine:
    """One visual row, as an ordered list of column cells.

    The leading cell is the row's label and the rest are its figures - but all
    of them are cells, deliberately. A column-heading row has no label: its
    first column holds a date like every other column, and a model that treats
    cell zero as "the label" makes the current period's heading disappear
    exactly where period selection needs to see it.
    """

    page_index: int
    cells: list[Cell] = field(default_factory=list)
    row: int | None = None
    sheet_name: str | None = None

    @property
    def label(self) -> str:
        return self.cells[0].text if self.cells else ""

    @property
    def value_cells(self) -> list[Cell]:
        """The cells across from the label - where a figure would be."""
        return self.cells[1:]

    @property
    def segments(self) -> list[LabelSegment]:
        """The label-and-figures runs this row contains, left to right.

        A Balance Sheet is not always printed as one column of labels. The
        horizontal ("T-account") layout runs Assets down the left of the page
        and Liabilities and Equity down the right, so one visual row reads

            Intangible Assets  150,000    Total Liabilities  1,350,000

        and holds two labels, each with its own figure. Taking cell zero as
        *the* label makes every total in the right-hand column invisible - a
        genuine ``Total Liabilities`` line is then reported as missing while
        the sheet balances perfectly.

        A cell without the shape of a figure opens a new run as its label;
        figure-shaped cells attach to the run already open, so a figure belongs
        to the label on its left rather than to the row. A run whose label is
        itself figure-shaped has no label at all and is dropped.

        On a single-column sheet this yields exactly one run holding the same
        cells :attr:`label` and :attr:`value_cells` describe - including a
        comparative row, where both periods' figures stay under the one label
        that heads them and the choice between columns is left where it
        belongs, to period selection.
        """
        runs: list[tuple[Cell, list[Cell]]] = []
        for cell in self.cells:
            if runs and looks_like_amount(cell.text):
                runs[-1][1].append(cell)
            else:
                runs.append((cell, []))
        return [
            LabelSegment(label=label, figures=figures)
            for label, figures in runs
            if not looks_like_amount(label.text)
        ]

    @property
    def text(self) -> str:
        return " ".join(cell.text for cell in self.cells).strip()

    def source(self, column: int | None = None) -> SourceRef:
        return SourceRef(
            page_index=self.page_index,
            sheet_name=self.sheet_name,
            row=self.row,
            column=column,
        )


def build_lines(preliminary: PreliminaryExtraction) -> list[DocumentLine]:
    """Flatten every page into one ordered list of lines."""
    lines: list[DocumentLine] = []
    for page in preliminary.pages:
        lines.extend(build_page_lines(page))
    return lines


def build_page_lines(page: SourcePage) -> list[DocumentLine]:
    """Turn one page into lines, by whichever route that page supports.

    Word geometry is preferred wherever it exists - for a PDF, digital or
    scanned - because it is the only representation that says which *column* a
    figure sits in, and that is what decides its reporting period. Worksheets
    need no such reconstruction: a row already is a row.
    """
    if page.words:
        return _lines_from_words(page)
    if page.tables:
        return _lines_from_tables(page)
    return _lines_from_text(page)


def _lines_from_words(page: SourcePage) -> list[DocumentLine]:
    lines: list[DocumentLine] = []
    for row, grouped in enumerate(group_into_lines(page.words)):
        words = grouped.words
        if not words:  # pragma: no cover - grouping never emits an empty line
            continue

        # Split the row wherever the horizontal gap is wider than the spaces
        # between words. Each run becomes one cell, so a multi-word heading
        # like "31 March 2023" stays a single cell rather than fragmenting into
        # three - which would leave nothing that reads as a date.
        gap_threshold = _column_gap_threshold(words)
        groups: list[list] = [[words[0]]]
        for previous, word in zip(words, words[1:]):
            if (word.left - previous.right) > gap_threshold:
                groups.append([word])
            else:
                groups[-1].append(word)

        lines.append(
            DocumentLine(
                page_index=page.index,
                cells=[
                    Cell(
                        text=" ".join(word.text for word in group),
                        column=index,
                        x=min(word.left for word in group),
                    )
                    for index, group in enumerate(groups)
                ],
                row=row,
                sheet_name=page.name,
            )
        )
    return lines


def _column_gap_threshold(words: list) -> float:
    """How wide a horizontal gap has to be to count as a column break.

    Scaled to the type size on the line, so it holds at 300 dpi and at 72 pt
    alike. Roughly two and a half character widths - wider than the space
    between words, narrower than the run-up to a figure column.
    """
    heights = [word.height for word in words if word.height > 0]
    typical = sum(heights) / len(heights) if heights else 10.0
    return typical * 1.5


def _lines_from_tables(page: SourcePage) -> list[DocumentLine]:
    lines: list[DocumentLine] = []
    row_index = 0
    for table in page.tables:
        for cells in table.rows:
            present = [(index, (text or "").strip()) for index, text in enumerate(cells)]
            filled = [(index, text) for index, text in present if text]
            if not filled:
                row_index += 1
                continue

            lines.append(
                DocumentLine(
                    page_index=page.index,
                    # Original worksheet column indices are kept, so a period
                    # heading in column C and its figures in column C line up.
                    cells=[Cell(text=text, column=index) for index, text in filled],
                    row=row_index,
                    sheet_name=page.name,
                )
            )
            row_index += 1
    return lines


def _lines_from_text(page: SourcePage) -> list[DocumentLine]:
    """Last resort: plain text, with no geometry to work from.

    Columns cannot be recovered here, so every line is label-only. A document
    that reaches this path can still be identified, but a comparative one
    cannot have its periods told apart - which is reported rather than guessed.
    """
    return [
        DocumentLine(
            page_index=page.index,
            cells=[Cell(text=line.strip(), column=0)],
            row=row,
            sheet_name=page.name,
        )
        for row, line in enumerate(page.text.splitlines())
        if line.strip()
    ]


__all__ = [
    "Cell",
    "DocumentLine",
    "LabelSegment",
    "build_lines",
    "build_page_lines",
]
